from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path


# The UFS/BFS host-side code touches the same on-disk structures (superblock,
# cylinder-group bitmaps, inode blocks, indirect blocks) over and over while
# populating a slice. A bounded write-back page cache keeps reads coherent with
# writes and collapses thousands of tiny metadata updates into page-sized writes.
_PAGE_SHIFT = 16            # 64 KiB pages
_PAGE_SIZE = 1 << _PAGE_SHIFT
_MAX_CACHED_PAGES = 4096    # ~256 MiB upper bound; LRU-evicted below that


class DiskBackedSlice:
    def __init__(self, image_path: Path, start_offset: int, size: int) -> None:
        self._path = image_path.resolve()
        self._start_offset = start_offset
        self._size = size
        self._handle = self._path.open('r+b')
        self._pages: 'OrderedDict[int, bytearray]' = OrderedDict()
        self._dirty_pages: set[int] = set()
        self._needs_sync = False

    def __len__(self) -> int:
        return self._size

    def _page_length(self, page_index: int) -> int:
        page_start = page_index << _PAGE_SHIFT
        return min(_PAGE_SIZE, self._size - page_start)

    def _flush_page(self, page_index: int) -> None:
        if page_index not in self._dirty_pages:
            return
        page = self._pages.get(page_index)
        if page is None:
            self._dirty_pages.discard(page_index)
            return
        page_start = page_index << _PAGE_SHIFT
        self._handle.seek(self._start_offset + page_start)
        self._handle.write(page)
        self._dirty_pages.discard(page_index)
        self._needs_sync = True

    def _evict_if_needed(self) -> None:
        while len(self._pages) > _MAX_CACHED_PAGES:
            page_index, _page = next(iter(self._pages.items()))
            self._flush_page(page_index)
            self._pages.pop(page_index, None)

    def _load_page(self, page_index: int) -> bytearray:
        page = self._pages.get(page_index)
        if page is not None:
            self._pages.move_to_end(page_index)
            return page
        page_start = page_index << _PAGE_SHIFT
        read_len = self._page_length(page_index)
        self._handle.seek(self._start_offset + page_start)
        data = self._handle.read(read_len)
        page = bytearray(read_len)
        page[:len(data)] = data
        self._pages[page_index] = page
        self._evict_if_needed()
        return page

    def _read_range(self, start: int, end: int) -> bytes:
        if end <= start:
            return b''
        result = bytearray(end - start)
        offset = start
        while offset < end:
            page_index = offset >> _PAGE_SHIFT
            page = self._load_page(page_index)
            page_base = page_index << _PAGE_SHIFT
            page_pos = offset - page_base
            chunk_end = min(end, page_base + len(page))
            chunk = page[page_pos:page_pos + (chunk_end - offset)]
            result[offset - start:offset - start + len(chunk)] = chunk
            offset = chunk_end
            if not chunk:
                break
        return bytes(result)

    def _write_range(self, start: int, payload: bytes) -> None:
        end = start + len(payload)
        offset = start
        while offset < end:
            page_index = offset >> _PAGE_SHIFT
            page_base = page_index << _PAGE_SHIFT
            page_len = self._page_length(page_index)
            page_end = page_base + page_len
            chunk_end = min(end, page_end)
            page_pos = offset - page_base
            src_pos = offset - start
            length = chunk_end - offset
            if page_pos == 0 and length == page_len:
                page = bytearray(payload[src_pos:src_pos + length])
                self._pages[page_index] = page
            else:
                page = self._load_page(page_index)
                page[page_pos:page_pos + length] = payload[src_pos:src_pos + length]
            self._pages.move_to_end(page_index)
            self._dirty_pages.add(page_index)
            self._needs_sync = True
            offset = chunk_end
        self._evict_if_needed()

    def _record_dirty_range(self, start: int, end: int) -> None:
        del start, end

    def dirty_ranges(self) -> list[tuple[int, int]]:
        ranges = []
        for page_index in sorted(self._dirty_pages):
            start = page_index << _PAGE_SHIFT
            ranges.append((start, start + self._page_length(page_index)))
        return ranges

    def consume_dirty_ranges(self) -> list[tuple[int, int]]:
        return self.dirty_ranges()

    def __getitem__(self, key: int | slice) -> int | bytes:
        if isinstance(key, slice):
            start, stop, step = key.indices(self._size)
            if step != 1:
                return bytes(self[index] for index in range(start, stop, step))
            if stop <= start:
                return b''
            return self._read_range(start, stop)

        index = key if key >= 0 else self._size + key
        if index < 0 or index >= self._size:
            raise IndexError('disk-backed slice index out of range')
        data = self._read_range(index, index + 1)
        if not data:
            return 0
        return data[0]

    def __setitem__(self, key: int | slice, value: object) -> None:
        if isinstance(key, slice):
            start, stop, step = key.indices(self._size)
            if step != 1:
                positions = list(range(start, stop, step))
                payload = bytes(value)  # type: ignore[arg-type]
                if len(payload) != len(positions):
                    raise ValueError('attempt to assign sequence of wrong size to extended slice')
                for position, byte in zip(positions, payload, strict=True):
                    self[position] = byte
                return
            payload = bytes(value)  # type: ignore[arg-type]
            if stop - start != len(payload):
                raise ValueError('disk-backed slice assignments must preserve length')
            if not payload:
                return
            self._write_range(start, payload)
            self._record_dirty_range(start, stop)
            return

        index = key if key >= 0 else self._size + key
        if index < 0 or index >= self._size:
            raise IndexError('disk-backed slice index out of range')
        if not isinstance(value, int):
            raise TypeError('an integer is required')
        self._write_range(index, bytes([value & 0xFF]))
        self._record_dirty_range(index, index + 1)

    def flush(self, sync: bool = True) -> None:
        if sync:
            for page_index in sorted(self._dirty_pages):
                self._flush_page(page_index)
            if self._needs_sync:
                self._handle.flush()
                os.fsync(self._handle.fileno())
                self._needs_sync = False

    def close(self) -> None:
        self.flush(sync=True)
        self._handle.close()
