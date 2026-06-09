from __future__ import annotations

import argparse
import errno
import inspect
import logging
import os
import stat
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pyfuse3
import trio
from pyfuse3 import EntryAttributes, FileHandleT, FileInfo, FUSEError, InodeT, ReaddirToken, RequestContext, SetattrFields, StatvfsData

from host_tools.disk.inspect import inspect_slice_metadata_by_selector, read_slice_bytes
from host_tools.fs.bfs import BFS_VDIR, bfs_allocated_bytes, bfs_file_size
from host_tools.fs.bfs import detect_bfs
from host_tools.fs.bfs_backend import BFSBackend
from host_tools.fs.common import BFS_ROOT_INODE, FilesystemCandidate, SECTOR_SIZE


log = logging.getLogger(__name__)


class DirtyTrackingBytearray(bytearray):
    def __new__(cls, initial: bytes | bytearray = b'') -> 'DirtyTrackingBytearray':
        instance = super().__new__(cls, initial)
        instance._dirty_ranges: list[tuple[int, int]] = []
        return instance

    def _record_dirty_range(self, start: int, end: int) -> None:
        bounded_start = max(0, start)
        bounded_end = min(len(self), end)
        if bounded_start >= bounded_end:
            return
        merged_start = bounded_start
        merged_end = bounded_end
        merged_ranges: list[tuple[int, int]] = []
        inserted = False
        for existing_start, existing_end in self._dirty_ranges:
            if existing_end < merged_start:
                merged_ranges.append((existing_start, existing_end))
                continue
            if merged_end < existing_start:
                if not inserted:
                    merged_ranges.append((merged_start, merged_end))
                    inserted = True
                merged_ranges.append((existing_start, existing_end))
                continue
            merged_start = min(merged_start, existing_start)
            merged_end = max(merged_end, existing_end)
        if not inserted:
            merged_ranges.append((merged_start, merged_end))
        self._dirty_ranges = merged_ranges

    def consume_dirty_ranges(self) -> list[tuple[int, int]]:
        ranges = list(self._dirty_ranges)
        self._dirty_ranges.clear()
        return ranges

    def __setitem__(self, key: int | slice, value: object) -> None:
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step == 1:
                dirty_start = start
                dirty_end = stop
            else:
                positions = list(range(start, stop, step))
                if positions:
                    dirty_start = min(positions)
                    dirty_end = max(positions) + 1
                else:
                    dirty_start = 0
                    dirty_end = 0
        else:
            index = key if key >= 0 else len(self) + key
            dirty_start = index
            dirty_end = index + 1
        super().__setitem__(key, value)
        self._record_dirty_range(dirty_start, dirty_end)


def init_logging(debug: bool = False) -> None:
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d %(threadName)s: [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    if debug:
        handler.setLevel(logging.DEBUG)
        root_logger.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)
        root_logger.setLevel(logging.INFO)
    for existing_handler in root_logger.handlers:
        if isinstance(existing_handler, logging.StreamHandler) and getattr(existing_handler, '_svr4_host_tools_handler', False):
            existing_handler.setLevel(handler.level)
            existing_handler.setFormatter(formatter)
            return
    handler._svr4_host_tools_handler = True
    root_logger.addHandler(handler)


def _mode_with_umask(mode: int, umask: int) -> int:
    return mode & ~umask


def _seconds_from_ns(value: int) -> int:
    if value <= 0:
        return 0
    return value // 1_000_000_000


