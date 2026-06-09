from __future__ import annotations

import argparse
import errno
import faulthandler
import logging
import os
import posixpath
import signal
import stat
import sys
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

from host_tools.disk.inspect import inspect_slice_metadata_by_selector
from host_tools.fs.disk_backed import DiskBackedSlice
from host_tools.fs.common import FilesystemCandidate, SECTOR_SIZE, UFS_ROOT_INODE, u32
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NBFREE_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NIFREE_OFFSET
from host_tools.fs.ufs import iter_ufs_inode_directory_records
from host_tools.fs.ufs import read_ufs_inode_range
from host_tools.fs.ufs import apply_ufs_inode_truncate
from host_tools.fs.ufs import apply_ufs_inode_write
from host_tools.fs.ufs import apply_ufs_inode_replacement
from host_tools.fs.ufs import clear_ufs_filesystem_runtime_caches
from host_tools.fs.ufs import clear_ufs_runtime_caches
from host_tools.fs.ufs import add_ufs_directory_entry
from host_tools.fs.ufs import create_ufs_file_in_parent
from host_tools.fs.ufs import detach_ufs_directory
from host_tools.fs.ufs import detach_ufs_path
from host_tools.fs.ufs import detect_ufs_at_start
from host_tools.fs.ufs import finalize_ufs_unlinked_inode
from host_tools.fs.ufs import lookup_ufs_directory_entry
from host_tools.fs.ufs import make_ufs_directory_in_parent
from host_tools.fs.ufs import ensure_ufs_metadata_normalized
from host_tools.fs.ufs import reconcile_ufs_block_bitmap_from_inodes
from host_tools.fs.ufs import read_ufs_inode
from host_tools.fs.ufs import refresh_ufs_summary_layout
from host_tools.fs.ufs import UFS_FS_CLEAN_OFFSET
from host_tools.fs.ufs import UFS_FS_FMOD_OFFSET
from host_tools.fs.ufs import rename_ufs_in_parent
from host_tools.fs.ufs import ufs_allocation_byte_sizes
from host_tools.fs.ufs import ufs_inode_data_blocks
from host_tools.fs.ufs import remove_ufs_directory
from host_tools.fs.ufs import rename_ufs_path
from host_tools.fs.ufs import resolve_ufs_path
from host_tools.fs.ufs import ufs_file_type
from host_tools.fs.ufs import ufs_is_directory
from host_tools.fs.ufs import ufs_is_symlink
from host_tools.fs.ufs import ufs_inode_pointer_blocks
from host_tools.fs.ufs import unlink_ufs_path
from host_tools.fs.ufs import write_ufs_inode_mode
from host_tools.fs.ufs import write_ufs_inode_nlink
from host_tools.fs.ufs import write_ufs_inode_times
from host_tools.fs.ufs import write_ufs_inode_uid_gid


