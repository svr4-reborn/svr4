from __future__ import annotations

import argparse
import errno
import logging
import os
import posixpath
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

from host_tools.disk.inspect import inspect_slice_by_selector, read_slice_bytes
from host_tools.fs.common import FilesystemCandidate, SECTOR_SIZE, UFS_ROOT_INODE, u32
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NBFREE_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NIFREE_OFFSET
from host_tools.fs.ufs import iter_ufs_inode_directory_records
from host_tools.fs.ufs import read_ufs_inode_range
from host_tools.fs.ufs import read_ufs_path_range
from host_tools.fs.ufs import apply_ufs_inode_truncate
from host_tools.fs.ufs import apply_ufs_inode_write
from host_tools.fs.ufs import apply_ufs_inode_replacement
from host_tools.fs.ufs import create_ufs_file
from host_tools.fs.ufs import detach_ufs_directory
from host_tools.fs.ufs import detach_ufs_path
from host_tools.fs.ufs import detect_ufs
from host_tools.fs.ufs import finalize_ufs_unlinked_inode
from host_tools.fs.ufs import link_ufs_path
from host_tools.fs.ufs import make_ufs_directory
from host_tools.fs.ufs import read_ufs_inode
from host_tools.fs.ufs import ufs_allocation_byte_sizes
from host_tools.fs.ufs import ufs_inode_data_blocks
from host_tools.fs.ufs import remove_ufs_directory
from host_tools.fs.ufs import rename_ufs_path
from host_tools.fs.ufs import resolve_ufs_path
from host_tools.fs.ufs import symlink_ufs_path
from host_tools.fs.ufs import ufs_file_type
from host_tools.fs.ufs import ufs_is_symlink
from host_tools.fs.ufs import ufs_inode_pointer_blocks
from host_tools.fs.ufs import unlink_ufs_path
from host_tools.fs.ufs import write_ufs_inode_mode
from host_tools.fs.ufs import write_ufs_inode_times
from host_tools.fs.ufs import write_ufs_inode_uid_gid


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

    def dirty_ranges(self) -> list[tuple[int, int]]:
        return list(self._dirty_ranges)

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


def _join_path(parent_path: str, name: str) -> str:
    if parent_path == '/':
        return '/' + name
    return parent_path + '/' + name


def _parent_path(path: str) -> str:
    if path == '/':
        return '/'
    parent = posixpath.dirname(path)
    return parent or '/'


def _mode_with_umask(mode: int, umask: int) -> int:
    return mode & ~umask


def _seconds_from_ns(value: int) -> int:
    if value <= 0:
        return 0
    return value // 1_000_000_000


def _translate_ufs_error(error: BaseException) -> FUSEError:
    if isinstance(error, FUSEError):
        return error

    message = str(error)
    if 'already exists' in message:
        return FUSEError(errno.EEXIST)
    if 'does not exist' in message or 'could not resolve' in message:
        return FUSEError(errno.ENOENT)
    if 'not a directory' in message or 'use rmdir instead' in message:
        return FUSEError(errno.ENOTDIR if 'not a directory' in message else errno.EISDIR)
    if 'is a directory' in message:
        return FUSEError(errno.EISDIR)
    if 'not empty' in message:
        return FUSEError(errno.ENOTEMPTY)
    if '255-byte limit' in message:
        return FUSEError(errno.ENAMETOOLONG)
    if 'not ASCII' in message or 'own subtree' in message or 'across file and directory types' in message:
        return FUSEError(errno.EINVAL)
    if 'no free UFS' in message or 'exceeds its allocated UFS capacity' in message or 'addressing limit' in message:
        return FUSEError(errno.ENOSPC)
    if 'refusing to' in message:
        return FUSEError(errno.EPERM)
    if isinstance(error, ValueError):
        return FUSEError(errno.EINVAL)
    return FUSEError(errno.EIO)