def _translate_bfs_error(error: BaseException) -> FUSEError:
    if isinstance(error, FUSEError):
        return error

    message = str(error)
    if 'already exists' in message:
        return FUSEError(errno.EEXIST)
    if 'could not resolve' in message or 'does not exist' in message:
        return FUSEError(errno.ENOENT)
    if 'not a BFS directory' in message:
        return FUSEError(errno.ENOTDIR)
    if '14-character BFS limit' in message:
        return FUSEError(errno.ENAMETOOLONG)
    if 'not ASCII' in message:
        return FUSEError(errno.EINVAL)
    if 'root directory contents as a regular file' in message or 'root cannot be used as a regular file path' in message:
        return FUSEError(errno.EISDIR)
    if 'no free BFS dirent slots remain' in message or 'does not have enough contiguous space' in message:
        return FUSEError(errno.ENOSPC)
    if 'refusing to' in message:
        return FUSEError(errno.EPERM)
    if isinstance(error, ValueError):
        return FUSEError(errno.EINVAL)
    return FUSEError(errno.EIO)


@dataclass
class BFSVolume:
    image: bytearray
    filesystem: FilesystemCandidate
    sector_count: int
    flush_callback: Callable[[bytearray, Sequence[tuple[int, int]], bool], None] | None = None
    close_callback: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.image, DirtyTrackingBytearray):
            self.image = DirtyTrackingBytearray(self.image)

    @classmethod
    def open_raw_image(cls, image_path: Path, slice_selector: str) -> 'BFSVolume':
        resolved_path = image_path.resolve()
        _, slice_info = inspect_slice_metadata_by_selector(resolved_path, slice_selector)
        slice_image = bytearray(read_slice_bytes(resolved_path, slice_info.absolute_start_sector, slice_info.sector_count))
        candidates = detect_bfs(bytes(slice_image))
        if not candidates:
            raise SystemExit(f'error: failed to detect a BFS filesystem inside slice {slice_selector!r}')

        filesystem = candidates[0]
        for candidate in candidates:
            if candidate.start_offset == slice_info.filesystem_offset:
                filesystem = candidate
                break

        handle = resolved_path.open('r+b')
        disk_offset = slice_info.absolute_start_sector * SECTOR_SIZE

        def flush_callback(data: bytearray, dirty_ranges: Sequence[tuple[int, int]], sync: bool) -> None:
            for start, end in dirty_ranges:
                handle.seek(disk_offset + start)
                handle.write(data[start:end])
            handle.flush()
            if sync:
                os.fsync(handle.fileno())

        return cls(
            image=slice_image,
            filesystem=filesystem,
            sector_count=slice_info.sector_count,
            flush_callback=flush_callback,
            close_callback=handle.close,
        )

    def flush(self, sync: bool = True) -> None:
        if self.flush_callback is not None:
            dirty_ranges = self.image.consume_dirty_ranges() if isinstance(self.image, DirtyTrackingBytearray) else []
            if dirty_ranges or sync:
                if len(inspect.signature(self.flush_callback).parameters) == 1:
                    self.flush_callback(self.image)  # type: ignore[misc]
                else:
                    self.flush_callback(self.image, dirty_ranges, sync)

    def close(self) -> None:
        self.flush(sync=True)
        if self.close_callback is not None:
            self.close_callback()
            self.close_callback = None


@dataclass
class OpenHandle:
    inode: InodeT


@dataclass
class PendingDeletion:
    directory: bool