log = logging.getLogger(__name__)
_DIRTY_RANGE_COALESCE_THRESHOLD = 4096


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
        self._dirty_ranges.append((bounded_start, bounded_end))
        if len(self._dirty_ranges) >= _DIRTY_RANGE_COALESCE_THRESHOLD:
            self._dirty_ranges = self._coalesce_dirty_ranges(self._dirty_ranges)

    @staticmethod
    def _coalesce_dirty_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not ranges:
            return []
        ordered = sorted(ranges)
        merged = [ordered[0]]
        for start, end in ordered[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def consume_dirty_ranges(self) -> list[tuple[int, int]]:
        ranges = self._coalesce_dirty_ranges(self._dirty_ranges)
        self._dirty_ranges.clear()
        return ranges

    def dirty_ranges(self) -> list[tuple[int, int]]:
        self._dirty_ranges = self._coalesce_dirty_ranges(self._dirty_ranges)
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
    image: bytearray | DiskBackedSlice
    filesystem: FilesystemCandidate
    sector_count: int
    flush_callback: Callable[[bytearray | DiskBackedSlice, Sequence[tuple[int, int]], bool], None] | None = None
    close_callback: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.image, DirtyTrackingBytearray) and not isinstance(self.image, DiskBackedSlice):
            self.image = DirtyTrackingBytearray(self.image)

    @classmethod
    def open_raw_image(cls, image_path: Path, slice_selector: str) -> 'UFSVolume':
        resolved_path = image_path.resolve()
        _, slice_info = inspect_slice_metadata_by_selector(resolved_path, slice_selector)
        slice_image = DiskBackedSlice(
            resolved_path,
            slice_info.absolute_start_sector * SECTOR_SIZE,
            slice_info.sector_count * SECTOR_SIZE,
        )
        filesystem = detect_ufs_at_start(slice_image)
        if filesystem is None:
            slice_image.close()
            raise SystemExit(f'error: failed to detect a UFS filesystem inside slice {slice_selector!r}')

        def flush_callback(data: bytearray | DiskBackedSlice, dirty_ranges: Sequence[tuple[int, int]], sync: bool) -> None:
            del dirty_ranges
            if hasattr(data, 'flush'):
                data.flush(sync=sync)  # type: ignore[call-arg]

        return cls(
            image=slice_image,
            filesystem=filesystem,
            sector_count=slice_info.sector_count,
            flush_callback=flush_callback,
            close_callback=slice_image.close,
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
        clear_ufs_filesystem_runtime_caches(self.filesystem)
        clear_ufs_runtime_caches(self.image)


@dataclass
class OpenHandle:
    inode: InodeT
    dirty: bool = False
    inode_data: dict[str, int | list[int]] | None = None
    data_blocks: list[int] | None = None
    allocation_sizes: list[int] | None = None
    pointer_blocks: list[int] | None = None


@dataclass
class DirectoryEntryState:
    next_id: int
    name: str
    inode: int
    attr: EntryAttributes


@dataclass
class DirectoryHandle:
    inode: InodeT
    entries: list[DirectoryEntryState] | None = None


@dataclass
class PendingDeletion:
    directory: bool


class UFSOperations(pyfuse3.Operations):
    supports_dot_lookup = True
    enable_writeback_cache = True

    def __init__(self, volume: UFSVolume, slow_op_ms: float = 0.0, cache_timeout: float = 1.0, bulk_populate: bool = False, reconcile_blocks: bool = False) -> None:
        super().__init__()
        self._volume = volume
        self._slow_op_ms = slow_op_ms
        self._cache_timeout = cache_timeout
        self._reconcile_blocks = reconcile_blocks
        # In bulk-populate mode, per-operation flushes write through to the OS
        # page cache (pwrite) but skip the fsync barrier; durability is provided
        # by the single fsync performed when the volume is closed at unmount.
        # This avoids one fsync per file, which otherwise makes populating an
        # image with thousands of files latency-bound on disk barriers. The
        # default (interactive) mode keeps per-operation fsync semantics.
        self._sync_per_op = not bulk_populate
        self._lock = trio.Lock()
        self._inode_path_map: dict[InodeT, str | set[str]] = {InodeT(pyfuse3.ROOT_INODE): '/'}
        self._lookup_counts: defaultdict[InodeT, int] = defaultdict(int)
        self._directory_entry_cache: dict[tuple[int, str], tuple[int, dict[str, int | list[int]]]] = {}
        self._directory_name_cache: dict[int, set[str]] = {}
        self._open_handles: dict[FileHandleT, OpenHandle] = {}
        self._directory_handles: dict[FileHandleT, DirectoryHandle] = {}
        self._pending_deletions: dict[InodeT, PendingDeletion] = {}
        self._next_handle = 1
        # Per-operation full cylinder-group summary recomputation is O(filesystem
        # size) and dominates bulk population of a large slice. The low-level
        # allocators already keep the free block/inode/dir counts coherent
        # incrementally, so we skip the expensive rotational-layout rebuild during
        # the mount and reconcile it once when the filesystem is finalized.
        self._summary_dirty = False

    def reconcile_on_mount(self) -> None:
        """Light, fsck-style reconciliation run once before the mount serves I/O.

        A guest VM killed without unmounting leaves the on-disk UFS marked dirty
        and its summary accounting (per-cylinder-group and superblock free
        block/inode/dir counts) potentially out of sync with the allocation
        bitmaps. Rebuilding those counts from the bitmaps up front means the
        allocators start from a coherent free-count view, so a reused dirty image
        does not slowly drift into ENOSPC or bogus statfs numbers. This is O(ncg)
        cylinder-group reads, not an inode tree walk, so it stays cheap even on a
        large slice; the expensive tree-level reconciliation is handled for free
        by the rsync --delete pass that follows.

        Per-inode link-count and orphan repair is deliberately *not* done here:
        rsync rewrites the tree to match the sysroot, and the tolerant free paths
        (see warn_inconsistent_ufs_metadata) absorb any stale bitmap state without
        aborting the mount.
        """
        image = self._volume.image
        filesystem = self._volume.filesystem
        super_offset = filesystem.super_offset
        clean = image[super_offset + UFS_FS_CLEAN_OFFSET]
        fmod = image[super_offset + UFS_FS_FMOD_OFFSET]
        unclean = clean != 1 or fmod != 0
        if unclean:
            logging.getLogger(__name__).warning(
                'ufs-fuse: %s was not cleanly unmounted (fs_clean=%d, fs_fmod=%d); '
                'reconciling free-space accounting before population',
                getattr(self._volume, 'slice_selector', 'root'),
                clean,
                fmod,
            )
        # Recompute regardless of the flag: detection of an unclean shutdown is
        # best-effort (an older SVR4 kernel may not update fs_clean the way we
        # expect), and the recompute is cheap and idempotent on a clean image.
        # When reusing a potentially dirty image, repair cross-linked/stale
        # inodes (a block marked free in the bitmap while a live inode still
        # references it) before recomputing accounting, so the rebuilt summary
        # counts reflect the corrected bitmap. This walks the inode table once
        # and is gated to the reused-image path; a fresh format never needs it.
        if self._reconcile_blocks:
            reconcile_ufs_block_bitmap_from_inodes(image, filesystem)
        # force=True rebuilds the summary counts from the bitmaps even if the
        # runtime state was already marked normalized (e.g. by the formatter),
        # and leaves it marked normalized so the first allocator call later does
        # not pay for a second full-filesystem recompute.
        ensure_ufs_metadata_normalized(image, filesystem, force=True)
        # Mark the filesystem clean now that its accounting is coherent. The
        # population pass that follows keeps it coherent incrementally, and the
        # guest's own fsck/mount will re-evaluate it on next boot anyway.
        image[super_offset + UFS_FS_CLEAN_OFFSET] = 1
        image[super_offset + UFS_FS_FMOD_OFFSET] = 0
        self._flush(sync=True)

    def _mark_summary_dirty(self) -> None:
        self._summary_dirty = True

    def finalize_summary(self) -> None:
        if not self._summary_dirty:
            return
        refresh_ufs_summary_layout(self._volume.image, self._volume.filesystem)
        self._summary_dirty = False
        self._flush(sync=True)

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

    def _cache_directory_entry(self, parent_inode: int, name: str, child_inode: int, inode_data: dict[str, int | list[int]]) -> None:
        if name not in {'.', '..'}:
            self._directory_entry_cache[(parent_inode, name)] = (child_inode, dict(inode_data))

    def _invalidate_directory_cache(self, parent_inode: int | None = None, name: str | None = None) -> None:
        if parent_inode is None:
            self._directory_entry_cache.clear()
            self._directory_name_cache.clear()
            return
        if name is not None:
            self._directory_entry_cache.pop((parent_inode, name), None)
            cached_names = self._directory_name_cache.get(parent_inode)
            if cached_names is not None:
                cached_names.discard(name)
            return
        stale_keys = [cache_key for cache_key in self._directory_entry_cache if cache_key[0] == parent_inode]
        for cache_key in stale_keys:
            del self._directory_entry_cache[cache_key]
        self._directory_name_cache.pop(parent_inode, None)

    def _directory_names(self, parent_inode: int, parent_inode_data: dict[str, int | list[int]]) -> set[str]:
        names = self._directory_name_cache.get(parent_inode)
        if names is not None:
            return names
        names: set[str] = set()
        for record in iter_ufs_inode_directory_records(self._volume.image, self._volume.filesystem, parent_inode_data):
            if record.inode == 0:
                continue
            names.add(record.name)
            if record.name in {'.', '..'}:
                continue
            child_inode_number = int(record.inode)
            child_inode = read_ufs_inode(
                self._volume.image,
                self._volume.filesystem.start_offset,
                self._volume.filesystem.details,
                child_inode_number,
            )
            if child_inode is not None and int(child_inode['mode']) != 0:
                self._cache_directory_entry(parent_inode, record.name, child_inode_number, child_inode)
        self._directory_name_cache[parent_inode] = names
        return names

    def _remember_directory_name(self, parent_inode: int, name: str) -> None:
        names = self._directory_name_cache.get(parent_inode)
        if names is not None:
            names.add(name)

    def _lookup_child(self, parent_inode: InodeT, name: str) -> tuple[int, dict[str, int | list[int]]]:
        parent_ufs_inode, parent_inode_data = self._inode_state(parent_inode)
        if name == '.':
            return parent_ufs_inode, parent_inode_data
        if name == '..':
            parent_path = self._path_for_inode(parent_inode)
            return self._resolve_path(_parent_path(parent_path))

        cache_key = (parent_ufs_inode, name)
        cached = self._directory_entry_cache.get(cache_key)
        if cached is not None:
            child_inode_number, _cached_inode = cached
            fresh_inode = read_ufs_inode(
                self._volume.image,
                self._volume.filesystem.start_offset,
                self._volume.filesystem.details,
                child_inode_number,
            )
            if fresh_inode is not None and int(fresh_inode['mode']) != 0:
                return child_inode_number, fresh_inode
            self._directory_entry_cache.pop(cache_key, None)

        if name not in self._directory_names(parent_ufs_inode, parent_inode_data):
            raise FUSEError(errno.ENOENT)

        cached = self._directory_entry_cache.get(cache_key)
        if cached is not None:
            child_inode_number, cached_inode = cached
            return child_inode_number, dict(cached_inode)

        resolved = lookup_ufs_directory_entry(self._volume.image, self._volume.filesystem, parent_inode_data, name)
        if resolved is None:
            raise FUSEError(errno.ENOENT)
        child_inode_number, child_inode = resolved
        self._cache_directory_entry(parent_ufs_inode, name, child_inode_number, child_inode)
        self._remember_directory_name(parent_ufs_inode, name)
        return child_inode_number, child_inode

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

    def _discard_stale_inode_state(self, ufs_inode: int) -> None:
        # A newly allocated UFS inode number may collide with the FUSE inode key of
        # a previously unlinked inode whose deferred deletion is still pending (the
        # kernel has not yet sent the matching forget). Because we key FUSE inodes
        # 1:1 on the UFS inode number, the allocator can hand the same number back
        # out before that forget arrives. The pending deletion now refers to the
        # *old* file, which no longer exists; finalizing it later would free the
        # bitmap bit that the new file legitimately owns (a double free). Drop the
        # stale bookkeeping so the reused inode starts from a clean slate.
        fuse_inode = self._fuse_inode(ufs_inode)
        self._pending_deletions.pop(fuse_inode, None)
        self._lookup_counts.pop(fuse_inode, None)
        self._inode_path_map.pop(fuse_inode, None)

    def _inode_from_creation_result(self, result: dict[str, object]) -> tuple[int, dict[str, int | list[int]]]:
        inode_number = int(result['inode'])
        self._discard_stale_inode_state(inode_number)
        inode_data = result.get('inode_data')
        if isinstance(inode_data, dict):
            return inode_number, cast(dict[str, int | list[int]], inode_data)
        reread_inode = read_ufs_inode(
            self._volume.image,
            self._volume.filesystem.start_offset,
            self._volume.filesystem.details,
            inode_number,
        )
        if reread_inode is None:
            raise FUSEError(errno.EIO)
        return inode_number, reread_inode

    def _load_directory_entries(self, directory_handle: DirectoryHandle) -> list[DirectoryEntryState]:
        if directory_handle.entries is not None:
            return directory_handle.entries

        inode = directory_handle.inode
        _, directory_inode = self._inode_state(inode)
        entries: list[DirectoryEntryState] = []
        for record in iter_ufs_inode_directory_records(self._volume.image, self._volume.filesystem, directory_inode):
            if record.inode == 0:
                continue
            child_inode_number = int(record.inode)
            child_inode = read_ufs_inode(
                self._volume.image,
                self._volume.filesystem.start_offset,
                self._volume.filesystem.details,
                child_inode_number,
            )
            if child_inode is None or int(child_inode['mode']) == 0:
                continue
            entries.append(
                DirectoryEntryState(
                    next_id=record.offset + 1,
                    name=record.name,
                    inode=child_inode_number,
                    attr=self._entry_from_inode(child_inode_number, child_inode),
                )
            )
            if record.name not in {'.', '..'}:
                self._cache_directory_entry(self._ufs_inode_number(inode), record.name, child_inode_number, child_inode)
                self._remember_directory_name(self._ufs_inode_number(inode), record.name)
        directory_handle.entries = entries
        return entries

    def _flush(self, sync: bool | None = None) -> None:
        # sync=None means "use the configured per-operation policy": always sync
        # in interactive mode, defer in bulk-populate mode. Callers that need a
        # hard durability point (the fsync()/flush() FUSE callbacks) pass
        # sync=True explicitly and always force a disk sync.
        if sync is None:
            sync = self._sync_per_op
        self._volume.flush(sync=sync)

    def _clear_dirty_handles(self) -> None:
        for handle in self._open_handles.values():
            handle.dirty = False

    def _invalidate_inode_cache(self, inode: InodeT, *, except_handle: FileHandleT | None = None) -> None:
        except_open_handle = self._open_handles.get(except_handle)
        for handle in self._open_handles.values():
            if handle is except_open_handle:
                continue
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

    def _truncate(
        self,
        inode: InodeT,
        ufs_inode: int,
        inode_data: dict[str, int | list[int]],
        size: int,
        fh: FileHandleT | None = None,
    ) -> dict[str, int | str | list[int] | None]:
        result = apply_ufs_inode_truncate(self._volume.image, self._volume.filesystem, ufs_inode, inode_data, size)
        handle = self._open_handles.get(fh)
        if handle is not None and handle.inode == inode:
            handle.inode_data = dict(inode_data)
            handle.inode_data['size'] = size
            blocks_state = result.get('blocks_state')
            if blocks_state is not None:
                handle.inode_data['blocks'] = int(blocks_state)
            data_blocks_state = result.get('data_blocks_state')
            allocation_sizes_state = result.get('allocation_sizes_state')
            pointer_blocks_state = result.get('pointer_blocks_state')
            handle.data_blocks = list(data_blocks_state) if isinstance(data_blocks_state, list) else None
            handle.allocation_sizes = list(allocation_sizes_state) if isinstance(allocation_sizes_state, list) else None
            handle.pointer_blocks = list(pointer_blocks_state) if isinstance(pointer_blocks_state, list) else None
        self._invalidate_inode_cache(inode, except_handle=fh)
        return result

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
        # Claim the pending deletion before doing any work so that a concurrent
        # forget/release for the same inode cannot also pass the checks above and
        # double-free the inode. finalize_ufs_unlinked_inode is destructive and
        # must run exactly once per inode.
        self._pending_deletions.pop(inode, None)
        finalize_ufs_unlinked_inode(
            self._volume.image,
            self._volume.filesystem,
            self._ufs_inode_number(inode),
            directory=pending.directory,
        )
        self._flush()
        self._inode_path_map.pop(inode, None)

    async def forget(self, inode_list: Sequence[tuple[InodeT, int]]) -> None:
        async with self._lock:
            for inode, nlookup in inode_list:
                if self._lookup_counts[inode] > nlookup:
                    self._lookup_counts[inode] -= nlookup
                else:
                    self._lookup_counts.pop(inode, None)
                # forget is a kernel notification with no reply channel, so an
                # exception here cannot be turned into an errno: it would unwind
                # out of the pyfuse3 session loop and tear down the entire mount
                # (the "Transport endpoint is not connected" cascade seen when a
                # dirty reused image trips deferred-deletion bookkeeping). Keep
                # the mount alive and let the rsync pass reconcile the tree.
                try:
                    self._maybe_finalize_pending_inode(inode)
                except BaseException:
                    logging.getLogger(__name__).warning(
                        'ufs-fuse: deferred deletion of inode %s failed; mount kept alive',
                        inode,
                        exc_info=True,
                    )

    async def lookup(self, parent_inode: InodeT, name: bytes, ctx: RequestContext) -> EntryAttributes:
        del ctx
        started_at = time.perf_counter()
        async with self._lock:
            try:
                name_text = os.fsdecode(name)
                child_inode_number, child_inode = self._lookup_child(parent_inode, name_text)
                entry = self._entry_from_inode(child_inode_number, child_inode)
                parent_path = self._path_for_inode(parent_inode)
                path = _parent_path(parent_path) if name_text == '..' else _join_path(parent_path, name_text)
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
                _, inode_data = self._inode_state(inode)
                if not ufs_is_symlink(inode_data):
                    raise FUSEError(errno.EINVAL)
                return read_ufs_inode_range(
                    self._volume.image,
                    self._volume.filesystem,
                    inode_data,
                    0,
                    int(inode_data['size']),
                )
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def opendir(self, inode: InodeT, ctx: RequestContext) -> FileHandleT:
        del ctx
        async with self._lock:
            entry = self._entry_from_fuse_inode(inode)
            if not stat.S_ISDIR(entry.st_mode):
                raise FUSEError(errno.ENOTDIR)
            handle = self._new_handle()
            self._directory_handles[handle] = DirectoryHandle(inode=inode)
            return handle

    async def readdir(self, fh: FileHandleT, start_id: int, token: ReaddirToken) -> None:
        started_at = time.perf_counter()
        async with self._lock:
            try:
                directory_handle = self._directory_handles[fh]
                inode = directory_handle.inode
                parent_path = self._path_for_inode(inode)
                for entry_state in self._load_directory_entries(directory_handle):
                    if entry_state.next_id <= start_id:
                        continue
                    child_name = entry_state.name
                    child_path = _join_path(parent_path, child_name)
                    if not pyfuse3.readdir_reply(token, os.fsencode(child_name), entry_state.attr, entry_state.next_id):
                        break
                    if child_name not in {'.', '..'}:
                        self._add_path(cast(InodeT, entry_state.attr.st_ino), child_path, increment_lookup=True)
            except BaseException as error:
                raise _translate_ufs_error(error) from error
            finally:
                self._log_slow_operation('readdir', started_at, f'fh={fh} start_id={start_id}')

    async def releasedir(self, fh: FileHandleT) -> None:
        async with self._lock:
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
                self._mark_summary_dirty()
                return len(buf)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def release(self, fh: FileHandleT) -> None:
        async with self._lock:
            handle = self._open_handles.pop(fh, None)
            if handle is not None:
                if handle.dirty:
                    # Honor the per-operation sync policy: sync in interactive mode
                    # (preserving close-time durability), defer in bulk-populate mode.
                    self._flush()
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
                entry_name = os.fsdecode(name)
                path = _join_path(parent_path, entry_name)
                parent_ufs_inode, parent_inode_data = self._inode_state(parent_inode)
                if entry_name in self._directory_names(parent_ufs_inode, parent_inode_data):
                    raise FUSEError(errno.EEXIST)
                result = create_ufs_file_in_parent(
                    self._volume.image,
                    self._volume.filesystem,
                    parent_ufs_inode,
                    parent_inode_data,
                    entry_name,
                    b'',
                    target_path=path,
                    mode=_mode_with_umask(mode, ctx.umask),
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                    recompute_summary=False,
                    check_existing=False,
                    append_directory_entry=True,
                )
                self._mark_summary_dirty()
                self._invalidate_directory_cache(parent_ufs_inode, entry_name)
                self._flush()
                new_inode_number, new_inode = self._inode_from_creation_result(cast(dict[str, object], result))
                entry = self._entry_from_inode(new_inode_number, new_inode)
                inode = cast(InodeT, entry.st_ino)
                self._add_path(inode, path, increment_lookup=True)
                self._cache_directory_entry(parent_ufs_inode, entry_name, new_inode_number, new_inode)
                self._remember_directory_name(parent_ufs_inode, entry_name)
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
                entry_name = os.fsdecode(name)
                path = _join_path(parent_path, entry_name)
                parent_ufs_inode, parent_inode_data = self._inode_state(parent_inode)
                if entry_name in self._directory_names(parent_ufs_inode, parent_inode_data):
                    raise FUSEError(errno.EEXIST)
                result = create_ufs_file_in_parent(
                    self._volume.image,
                    self._volume.filesystem,
                    parent_ufs_inode,
                    parent_inode_data,
                    entry_name,
                    b'',
                    target_path=path,
                    mode=_mode_with_umask(mode, ctx.umask),
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                    recompute_summary=False,
                    check_existing=False,
                    append_directory_entry=True,
                )
                self._mark_summary_dirty()
                self._invalidate_directory_cache(parent_ufs_inode, entry_name)
                self._flush()
                new_inode_number, new_inode = self._inode_from_creation_result(cast(dict[str, object], result))
                entry = self._entry_from_inode(new_inode_number, new_inode)
                self._add_path(cast(InodeT, entry.st_ino), path, increment_lookup=True)
                self._cache_directory_entry(parent_ufs_inode, entry_name, new_inode_number, new_inode)
                self._remember_directory_name(parent_ufs_inode, entry_name)
                return entry
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def mkdir(self, parent_inode: InodeT, name: bytes, mode: int, ctx: RequestContext) -> EntryAttributes:
        async with self._lock:
            try:
                parent_path = self._path_for_inode(parent_inode)
                entry_name = os.fsdecode(name)
                path = _join_path(parent_path, entry_name)
                parent_ufs_inode, parent_inode_data = self._inode_state(parent_inode)
                if entry_name in self._directory_names(parent_ufs_inode, parent_inode_data):
                    raise FUSEError(errno.EEXIST)
                result = make_ufs_directory_in_parent(
                    self._volume.image,
                    self._volume.filesystem,
                    parent_ufs_inode,
                    parent_inode_data,
                    entry_name,
                    target_path=path,
                    mode=_mode_with_umask(mode, ctx.umask),
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                    recompute_summary=False,
                    check_existing=False,
                    append_directory_entry=True,
                )
                self._mark_summary_dirty()
                self._invalidate_directory_cache(parent_ufs_inode, entry_name)
                self._flush()
                new_inode_number, new_inode = self._inode_from_creation_result(cast(dict[str, object], result))
                entry = self._entry_from_inode(new_inode_number, new_inode)
                self._add_path(cast(InodeT, entry.st_ino), path, increment_lookup=True)
                self._cache_directory_entry(parent_ufs_inode, entry_name, new_inode_number, new_inode)
                self._remember_directory_name(parent_ufs_inode, entry_name)
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
                parent_ufs_inode = self._ufs_inode_number(parent_inode)
                if self._lookup_counts.get(inode, 0) > 0 or self._inode_open_count(inode) > 0:
                    detach_ufs_path(self._volume.image, self._volume.filesystem, path)
                    self._pending_deletions[inode] = PendingDeletion(directory=False)
                else:
                    unlink_ufs_path(self._volume.image, self._volume.filesystem, path)
                    self._inode_path_map.pop(inode, None)
                self._mark_summary_dirty()
                self._invalidate_directory_cache(parent_ufs_inode, os.fsdecode(name))
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
                parent_ufs_inode = self._ufs_inode_number(parent_inode)
                if self._lookup_counts.get(inode, 0) > 0 or self._inode_open_count(inode) > 0:
                    detach_ufs_directory(self._volume.image, self._volume.filesystem, path)
                    self._pending_deletions[inode] = PendingDeletion(directory=True)
                else:
                    remove_ufs_directory(self._volume.image, self._volume.filesystem, path)
                    self._inode_path_map.pop(inode, None)
                self._mark_summary_dirty()
                self._invalidate_directory_cache(parent_ufs_inode, os.fsdecode(name))
                self._flush()
                self._remove_path(inode, path)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def symlink(self, parent_inode: InodeT, name: bytes, target: bytes, ctx: RequestContext) -> EntryAttributes:
        async with self._lock:
            try:
                parent_path = self._path_for_inode(parent_inode)
                entry_name = os.fsdecode(name)
                path = _join_path(parent_path, entry_name)
                parent_ufs_inode, parent_inode_data = self._inode_state(parent_inode)
                if entry_name in self._directory_names(parent_ufs_inode, parent_inode_data):
                    raise FUSEError(errno.EEXIST)
                result = create_ufs_file_in_parent(
                    self._volume.image,
                    self._volume.filesystem,
                    parent_ufs_inode,
                    parent_inode_data,
                    entry_name,
                    os.fsdecode(target).encode('ascii'),
                    target_path=path,
                    mode=stat.S_IFLNK | 0o777,
                    uid=ctx.uid,
                    gid=ctx.gid,
                    timestamp=int(time.time()),
                    recompute_summary=False,
                    check_existing=False,
                    append_directory_entry=True,
                )
                self._mark_summary_dirty()
                self._invalidate_directory_cache(parent_ufs_inode, entry_name)
                self._flush()
                new_inode_number, new_inode = self._inode_from_creation_result(cast(dict[str, object], result))
                entry = self._entry_from_inode(new_inode_number, new_inode)
                self._add_path(cast(InodeT, entry.st_ino), path, increment_lookup=True)
                self._cache_directory_entry(parent_ufs_inode, entry_name, new_inode_number, new_inode)
                self._remember_directory_name(parent_ufs_inode, entry_name)
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
                source_name = os.fsdecode(name_old)
                target_name = os.fsdecode(name_new)
                source_path = _join_path(old_parent_path, source_name)
                target_path = _join_path(new_parent_path, target_name)
                source_inode_number, source_inode = self._lookup_child(parent_inode_old, source_name)
                source_entry = self._entry_from_inode(source_inode_number, source_inode)
                target_exists = False
                if flags & pyfuse3.RENAME_NOREPLACE:
                    try:
                        self._lookup_child(parent_inode_new, target_name)
                    except FUSEError as error:
                        if error.errno != errno.ENOENT:
                            raise
                    else:
                        raise FUSEError(errno.EEXIST)
                overwritten_inode: InodeT | None = None
                try:
                    target_inode_number, target_inode = self._lookup_child(parent_inode_new, target_name)
                except FUSEError as error:
                    if error.errno != errno.ENOENT:
                        raise
                else:
                    target_exists = True
                    overwritten_inode = cast(InodeT, target_inode_number)
                    del target_inode
                if target_exists:
                    rename_ufs_path(self._volume.image, self._volume.filesystem, source_path, target_path)
                else:
                    old_parent_ufs_inode, old_parent_inode_data = self._inode_state(parent_inode_old)
                    new_parent_ufs_inode, new_parent_inode_data = self._inode_state(parent_inode_new)
                    rename_ufs_in_parent(
                        self._volume.image,
                        self._volume.filesystem,
                        old_parent_ufs_inode,
                        old_parent_inode_data,
                        source_name,
                        source_inode_number,
                        source_inode,
                        new_parent_ufs_inode,
                        new_parent_inode_data,
                        target_name,
                        check_existing=False,
                    )
                self._mark_summary_dirty()
                self._invalidate_directory_cache(self._ufs_inode_number(parent_inode_old), source_name)
                self._invalidate_directory_cache(self._ufs_inode_number(parent_inode_new), target_name)
                if stat.S_ISDIR(source_entry.st_mode):
                    self._invalidate_directory_cache()
                self._flush()
                source_fuse_inode = cast(InodeT, source_entry.st_ino)
                self._remove_path(source_fuse_inode, source_path)
                if overwritten_inode is not None:
                    self._remove_path(overwritten_inode, target_path)
                    # rename_ufs_path freed the overwritten target inode in place
                    # (via unlink_ufs_path). Any deferred deletion still queued for
                    # that inode now refers to storage the allocator may hand back
                    # out; clear it so a later forget cannot double-free it.
                    self._pending_deletions.pop(overwritten_inode, None)
                    self._lookup_counts.pop(overwritten_inode, None)
                self._add_path(source_fuse_inode, target_path)
                self._rewrite_path_prefix(source_path, target_path)
                self._remember_directory_name(self._ufs_inode_number(parent_inode_new), target_name)
            except BaseException as error:
                raise _translate_ufs_error(error) from error

    async def link(self, inode: InodeT, new_parent_inode: InodeT, new_name: bytes, ctx: RequestContext) -> EntryAttributes:
        del ctx
        async with self._lock:
            try:
                parent_path = self._path_for_inode(new_parent_inode)
                target_name = os.fsdecode(new_name)
                target_path = _join_path(parent_path, target_name)
                source_ufs_inode, source_inode = self._inode_state(inode)
                if ufs_is_directory(source_inode):
                    raise FUSEError(errno.EPERM)
                parent_ufs_inode, parent_inode = self._inode_state(new_parent_inode)
                if target_name in self._directory_names(parent_ufs_inode, parent_inode):
                    raise FUSEError(errno.EEXIST)
                add_ufs_directory_entry(
                    self._volume.image,
                    self._volume.filesystem,
                    parent_ufs_inode,
                    parent_inode,
                    target_name,
                    source_ufs_inode,
                    append_only=True,
                )
                write_ufs_inode_nlink(
                    self._volume.image,
                    self._volume.filesystem,
                    source_ufs_inode,
                    int(source_inode['nlink']) + 1,
                )
                self._flush()
                linked_inode = dict(source_inode)
                linked_inode['nlink'] = int(source_inode['nlink']) + 1
                entry = self._entry_from_inode(source_ufs_inode, linked_inode)
                self._add_path(inode, target_path, increment_lookup=True)
                self._cache_directory_entry(parent_ufs_inode, target_name, source_ufs_inode, linked_inode)
                self._remember_directory_name(parent_ufs_inode, target_name)
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
        del ctx
        async with self._lock:
            try:
                ufs_inode, current_inode = self._inode_state(inode)
                changed = False
                if fields.update_size:
                    new_size = int(attr.st_size)
                    if new_size != int(current_inode['size']):
                        truncate_result = self._truncate(inode, ufs_inode, current_inode, new_size, fh)
                        current_inode['size'] = new_size
                        blocks_state = truncate_result.get('blocks_state')
                        if blocks_state is not None:
                            current_inode['blocks'] = int(blocks_state)
                        changed = True
                        self._mark_summary_dirty()
                if fields.update_mode:
                    new_mode = ufs_file_type(int(current_inode['mode'])) | stat.S_IMODE(int(attr.st_mode))
                    if new_mode != int(current_inode['mode']):
                        write_ufs_inode_mode(self._volume.image, self._volume.filesystem, ufs_inode, new_mode)
                        current_inode['mode'] = new_mode
                        changed = True
                if fields.update_uid or fields.update_gid:
                    uid = int(attr.st_uid) if fields.update_uid else int(current_inode['uid'])
                    gid = int(attr.st_gid) if fields.update_gid else int(current_inode['gid'])
                    if uid != int(current_inode['uid']) or gid != int(current_inode['gid']):
                        write_ufs_inode_uid_gid(self._volume.image, self._volume.filesystem, ufs_inode, uid, gid)
                        current_inode['uid'] = uid
                        current_inode['gid'] = gid
                        changed = True

                timestamp_updates: dict[str, int] = {}
                if fields.update_atime:
                    new_atime = _seconds_from_ns(int(attr.st_atime_ns))
                    if new_atime != int(current_inode['atime']):
                        timestamp_updates['atime'] = new_atime
                if fields.update_mtime:
                    new_mtime = _seconds_from_ns(int(attr.st_mtime_ns))
                    if new_mtime != int(current_inode['mtime']):
                        timestamp_updates['mtime'] = new_mtime
                if fields.update_ctime:
                    new_ctime = _seconds_from_ns(int(attr.st_ctime_ns))
                    if new_ctime != int(current_inode['ctime']):
                        timestamp_updates['ctime'] = new_ctime
                elif changed:
                    timestamp_updates['ctime'] = int(time.time())
                if timestamp_updates:
                    write_ufs_inode_times(self._volume.image, self._volume.filesystem, ufs_inode, **timestamp_updates)
                    current_inode.update(timestamp_updates)
                    changed = True

                if changed:
                    self._flush()
                return self._entry_from_inode(ufs_inode, current_inode)
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
    parser.add_argument('--no-default-permissions', action='store_true', default=False, help='Do not let the kernel enforce mode bits before FUSE operations')
    parser.add_argument('--slow-op-ms', type=float, default=0.0, help='Log lookup/getattr/readdir operations slower than this many milliseconds')
    parser.add_argument('--cache-timeout', type=float, default=1.0, help='Kernel entry/attribute cache timeout in seconds (default: 1.0)')
    parser.add_argument('--bulk-populate', action='store_true', default=False, help='Defer fsync to unmount instead of syncing after every operation (much faster for bulk image population)')
    parser.add_argument('--reconcile-blocks', action='store_true', default=False, help='Walk live inodes at mount time and re-mark as allocated any block a live inode owns but the bitmap marks free (repairs cross-linked/stale inodes left by an unclean guest shutdown). Reserved for reused images; costs one inode-table scan.')
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_args(argv)
    init_logging(options.debug)
    if hasattr(signal, 'SIGUSR1'):
        faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True)

    volume = UFSVolume.open_raw_image(options.image, options.slice)
    operations = UFSOperations(volume, slow_op_ms=options.slow_op_ms, cache_timeout=options.cache_timeout, bulk_populate=options.bulk_populate, reconcile_blocks=options.reconcile_blocks)
    # Reconcile any inconsistency left by a guest VM that was killed without
    # unmounting (the common debugging case) before the mount serves I/O.
    try:
        operations.reconcile_on_mount()
    except BaseException:
        volume.close()
        raise
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add(f'fsname=svr4-ufs:{options.image.name}:{options.slice}')
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
        operations.finalize_summary()
        volume.close()
        raise

    pyfuse3.close()
    operations.finalize_summary()
    volume.close()
    return 0


def make_test_context(uid: int = 0, gid: int = 0, umask: int = 0o022) -> SimpleNamespace:
    return SimpleNamespace(uid=uid, gid=gid, umask=umask, pid=1)