@dataclass
class UFSVolume:
    image: bytearray
    filesystem: FilesystemCandidate
    sector_count: int
    flush_callback: Callable[[bytearray, Sequence[tuple[int, int]], bool], None] | None = None
    close_callback: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.image, DirtyTrackingBytearray):
            self.image = DirtyTrackingBytearray(self.image)

    @classmethod
    def open_raw_image(cls, image_path: Path, slice_selector: str) -> 'UFSVolume':
        resolved_path = image_path.resolve()
        _, slice_info = inspect_slice_by_selector(resolved_path, slice_selector)
        if slice_info.filesystem != 'ufs':
            raise SystemExit(f'error: slice {slice_selector!r} is not a UFS filesystem')

        slice_image = DirtyTrackingBytearray(read_slice_bytes(resolved_path, slice_info.absolute_start_sector, slice_info.sector_count))
        candidates = detect_ufs(bytes(slice_image))
        if not candidates:
            raise SystemExit(f'error: failed to detect a UFS filesystem inside slice {slice_selector!r}')

        filesystem = candidates[0]
        for candidate in candidates:
            if candidate.start_offset == slice_info.filesystem_offset:
                filesystem = candidate
                break

        handle = resolved_path.open('r+b')
        disk_offset = slice_info.absolute_start_sector * SECTOR_SIZE

        def flush_callback(data: bytearray, dirty_ranges: Sequence[tuple[int, int]], sync: bool) -> None:
            if dirty_ranges:
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
                self.flush_callback(self.image, dirty_ranges, sync)

    def close(self) -> None:
        self.flush(sync=True)
        if self.close_callback is not None:
            self.close_callback()
            self.close_callback = None


@dataclass
class OpenHandle:
    inode: InodeT
    dirty: bool = False
    inode_data: dict[str, int | list[int]] | None = None
    data_blocks: list[int] | None = None
    allocation_sizes: list[int] | None = None
    pointer_blocks: list[int] | None = None


@dataclass
class PendingDeletion:
    directory: bool