class BFSOperations(pyfuse3.Operations):
    supports_dot_lookup = True
    enable_writeback_cache = False

    def __init__(self, volume: BFSVolume, slow_op_ms: float = 0.0, cache_timeout: float = 1.0) -> None:
        super().__init__()
        self._volume = volume
        self._backend = BFSBackend(volume.image, volume.filesystem)
        self._slow_op_ms = slow_op_ms
        self._cache_timeout = cache_timeout
        self._lock = trio.Lock()
        self._lookup_counts: defaultdict[InodeT, int] = defaultdict(int)
        self._open_handles: dict[FileHandleT, OpenHandle] = {}
        self._directory_handles: dict[FileHandleT, InodeT] = {}
        self._pending_deletions: dict[InodeT, PendingDeletion] = {}
        self._next_handle = 1

    def _log_slow_operation(self, operation: str, started_at: float, detail: str) -> None:
        if self._slow_op_ms <= 0:
            return
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if elapsed_ms >= self._slow_op_ms:
            log.warning('slow fuse op %s %.1f ms: %s', operation, elapsed_ms, detail)

    def _new_handle(self) -> FileHandleT:
        handle = FileHandleT(self._next_handle)
        self._next_handle += 1
        return handle

    def _fuse_inode(self, bfs_inode: int) -> InodeT:
        if bfs_inode == BFS_ROOT_INODE:
            return InodeT(pyfuse3.ROOT_INODE)
        return InodeT(bfs_inode)

    def _bfs_inode_number(self, inode: InodeT) -> int:
        if inode == pyfuse3.ROOT_INODE:
            return BFS_ROOT_INODE
        return int(inode)

    def _inode_state(self, inode: InodeT) -> tuple[int, dict[str, int]]:
        bfs_inode = self._bfs_inode_number(inode)
        inode_data = self._backend.getattr_inode(bfs_inode)
        return bfs_inode, inode_data

    def _entry_from_inode(self, bfs_inode: int, inode: dict[str, int]) -> EntryAttributes:
        entry = EntryAttributes()
        entry.st_ino = self._fuse_inode(bfs_inode)
        entry.generation = 0
        entry.entry_timeout = self._cache_timeout
        entry.attr_timeout = self._cache_timeout
        file_mode = stat.S_IFDIR if int(inode['file_type']) == BFS_VDIR else stat.S_IFREG
        entry.st_mode = file_mode | stat.S_IMODE(int(inode['mode']))
        entry.st_nlink = int(inode['nlink'])
        entry.st_uid = int(inode['uid'])
        entry.st_gid = int(inode['gid'])
        entry.st_rdev = 0
        entry.st_size = bfs_file_size(inode)
        entry.st_blksize = SECTOR_SIZE
        entry.st_blocks = bfs_allocated_bytes(inode) // SECTOR_SIZE
        entry.st_atime_ns = int(inode.get('atime', 0)) * 1_000_000_000
        entry.st_mtime_ns = int(inode.get('mtime', 0)) * 1_000_000_000
        entry.st_ctime_ns = int(inode.get('ctime', 0)) * 1_000_000_000
        return entry

    def _entry_from_fuse_inode(self, inode: InodeT) -> EntryAttributes:
        bfs_inode, inode_data = self._inode_state(inode)
        return self._entry_from_inode(bfs_inode, inode_data)

    def _flush(self) -> None:
        self._volume.flush()

    def _inode_bytes(self, inode: InodeT) -> tuple[int, dict[str, int], bytes]:
        bfs_inode, inode_data = self._inode_state(inode)
        data = self._backend.read_inode(bfs_inode)
        return bfs_inode, inode_data, data

    def _write_data(self, inode: InodeT, offset: int, data: bytes) -> None:
        bfs_inode, _, current = self._inode_bytes(inode)
        if offset > len(current):
            current = current + (b'\0' * (offset - len(current)))
        updated = current[:offset] + data
        tail_offset = offset + len(data)
        if tail_offset < len(current):
            updated += current[tail_offset:]
        self._backend.write_inode(bfs_inode, updated)

    def _truncate(self, inode: InodeT, size: int) -> None:
        bfs_inode, _, current = self._inode_bytes(inode)
        if size < len(current):
            updated = current[:size]
        else:
            updated = current + (b'\0' * (size - len(current)))
        self._backend.write_inode(bfs_inode, updated)

    def _inode_open_count(self, inode: InodeT) -> int:
        count = 0
        for handle in self._open_handles.values():
            if handle.inode == inode:
                count += 1
        return count

    def _maybe_finalize_pending_inode(self, inode: InodeT) -> None:
        pending = self._pending_deletions.get(inode)
        if pending is None:
            return
        if self._lookup_counts.get(inode, 0) > 0:
            return
        if self._inode_open_count(inode) > 0:
            return
        self._backend.finalize_unlinked_inode(self._bfs_inode_number(inode))
        self._flush()
        self._pending_deletions.pop(inode, None)

    async def forget(self, inode_list: Sequence[tuple[InodeT, int]]) -> None:
        for inode, nlookup in inode_list:
            if self._lookup_counts[inode] > nlookup:
                self._lookup_counts[inode] -= nlookup
            else:
                self._lookup_counts.pop(inode, None)
            self._maybe_finalize_pending_inode(inode)

    async def lookup(self, parent_inode: InodeT, name: bytes, ctx: RequestContext) -> EntryAttributes:
        del ctx
        started_at = time.perf_counter()
        async with self._lock:
            try:
                if parent_inode != pyfuse3.ROOT_INODE:
                    raise FUSEError(errno.ENOTDIR)
                name_text = os.fsdecode(name)
                if name_text in {'.', '..'}:
                    return self._entry_from_fuse_inode(pyfuse3.ROOT_INODE)
                bfs_inode, inode_data = self._backend.lookup('/' + name_text)
                entry = self._entry_from_inode(bfs_inode, inode_data)
                self._lookup_counts[cast(InodeT, entry.st_ino)] += 1
                return entry
            except BaseException as error:
                raise _translate_bfs_error(error) from error
            finally:
                self._log_slow_operation('lookup', started_at, f'parent={parent_inode} name={os.fsdecode(name)!r}')

    async def getattr(self, inode: InodeT, ctx: RequestContext | None = None) -> EntryAttributes:
        del ctx
        started_at = time.perf_counter()
        async with self._lock:
            try:
                return self._entry_from_fuse_inode(inode)
            except BaseException as error:
                raise _translate_bfs_error(error) from error
            finally:
                self._log_slow_operation('getattr', started_at, f'inode={inode}')

    async def opendir(self, inode: InodeT, ctx: RequestContext) -> FileHandleT:
        del ctx
        async with self._lock:
            entry = self._entry_from_fuse_inode(inode)
            if not stat.S_ISDIR(entry.st_mode):
                raise FUSEError(errno.ENOTDIR)
            handle = self._new_handle()
            self._directory_handles[handle] = inode
            return handle

    async def readdir(self, fh: FileHandleT, start_id: int, token: ReaddirToken) -> None:
        started_at = time.perf_counter()
        async with self._lock:
            try:
                inode = self._directory_handles[fh]
                if inode != pyfuse3.ROOT_INODE:
                    raise FUSEError(errno.ENOTDIR)
                root_attr = self._entry_from_fuse_inode(pyfuse3.ROOT_INODE)
                entries: list[tuple[str, EntryAttributes, int]] = [
                    ('.', root_attr, 1),
                    ('..', root_attr, 2),
                ]
                next_id = 3
                for directory_entry in sorted(self._backend.readdir('/'), key=lambda item: str(item['name'])):
                    bfs_inode = int(directory_entry['inode'])
                    attr = self._entry_from_inode(bfs_inode, self._backend.getattr_inode(bfs_inode))
                    entries.append((str(directory_entry['name']), attr, next_id))
                    next_id += 1

                for child_name, attr, child_next_id in entries:
                    if child_next_id <= start_id:
                        continue
                    if not pyfuse3.readdir_reply(token, os.fsencode(child_name), attr, child_next_id):
                        break
                    if child_name not in {'.', '..'}:
                        self._lookup_counts[cast(InodeT, attr.st_ino)] += 1
            except BaseException as error:
                raise _translate_bfs_error(error) from error
            finally:
                self._log_slow_operation('readdir', started_at, f'fh={fh} start_id={start_id}')

    async def releasedir(self, fh: FileHandleT) -> None:
        self._directory_handles.pop(fh, None)

    async def open(self, inode: InodeT, flags: int, ctx: RequestContext) -> FileInfo:
        del flags, ctx
        async with self._lock:
            entry = self._entry_from_fuse_inode(inode)
            if stat.S_ISDIR(entry.st_mode):
                raise FUSEError(errno.EISDIR)
            handle = self._new_handle()
            self._open_handles[handle] = OpenHandle(inode=inode)
            info = FileInfo(fh=handle)
            info.direct_io = True
            info.keep_cache = True
            return info

    async def read(self, fh: FileHandleT, off: int, size: int) -> bytes:
        async with self._lock:
            try:
                inode = self._open_handles[fh].inode
                _, _, data = self._inode_bytes(inode)
                return data[off:off + size]
            except BaseException as error:
                raise _translate_bfs_error(error) from error

    async def write(self, fh: FileHandleT, off: int, buf: bytes) -> int:
        async with self._lock:
            try:
                inode = self._open_handles[fh].inode
                self._write_data(inode, off, buf)
                now = int(time.time())
                self._backend.setattr_inode(self._bfs_inode_number(inode), mtime=now, ctime=now)
                self._flush()
                return len(buf)
            except BaseException as error:
                raise _translate_bfs_error(error) from error

    async def release(self, fh: FileHandleT) -> None:
        handle = self._open_handles.pop(fh, None)
        if handle is not None:
            self._maybe_finalize_pending_inode(handle.inode)

    async def flush(self, fh: FileHandleT) -> None:
        del fh
        async with self._lock:
            self._flush()

    async def fsync(self, fh: FileHandleT, datasync: bool) -> None:
        del fh, datasync
        async with self._lock:
            self._flush()

    async def fsyncdir(self, fh: FileHandleT, datasync: bool) -> None:
        del fh, datasync
        async with self._lock:
            self._flush()

    async def access(self, inode: InodeT, mode: int, ctx: RequestContext) -> bool:
        del inode, mode, ctx
        return True

    async def create(self, parent_inode: InodeT, name: bytes, mode: int, flags: int, ctx: RequestContext) -> tuple[FileInfo, EntryAttributes]:
        del flags
        async with self._lock:
            try:
                if parent_inode != pyfuse3.ROOT_INODE:
                    raise FUSEError(errno.ENOTDIR)
                path = '/' + os.fsdecode(name)
                result = self._backend.create(
                    path,
                    b'',
                    mode=_mode_with_umask(mode, ctx.umask),
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                )
                self._flush()
                inode = self._fuse_inode(int(result['inode']))
                self._lookup_counts[inode] += 1
                entry = self._entry_from_fuse_inode(inode)
                handle = self._new_handle()
                self._open_handles[handle] = OpenHandle(inode=inode)
                info = FileInfo(fh=handle)
                info.direct_io = True
                info.keep_cache = True
                return info, entry
            except BaseException as error:
                raise _translate_bfs_error(error) from error

    async def mknod(self, parent_inode: InodeT, name: bytes, mode: int, rdev: int, ctx: RequestContext) -> EntryAttributes:
        del rdev
        if not stat.S_ISREG(mode):
            raise FUSEError(errno.ENOSYS)
        async with self._lock:
            try:
                if parent_inode != pyfuse3.ROOT_INODE:
                    raise FUSEError(errno.ENOTDIR)
                path = '/' + os.fsdecode(name)
                result = self._backend.create(
                    path,
                    b'',
                    mode=_mode_with_umask(mode, ctx.umask),
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                )
                self._flush()
                inode = self._fuse_inode(int(result['inode']))
                self._lookup_counts[inode] += 1
                return self._entry_from_fuse_inode(inode)
            except BaseException as error:
                raise _translate_bfs_error(error) from error

    async def mkdir(self, parent_inode: InodeT, name: bytes, mode: int, ctx: RequestContext) -> EntryAttributes:
        del parent_inode, name, mode, ctx
        raise FUSEError(errno.ENOSYS)

    async def unlink(self, parent_inode: InodeT, name: bytes, ctx: RequestContext) -> None:
        del ctx
        async with self._lock:
            try:
                if parent_inode != pyfuse3.ROOT_INODE:
                    raise FUSEError(errno.ENOTDIR)
                path = '/' + os.fsdecode(name)
                bfs_inode, inode_data = self._backend.lookup(path)
                inode = self._fuse_inode(bfs_inode)
                if int(inode_data['file_type']) == BFS_VDIR:
                    raise FUSEError(errno.EISDIR)
                if self._lookup_counts.get(inode, 0) > 0 or self._inode_open_count(inode) > 0:
                    self._backend.detach(path)
                    self._pending_deletions[inode] = PendingDeletion(directory=False)
                else:
                    self._backend.unlink(path)
                self._flush()
            except BaseException as error:
                raise _translate_bfs_error(error) from error

    async def rmdir(self, parent_inode: InodeT, name: bytes, ctx: RequestContext) -> None:
        del parent_inode, name, ctx
        raise FUSEError(errno.ENOSYS)

    async def symlink(self, parent_inode: InodeT, name: bytes, target: bytes, ctx: RequestContext) -> EntryAttributes:
        del parent_inode, name, target, ctx
        raise FUSEError(errno.ENOSYS)

    async def rename(
        self,
        parent_inode_old: InodeT,
        name_old: bytes,
        parent_inode_new: InodeT,
        name_new: bytes,
        flags: int,
        ctx: RequestContext,
    ) -> None:
        del ctx
        if flags & pyfuse3.RENAME_EXCHANGE:
            raise FUSEError(errno.ENOSYS)
        async with self._lock:
            try:
                if parent_inode_old != pyfuse3.ROOT_INODE or parent_inode_new != pyfuse3.ROOT_INODE:
                    raise FUSEError(errno.ENOTDIR)
                source_path = '/' + os.fsdecode(name_old)
                target_path = '/' + os.fsdecode(name_new)
                if flags & pyfuse3.RENAME_NOREPLACE:
                    try:
                        self._backend.lookup(target_path)
                    except SystemExit as error:
                        if 'could not resolve' not in str(error):
                            raise
                    else:
                        raise FUSEError(errno.EEXIST)

                overwritten_inode: InodeT | None = None
                try:
                    overwritten_bfs_inode, _ = self._backend.lookup(target_path)
                except SystemExit as error:
                    if 'could not resolve' not in str(error):
                        raise
                else:
                    overwritten_inode = self._fuse_inode(overwritten_bfs_inode)

                detach_target = False
                if overwritten_inode is not None and (self._lookup_counts.get(overwritten_inode, 0) > 0 or self._inode_open_count(overwritten_inode) > 0):
                    detach_target = True
                self._backend.rename(source_path, target_path, detach_target=detach_target)
                if detach_target and overwritten_inode is not None:
                    self._pending_deletions[overwritten_inode] = PendingDeletion(directory=False)
                self._flush()
            except BaseException as error:
                raise _translate_bfs_error(error) from error

    async def link(self, inode: InodeT, new_parent_inode: InodeT, new_name: bytes, ctx: RequestContext) -> EntryAttributes:
        del inode, new_parent_inode, new_name, ctx
        raise FUSEError(errno.ENOSYS)

    async def setattr(
        self,
        inode: InodeT,
        attr: EntryAttributes,
        fields: SetattrFields,
        fh: FileHandleT | None,
        ctx: RequestContext,
    ) -> EntryAttributes:
        del fh, ctx
        async with self._lock:
            try:
                bfs_inode, current_inode = self._inode_state(inode)
                changed = False
                if fields.update_size:
                    self._truncate(inode, int(attr.st_size))
                    changed = True

                metadata_updates: dict[str, int] = {}
                if fields.update_mode:
                    metadata_updates['mode'] = stat.S_IMODE(int(attr.st_mode))
                if fields.update_uid:
                    metadata_updates['uid'] = int(attr.st_uid)
                if fields.update_gid:
                    metadata_updates['gid'] = int(attr.st_gid)
                if fields.update_atime:
                    metadata_updates['atime'] = _seconds_from_ns(int(attr.st_atime_ns))
                if fields.update_mtime:
                    metadata_updates['mtime'] = _seconds_from_ns(int(attr.st_mtime_ns))
                if fields.update_ctime:
                    metadata_updates['ctime'] = _seconds_from_ns(int(attr.st_ctime_ns))
                elif changed:
                    metadata_updates['ctime'] = int(time.time())
                if metadata_updates:
                    self._backend.setattr_inode(bfs_inode, **metadata_updates)
                    changed = True

                if changed:
                    self._flush()
                return self._entry_from_inode(bfs_inode, self._backend.getattr_inode(bfs_inode))
            except BaseException as error:
                raise _translate_bfs_error(error) from error

    async def getxattr(self, inode: InodeT, name: bytes, ctx: RequestContext) -> bytes:
        del inode, name, ctx
        raise FUSEError(errno.ENOSYS)

    async def listxattr(self, inode: InodeT, ctx: RequestContext) -> Sequence[bytes]:
        del inode, ctx
        raise FUSEError(errno.ENOSYS)

    async def setxattr(self, inode: InodeT, name: bytes, value: bytes, ctx: RequestContext) -> None:
        del inode, name, value, ctx
        raise FUSEError(errno.ENOSYS)

    async def removexattr(self, inode: InodeT, name: bytes, ctx: RequestContext) -> None:
        del inode, name, ctx
        raise FUSEError(errno.ENOSYS)

    async def statfs(self, ctx: RequestContext) -> StatvfsData:
        del ctx
        async with self._lock:
            stats = StatvfsData()
            values = self._backend.statfs()
            stats.f_bsize = int(values['bsize'])
            stats.f_frsize = int(values['bsize'])
            stats.f_blocks = int(values['blocks'])
            stats.f_bfree = int(values['bfree'])
            stats.f_bavail = int(values['bfree'])
            stats.f_files = int(values['files'])
            stats.f_ffree = int(values['ffree'])
            stats.f_favail = int(values['ffree'])
            stats.f_namemax = int(values['namemax'])
            return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Mount an SVR4 BFS slice from a raw disk image with pyfuse3.')
    parser.add_argument('image', type=Path, help='Path to the raw disk image')
    parser.add_argument('mountpoint', type=Path, help='Where to mount the BFS filesystem')
    parser.add_argument('--slice', default='stand', help='Slice selector, by index or VTOC tag name (default: stand)')
    parser.add_argument('--debug', action='store_true', default=False, help='Enable Python-side debug logging')
    parser.add_argument('--debug-fuse', action='store_true', default=False, help='Enable libfuse debug logging')
    parser.add_argument('--allow-other', action='store_true', default=False, help='Pass allow_other to FUSE')
    parser.add_argument('--no-default-permissions', action='store_true', default=False, help='Do not let the kernel enforce mode bits before FUSE operations')
    parser.add_argument('--slow-op-ms', type=float, default=0.0, help='Log lookup/getattr/readdir operations slower than this many milliseconds')
    parser.add_argument('--cache-timeout', type=float, default=1.0, help='Kernel entry/attribute cache timeout in seconds (default: 1.0)')
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_args(argv)
    init_logging(options.debug)

    volume = BFSVolume.open_raw_image(options.image, options.slice)
    operations = BFSOperations(volume, slow_op_ms=options.slow_op_ms, cache_timeout=options.cache_timeout)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add(f'fsname=svr4-bfs:{options.image.name}:{options.slice}')
    if options.no_default_permissions:
        fuse_options.discard('default_permissions')
    if options.allow_other:
        fuse_options.add('allow_other')
    if options.debug_fuse:
        fuse_options.add('debug')

    pyfuse3.init(operations, str(options.mountpoint), fuse_options)
    try:
        trio.run(pyfuse3.main)
    except BaseException:
        pyfuse3.close(unmount=False)
        volume.close()
        raise

    pyfuse3.close()
    volume.close()
    return 0


def make_test_context(uid: int = 0, gid: int = 0, umask: int = 0o022) -> SimpleNamespace:
    return SimpleNamespace(uid=uid, gid=gid, umask=umask, pid=1)