class UFSOperations(pyfuse3.Operations):
    supports_dot_lookup = True
    enable_writeback_cache = True

    def __init__(self, volume: UFSVolume, slow_op_ms: float = 0.0, cache_timeout: float = 1.0) -> None:
        super().__init__()
        self._volume = volume
        self._slow_op_ms = slow_op_ms
        self._cache_timeout = cache_timeout
        self._lock = trio.Lock()
        self._inode_path_map: dict[InodeT, str | set[str]] = {InodeT(pyfuse3.ROOT_INODE): '/'}
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

    def _fuse_inode(self, ufs_inode: int) -> InodeT:
        if ufs_inode == UFS_ROOT_INODE:
            return InodeT(pyfuse3.ROOT_INODE)
        return InodeT(ufs_inode)

    def _path_for_inode(self, inode: InodeT) -> str:
        if inode == pyfuse3.ROOT_INODE:
            return '/'
        try:
            value = self._inode_path_map[inode]
        except KeyError as error:
            raise FUSEError(errno.ENOENT) from error
        if isinstance(value, set):
            return sorted(value)[0]
        return value

    def _add_path(self, inode: InodeT, path: str, *, increment_lookup: bool = False) -> None:
        existing = self._inode_path_map.get(inode)
        if existing is None:
            self._inode_path_map[inode] = path
        elif isinstance(existing, set):
            existing.add(path)
        elif existing != path:
            self._inode_path_map[inode] = {existing, path}
        if increment_lookup:
            self._lookup_counts[inode] += 1

    def _remove_path(self, inode: InodeT, path: str) -> None:
        existing = self._inode_path_map.get(inode)
        if existing is None or inode == pyfuse3.ROOT_INODE:
            return
        if isinstance(existing, set):
            existing.discard(path)
            if len(existing) == 1:
                self._inode_path_map[inode] = next(iter(existing))
            elif len(existing) == 0:
                del self._inode_path_map[inode]
        elif existing == path:
            del self._inode_path_map[inode]

    def _rewrite_path_prefix(self, old_prefix: str, new_prefix: str) -> None:
        for inode, value in list(self._inode_path_map.items()):
            if inode == pyfuse3.ROOT_INODE:
                continue
            paths = value if isinstance(value, set) else {value}
            rewritten: set[str] = set()
            changed = False
            for path in paths:
                if path == old_prefix or path.startswith(old_prefix + '/'):
                    suffix = path[len(old_prefix):]
                    rewritten.add(new_prefix + suffix)
                    changed = True
                else:
                    rewritten.add(path)
            if not changed:
                continue
            if len(rewritten) == 1:
                self._inode_path_map[inode] = next(iter(rewritten))
            else:
                self._inode_path_map[inode] = rewritten

    def _resolve_path(self, path: str) -> tuple[int, dict[str, int | list[int]]]:
        resolved = resolve_ufs_path(self._volume.image, self._volume.filesystem, path)
        if resolved is None:
            raise FUSEError(errno.ENOENT)
        return resolved

    def _ufs_inode_number(self, inode: InodeT) -> int:
        if inode == pyfuse3.ROOT_INODE:
            return UFS_ROOT_INODE
        return int(inode)

    def _inode_state(self, inode: InodeT) -> tuple[int, dict[str, int | list[int]]]:
        ufs_inode = self._ufs_inode_number(inode)
        inode_data = read_ufs_inode(self._volume.image, self._volume.filesystem.start_offset, self._volume.filesystem.details, ufs_inode)
        if inode_data is None or int(inode_data['mode']) == 0:
            raise FUSEError(errno.ENOENT)
        return ufs_inode, inode_data

    def _entry_from_inode(self, ufs_inode: int, inode: dict[str, int | list[int]]) -> EntryAttributes:
        entry = EntryAttributes()
        entry.st_ino = self._fuse_inode(ufs_inode)
        entry.generation = 0
        entry.entry_timeout = self._cache_timeout
        entry.attr_timeout = self._cache_timeout
        entry.st_mode = int(inode['mode'])
        entry.st_nlink = int(inode['nlink'])
        entry.st_uid = int(inode['uid'])
        entry.st_gid = int(inode['gid'])
        entry.st_rdev = 0
        entry.st_size = int(inode['size'])
        entry.st_blksize = int(self._volume.filesystem.details['bsize'])
        entry.st_blocks = int(inode['blocks'])
        entry.st_atime_ns = int(inode.get('atime', 0)) * 1_000_000_000
        entry.st_mtime_ns = int(inode.get('mtime', 0)) * 1_000_000_000
        entry.st_ctime_ns = int(inode.get('ctime', 0)) * 1_000_000_000
        return entry

    def _entry_from_path(self, path: str) -> EntryAttributes:
        ufs_inode, inode = self._resolve_path(path)
        return self._entry_from_inode(ufs_inode, inode)

    def _entry_from_fuse_inode(self, inode: InodeT) -> EntryAttributes:
        ufs_inode, inode_data = self._inode_state(inode)
        return self._entry_from_inode(ufs_inode, inode_data)

    def _flush(self, sync: bool = True) -> None:
        self._volume.flush(sync=sync)

    def _clear_dirty_handles(self) -> None:
        for handle in self._open_handles.values():
            handle.dirty = False

    def _invalidate_inode_cache(self, inode: InodeT) -> None:
        for handle in self._open_handles.values():
            if handle.inode != inode:
                continue
            handle.inode_data = None
            handle.data_blocks = None
            handle.allocation_sizes = None
            handle.pointer_blocks = None

    def _write_data(self, handle: OpenHandle, offset: int, data: bytes) -> None:
        if handle.inode_data is None:
            ufs_inode, inode_data = self._inode_state(handle.inode)
            handle.inode_data = dict(inode_data)
        else:
            ufs_inode = self._ufs_inode_number(handle.inode)
        inode_data = handle.inode_data
        if handle.data_blocks is None:
            handle.data_blocks = ufs_inode_data_blocks(self._volume.image, self._volume.filesystem, inode_data)
        if handle.allocation_sizes is None:
            handle.allocation_sizes = ufs_allocation_byte_sizes(self._volume.filesystem.details, int(inode_data['size']))
        result = apply_ufs_inode_write(
            self._volume.image,
            self._volume.filesystem,
            ufs_inode,
            inode_data,
            offset,
            data,
            current_data_blocks=handle.data_blocks,
            current_allocation_sizes=handle.allocation_sizes,
            current_pointer_blocks=handle.pointer_blocks,
        )
        inode_data['size'] = int(result['new_size'])
        data_blocks_state = result.get('data_blocks_state')
        allocation_sizes_state = result.get('allocation_sizes_state')
        pointer_blocks_state = result.get('pointer_blocks_state')
        if isinstance(data_blocks_state, list):
            handle.data_blocks = list(data_blocks_state)
        if isinstance(allocation_sizes_state, list):
            handle.allocation_sizes = list(allocation_sizes_state)
        if isinstance(pointer_blocks_state, list):
            handle.pointer_blocks = list(pointer_blocks_state)
        elif pointer_blocks_state is None and handle.pointer_blocks is None and handle.data_blocks is not None and len(handle.data_blocks) <= 12:
            handle.pointer_blocks = []

    def _truncate(self, inode: InodeT, size: int) -> None:
        ufs_inode, inode_data = self._inode_state(inode)
        apply_ufs_inode_truncate(self._volume.image, self._volume.filesystem, ufs_inode, inode_data, size)
        self._invalidate_inode_cache(inode)

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
        finalize_ufs_unlinked_inode(
            self._volume.image,
            self._volume.filesystem,
            self._ufs_inode_number(inode),
            directory=pending.directory,
        )
        self._flush()
        self._pending_deletions.pop(inode, None)
        self._inode_path_map.pop(inode, None)

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
                parent_path = self._path_for_inode(parent_inode)
                name_text = os.fsdecode(name)
                if name_text == '.':
                    return self._entry_from_fuse_inode(parent_inode)
                if name_text == '..':
                    path = _parent_path(parent_path)
                else:
                    path = _join_path(parent_path, name_text)
                entry = self._entry_from_path(path)
                self._add_path(cast(InodeT, entry.st_ino), path, increment_lookup=True)
                return entry
            except BaseException as error:
                raise _translate_ufs_error(error) from error
            finally:
                self._log_slow_operation('lookup', started_at, f'parent={parent_inode} name={os.fsdecode(name)!r}')

    async def getattr(self, inode: InodeT, ctx: RequestContext | None = None) -> EntryAttributes:
        del ctx
        started_at = time.perf_counter()
        async with self._lock:
            try:
                return self._entry_from_fuse_inode(inode)
            except BaseException as error:
                raise _translate_ufs_error(error) from error
            finally:
                self._log_slow_operation('getattr', started_at, f'inode={inode}')

    async def readlink(self, inode: InodeT, ctx: RequestContext) -> bytes:
        del ctx
        async with self._lock:
            try:
                path = self._path_for_inode(inode)
                _, child_inode, data = read_ufs_path_range(self._volume.image, self._volume.filesystem, path)
                if not ufs_is_symlink(child_inode):
                    raise FUSEError(errno.EINVAL)
                return data
            except BaseException as error:
                raise _translate_ufs_error(error) from error

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
                parent_path = self._path_for_inode(inode)
                _, directory_inode = self._inode_state(inode)
                for record in iter_ufs_inode_directory_records(self._volume.image, self._volume.filesystem, directory_inode):
                    if record.inode == 0:
                        continue
                    next_id = record.offset + 1
                    if next_id <= start_id:
                        continue
                    child_name = record.name
                    child_path = _join_path(parent_path, child_name)
                    child_inode_number = int(record.inode)
                    child_inode = read_ufs_inode(
                        self._volume.image,
                        self._volume.filesystem.start_offset,
                        self._volume.filesystem.details,
                        child_inode_number,
                    )
                    if child_inode is None or int(child_inode['mode']) == 0:
                        continue
                    attr = self._entry_from_inode(child_inode_number, child_inode)
                    if not pyfuse3.readdir_reply(token, os.fsencode(child_name), attr, next_id):
                        break
                    if child_name not in {'.', '..'}:
                        self._add_path(cast(InodeT, attr.st_ino), child_path, increment_lookup=True)
            except BaseException as error:
                raise _translate_ufs_error(error) from error
            finally:
                self._log_slow_operation('readdir', started_at, f'fh={fh} start_id={start_id}')

    async def releasedir(self, fh: FileHandleT) -> None:
        self._directory_handles.pop(fh, None)

    async def open(self, inode: InodeT, flags: int, ctx: RequestContext) -> FileInfo:
        del ctx
        async with self._lock:
            entry = self._entry_from_fuse_inode(inode)
            if stat.S_ISDIR(entry.st_mode):
                raise FUSEError(errno.EISDIR)
            handle = self._new_handle()
            self._open_handles[handle] = OpenHandle(inode=inode)
            info = FileInfo(fh=handle)
            info.keep_cache = True
            return info

    async def read(self, fh: FileHandleT, off: int, size: int) -> bytes:
        async with self._lock:
            try:
                inode = self._open_handles[fh].inode
                _, inode_data = self._inode_state(inode)
                return read_ufs_inode_range(self._volume.image, self._volume.filesystem, inode_data, off, size)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def write(self, fh: FileHandleT, off: int, buf: bytes) -> int:
        async with self._lock:
            try:
                handle = self._open_handles[fh]
                self._write_data(handle, off, buf)
                inode = handle.inode
                now = int(time.time())
                ufs_inode = self._ufs_inode_number(inode)
                write_ufs_inode_times(self._volume.image, self._volume.filesystem, ufs_inode, mtime=now, ctime=now)
                handle.dirty = True
                return len(buf)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def release(self, fh: FileHandleT) -> None:
        handle = self._open_handles.pop(fh, None)
        if handle is not None:
            if handle.dirty:
                self._flush(sync=True)
            self._maybe_finalize_pending_inode(handle.inode)

    async def flush(self, fh: FileHandleT) -> None:
        del fh
        async with self._lock:
            self._flush()
            self._clear_dirty_handles()

    async def fsync(self, fh: FileHandleT, datasync: bool) -> None:
        del fh, datasync
        async with self._lock:
            self._flush()
            self._clear_dirty_handles()

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
                parent_path = self._path_for_inode(parent_inode)
                path = _join_path(parent_path, os.fsdecode(name))
                create_ufs_file(
                    self._volume.image,
                    self._volume.filesystem,
                    path,
                    b'',
                    mode=_mode_with_umask(mode, ctx.umask),
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                )
                self._flush()
                entry = self._entry_from_path(path)
                inode = cast(InodeT, entry.st_ino)
                self._add_path(inode, path, increment_lookup=True)
                handle = self._new_handle()
                self._open_handles[handle] = OpenHandle(inode=inode)
                info = FileInfo(fh=handle)
                info.keep_cache = True
                return info, entry
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def mknod(self, parent_inode: InodeT, name: bytes, mode: int, rdev: int, ctx: RequestContext) -> EntryAttributes:
        del rdev
        if not stat.S_ISREG(mode):
            raise FUSEError(errno.ENOSYS)
        async with self._lock:
            try:
                parent_path = self._path_for_inode(parent_inode)
                path = _join_path(parent_path, os.fsdecode(name))
                create_ufs_file(
                    self._volume.image,
                    self._volume.filesystem,
                    path,
                    b'',
                    mode=_mode_with_umask(mode, ctx.umask),
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                )
                self._flush()
                entry = self._entry_from_path(path)
                self._add_path(cast(InodeT, entry.st_ino), path, increment_lookup=True)
                return entry
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def mkdir(self, parent_inode: InodeT, name: bytes, mode: int, ctx: RequestContext) -> EntryAttributes:
        async with self._lock:
            try:
                parent_path = self._path_for_inode(parent_inode)
                path = _join_path(parent_path, os.fsdecode(name))
                make_ufs_directory(
                    self._volume.image,
                    self._volume.filesystem,
                    path,
                    mode=_mode_with_umask(mode, ctx.umask),
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                )
                self._flush()
                entry = self._entry_from_path(path)
                self._add_path(cast(InodeT, entry.st_ino), path, increment_lookup=True)
                return entry
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def unlink(self, parent_inode: InodeT, name: bytes, ctx: RequestContext) -> None:
        del ctx
        async with self._lock:
            try:
                parent_path = self._path_for_inode(parent_inode)
                path = _join_path(parent_path, os.fsdecode(name))
                entry = self._entry_from_path(path)
                inode = cast(InodeT, entry.st_ino)
                if self._lookup_counts.get(inode, 0) > 0 or self._inode_open_count(inode) > 0:
                    detach_ufs_path(self._volume.image, self._volume.filesystem, path)
                    self._pending_deletions[inode] = PendingDeletion(directory=False)
                else:
                    unlink_ufs_path(self._volume.image, self._volume.filesystem, path)
                    self._inode_path_map.pop(inode, None)
                self._flush()
                self._remove_path(inode, path)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def rmdir(self, parent_inode: InodeT, name: bytes, ctx: RequestContext) -> None:
        del ctx
        async with self._lock:
            try:
                parent_path = self._path_for_inode(parent_inode)
                path = _join_path(parent_path, os.fsdecode(name))
                entry = self._entry_from_path(path)
                inode = cast(InodeT, entry.st_ino)
                if self._lookup_counts.get(inode, 0) > 0 or self._inode_open_count(inode) > 0:
                    detach_ufs_directory(self._volume.image, self._volume.filesystem, path)
                    self._pending_deletions[inode] = PendingDeletion(directory=True)
                else:
                    remove_ufs_directory(self._volume.image, self._volume.filesystem, path)
                    self._inode_path_map.pop(inode, None)
                self._flush()
                self._remove_path(inode, path)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def symlink(self, parent_inode: InodeT, name: bytes, target: bytes, ctx: RequestContext) -> EntryAttributes:
        async with self._lock:
            try:
                parent_path = self._path_for_inode(parent_inode)
                path = _join_path(parent_path, os.fsdecode(name))
                symlink_ufs_path(
                    self._volume.image,
                    self._volume.filesystem,
                    os.fsdecode(target),
                    path,
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                )
                self._flush()
                entry = self._entry_from_path(path)
                self._add_path(cast(InodeT, entry.st_ino), path, increment_lookup=True)
                return entry
            except BaseException as error:
                raise _translate_ufs_error(error) from error

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
                old_parent_path = self._path_for_inode(parent_inode_old)
                new_parent_path = self._path_for_inode(parent_inode_new)
                source_path = _join_path(old_parent_path, os.fsdecode(name_old))
                target_path = _join_path(new_parent_path, os.fsdecode(name_new))
                source_entry = self._entry_from_path(source_path)
                if flags & pyfuse3.RENAME_NOREPLACE:
                    try:
                        self._entry_from_path(target_path)
                    except FUSEError as error:
                        if error.errno != errno.ENOENT:
                            raise
                    else:
                        raise FUSEError(errno.EEXIST)
                overwritten_inode: InodeT | None = None
                try:
                    overwritten_entry = self._entry_from_path(target_path)
                except FUSEError as error:
                    if error.errno != errno.ENOENT:
                        raise
                else:
                    overwritten_inode = cast(InodeT, overwritten_entry.st_ino)
                rename_ufs_path(self._volume.image, self._volume.filesystem, source_path, target_path)
                self._flush()
                source_inode = cast(InodeT, source_entry.st_ino)
                self._remove_path(source_inode, source_path)
                if overwritten_inode is not None:
                    self._remove_path(overwritten_inode, target_path)
                self._add_path(source_inode, target_path)
                self._rewrite_path_prefix(source_path, target_path)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def link(self, inode: InodeT, new_parent_inode: InodeT, new_name: bytes, ctx: RequestContext) -> EntryAttributes:
        del ctx
        async with self._lock:
            try:
                source_path = self._path_for_inode(inode)
                parent_path = self._path_for_inode(new_parent_inode)
                target_path = _join_path(parent_path, os.fsdecode(new_name))
                link_ufs_path(self._volume.image, self._volume.filesystem, source_path, target_path)
                self._flush()
                entry = self._entry_from_path(target_path)
                self._add_path(inode, target_path, increment_lookup=True)
                return entry
            except BaseException as error:
                raise _translate_ufs_error(error) from error

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
                ufs_inode, current_inode = self._inode_state(inode)
                changed = False
                if fields.update_size:
                    self._truncate(inode, int(attr.st_size))
                    changed = True
                if fields.update_mode:
                    new_mode = ufs_file_type(int(current_inode['mode'])) | stat.S_IMODE(int(attr.st_mode))
                    write_ufs_inode_mode(self._volume.image, self._volume.filesystem, ufs_inode, new_mode)
                    changed = True
                if fields.update_uid or fields.update_gid:
                    uid = int(attr.st_uid) if fields.update_uid else int(current_inode['uid'])
                    gid = int(attr.st_gid) if fields.update_gid else int(current_inode['gid'])
                    write_ufs_inode_uid_gid(self._volume.image, self._volume.filesystem, ufs_inode, uid, gid)
                    changed = True

                timestamp_updates: dict[str, int] = {}
                if fields.update_atime:
                    timestamp_updates['atime'] = _seconds_from_ns(int(attr.st_atime_ns))
                if fields.update_mtime:
                    timestamp_updates['mtime'] = _seconds_from_ns(int(attr.st_mtime_ns))
                if fields.update_ctime:
                    timestamp_updates['ctime'] = _seconds_from_ns(int(attr.st_ctime_ns))
                elif changed:
                    timestamp_updates['ctime'] = int(time.time())
                if timestamp_updates:
                    write_ufs_inode_times(self._volume.image, self._volume.filesystem, ufs_inode, **timestamp_updates)
                    changed = True

                if changed:
                    self._flush()
                return self._entry_from_fuse_inode(inode)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

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
            fs = self._volume.filesystem.details
            stats.f_bsize = int(fs['bsize'])
            stats.f_frsize = int(fs['fsize'])
            stats.f_blocks = (self._volume.sector_count * SECTOR_SIZE) // stats.f_frsize
            stats.f_bfree = u32(self._volume.image, self._volume.filesystem.super_offset + UFS_FS_CSTOTAL_NBFREE_OFFSET) * int(fs['frag'])
            stats.f_bavail = stats.f_bfree
            stats.f_files = int(fs['ipg']) * int(fs['ncg'])
            stats.f_ffree = u32(self._volume.image, self._volume.filesystem.super_offset + UFS_FS_CSTOTAL_NIFREE_OFFSET)
            stats.f_favail = stats.f_ffree
            stats.f_namemax = 255
            return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Mount an SVR4 UFS slice from a raw disk image with pyfuse3.')
    parser.add_argument('image', type=Path, help='Path to the raw disk image')
    parser.add_argument('mountpoint', type=Path, help='Where to mount the UFS filesystem')
    parser.add_argument('--slice', default='root', help='Slice selector, by index or VTOC tag name (default: root)')
    parser.add_argument('--debug', action='store_true', default=False, help='Enable Python-side debug logging')
    parser.add_argument('--debug-fuse', action='store_true', default=False, help='Enable libfuse debug logging')
    parser.add_argument('--allow-other', action='store_true', default=False, help='Pass allow_other to FUSE')
    parser.add_argument('--slow-op-ms', type=float, default=0.0, help='Log lookup/getattr/readdir operations slower than this many milliseconds')
    parser.add_argument('--cache-timeout', type=float, default=1.0, help='Kernel entry/attribute cache timeout in seconds (default: 1.0)')
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_args(argv)
    init_logging(options.debug)

    volume = UFSVolume.open_raw_image(options.image, options.slice)
    operations = UFSOperations(volume, slow_op_ms=options.slow_op_ms, cache_timeout=options.cache_timeout)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add(f'fsname=svr4-ufs:{options.image.name}:{options.slice}')
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