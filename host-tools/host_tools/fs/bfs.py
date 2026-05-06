from __future__ import annotations

from dataclasses import dataclass
from time import time

from .common import BFS_DIRENT_SIZE, BFS_LDIR_SIZE, BFS_MAGIC, BFS_ROOT_INODE, BFS_SUPER_SIZE, FilesystemCandidate, SECTOR_SIZE, u16, u32


BFS_VREG = 1
BFS_VDIR = 2
ImageBuffer = bytes | bytearray


@dataclass(frozen=True)
class BfsDirentRecord:
    inode_number: int
    inode_offset: int
    d_ino: int
    d_sblock: int
    d_eblock: int
    d_eoffset: int


def detect_bfs(image: ImageBuffer) -> list[FilesystemCandidate]:
    candidates: list[FilesystemCandidate] = []
    magic = BFS_MAGIC.to_bytes(4, 'little')
    search_from = 0
    while True:
        offset = image.find(magic, search_from)
        if offset < 0:
            break
        search_from = offset + 1
        if offset % SECTOR_SIZE != 0:
            continue
        if offset + BFS_SUPER_SIZE > len(image):
            continue
        data_start = u32(image, offset + 4)
        data_end = u32(image, offset + 8)
        if data_start < BFS_SUPER_SIZE or data_end < data_start or offset + data_end >= len(image):
            continue
        candidates.append(
            FilesystemCandidate(
                kind='bfs',
                start_offset=offset,
                super_offset=offset,
                block_size=SECTOR_SIZE,
                details={'data_start': data_start, 'data_end': data_end},
            )
        )
    return candidates


def read_bfs_dirent(image: ImageBuffer, fs_start: int, inode_number: int) -> dict[str, int] | None:
    inode_offset = fs_start + BFS_SUPER_SIZE + ((inode_number - BFS_ROOT_INODE) * BFS_DIRENT_SIZE)
    if inode_offset < fs_start or inode_offset + BFS_DIRENT_SIZE > len(image):
        return None
    raw = image[inode_offset:inode_offset + BFS_DIRENT_SIZE]
    return {'d_ino': u16(raw, 0), 'd_sblock': u32(raw, 4), 'd_eblock': u32(raw, 8), 'd_eoffset': u32(raw, 12)}


def list_bfs_root(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[dict[str, int | str]]:
    root_dirent = read_bfs_dirent(image, filesystem.start_offset, BFS_ROOT_INODE)
    if root_dirent is None:
        return []
    directory_start = filesystem.start_offset + (root_dirent['d_sblock'] * SECTOR_SIZE)
    directory_end = filesystem.start_offset + root_dirent['d_eoffset'] + 1
    if directory_end <= directory_start or directory_end > len(image):
        return []
    entries: list[dict[str, int | str]] = []
    directory_bytes = image[directory_start:directory_end]
    for offset in range(0, len(directory_bytes), BFS_LDIR_SIZE):
        inode_number = u16(directory_bytes, offset)
        if inode_number == 0:
            continue
        name = directory_bytes[offset + 2:offset + 16].split(b'\0', 1)[0].decode('ascii', errors='replace').strip()
        if not name:
            continue
        inode = read_bfs_dirent(image, filesystem.start_offset, inode_number)
        entry: dict[str, int | str] = {'name': name, 'inode': inode_number}
        if inode is not None and inode['d_sblock'] != 0:
            entry['size'] = (inode['d_eoffset'] - (inode['d_sblock'] * SECTOR_SIZE)) + 1
        entries.append(entry)
    entries.sort(key=lambda item: str(item['name']))
    return entries


def resolve_bfs_path(image: ImageBuffer, filesystem: FilesystemCandidate, path: str) -> tuple[int, dict[str, int]] | None:
    parts = [part for part in path.split('/') if part]
    if len(parts) > 1:
        return None
    if not parts:
        root = read_bfs_dirent(image, filesystem.start_offset, BFS_ROOT_INODE)
        if root is None:
            return None
        return BFS_ROOT_INODE, root
    target = parts[0]
    for entry in list_bfs_root(image, filesystem):
        if entry['name'] == target:
            inode_number = int(entry['inode'])
            inode = read_bfs_dirent(image, filesystem.start_offset, inode_number)
            if inode is None:
                return None
            return inode_number, inode
    return None


def read_bfs_file(image: ImageBuffer, filesystem: FilesystemCandidate, inode: dict[str, int]) -> bytes:
    start = filesystem.start_offset + (inode['d_sblock'] * SECTOR_SIZE)
    end = filesystem.start_offset + inode['d_eoffset'] + 1
    if start < filesystem.start_offset or end > len(image) or end < start:
        return b''
    return image[start:end]


def read_bfs_path_bytes(image: ImageBuffer, filesystem: FilesystemCandidate, target_path: str) -> tuple[int, dict[str, int], bytes]:
    resolved = resolve_bfs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: could not resolve {target_path} inside the bfs filesystem')
    inode_number, inode = resolved
    return inode_number, inode, read_bfs_file(image, filesystem, inode)


def bfs_inode_offset(filesystem: FilesystemCandidate, inode_number: int) -> int:
    return filesystem.start_offset + BFS_SUPER_SIZE + ((inode_number - BFS_ROOT_INODE) * BFS_DIRENT_SIZE)


def bfs_allocated_bytes(inode: dict[str, int]) -> int:
    d_sblock = int(inode['d_sblock'])
    d_eblock = int(inode['d_eblock'])
    if d_sblock == 0 or d_eblock < d_sblock:
        return 0
    return ((d_eblock - d_sblock) + 1) * SECTOR_SIZE


def bfs_file_size(inode: dict[str, int]) -> int:
    d_sblock = int(inode['d_sblock'])
    d_eoffset = int(inode['d_eoffset'])
    if d_sblock == 0 or d_eoffset < (d_sblock * SECTOR_SIZE):
        return 0
    return (d_eoffset - (d_sblock * SECTOR_SIZE)) + 1


def read_bfs_superblock(image: ImageBuffer, filesystem: FilesystemCandidate) -> dict[str, int]:
    offset = filesystem.super_offset
    return {
        'magic': u32(image, offset),
        'data_start': u32(image, offset + 4),
        'data_end': u32(image, offset + 8),
    }


def scan_bfs_dirents(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[BfsDirentRecord]:
    superblock = read_bfs_superblock(image, filesystem)
    records: list[BfsDirentRecord] = []
    for inode_offset in range(filesystem.start_offset + BFS_SUPER_SIZE, filesystem.start_offset + superblock['data_start'], BFS_DIRENT_SIZE):
        raw = image[inode_offset:inode_offset + BFS_DIRENT_SIZE]
        if len(raw) < BFS_DIRENT_SIZE:
            break
        inode_number = BFS_ROOT_INODE + ((inode_offset - (filesystem.start_offset + BFS_SUPER_SIZE)) // BFS_DIRENT_SIZE)
        records.append(
            BfsDirentRecord(
                inode_number=inode_number,
                inode_offset=inode_offset,
                d_ino=u16(raw, 0),
                d_sblock=u32(raw, 4),
                d_eblock=u32(raw, 8),
                d_eoffset=u32(raw, 12),
            )
        )
    return records


def bfs_dirent_to_inode(record: BfsDirentRecord) -> dict[str, int]:
    return {
        'd_ino': record.d_ino,
        'd_sblock': record.d_sblock,
        'd_eblock': record.d_eblock,
        'd_eoffset': record.d_eoffset,
    }


def valid_bfs_file_records(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[BfsDirentRecord]:
    superblock = read_bfs_superblock(image, filesystem)
    valid: list[BfsDirentRecord] = []
    for record in scan_bfs_dirents(image, filesystem):
        if record.d_ino == 0:
            continue
        if record.d_sblock == 0 or record.d_eblock < record.d_sblock:
            continue
        file_start = record.d_sblock * SECTOR_SIZE
        file_end = record.d_eblock * SECTOR_SIZE
        if file_start < superblock['data_start'] or file_end > superblock['data_end']:
            continue
        valid.append(record)
    return valid


def write_bfs_inode(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, inode: dict[str, int]) -> None:
    inode_offset = bfs_inode_offset(filesystem, inode_number)
    image[inode_offset:inode_offset + 2] = int(inode['d_ino']).to_bytes(2, 'little', signed=False)
    image[inode_offset + 4:inode_offset + 8] = int(inode['d_sblock']).to_bytes(4, 'little', signed=False)
    image[inode_offset + 8:inode_offset + 12] = int(inode['d_eblock']).to_bytes(4, 'little', signed=False)
    image[inode_offset + 12:inode_offset + 16] = int(inode['d_eoffset']).to_bytes(4, 'little', signed=False)


def build_bfs_vattr(file_type: int, mode: int, *, uid: int = 0, gid: int = 0, nlink: int = 1, timestamp: int = 0) -> bytes:
    raw = bytearray(40)
    raw[0:4] = int(file_type).to_bytes(4, 'little', signed=False)
    raw[4:6] = int(mode).to_bytes(2, 'little', signed=False)
    raw[6:8] = int(uid).to_bytes(2, 'little', signed=False)
    raw[8:10] = int(gid).to_bytes(2, 'little', signed=False)
    raw[10:12] = int(nlink).to_bytes(2, 'little', signed=False)
    raw[12:16] = int(timestamp).to_bytes(4, 'little', signed=True)
    raw[16:20] = int(timestamp).to_bytes(4, 'little', signed=True)
    raw[20:24] = int(timestamp).to_bytes(4, 'little', signed=True)
    return bytes(raw)


def build_bfs_dirent_bytes(
    inode_number: int,
    start_block: int,
    end_block: int,
    end_offset: int,
    *,
    file_type: int,
    mode: int,
    uid: int = 0,
    gid: int = 0,
    nlink: int = 1,
    timestamp: int = 0,
) -> bytes:
    raw = bytearray(BFS_DIRENT_SIZE)
    raw[0:2] = int(inode_number).to_bytes(2, 'little', signed=False)
    raw[4:8] = int(start_block).to_bytes(4, 'little', signed=False)
    raw[8:12] = int(end_block).to_bytes(4, 'little', signed=False)
    raw[12:16] = int(end_offset).to_bytes(4, 'little', signed=False)
    raw[16:56] = build_bfs_vattr(file_type, mode, uid=uid, gid=gid, nlink=nlink, timestamp=timestamp)
    return bytes(raw)


def build_bfs_filesystem_image(
    size_bytes: int,
    files: list[tuple[str, bytes]],
    *,
    dirent_slots: int | None = None,
    timestamp: int | None = None,
) -> bytes:
    if size_bytes < (BFS_SUPER_SIZE + SECTOR_SIZE):
        raise SystemExit('error: bfs slice is too small to hold a filesystem image')

    normalized_files: list[tuple[str, bytes]] = []
    seen_names: set[str] = set()
    for name, data in files:
        encoded_name = name.encode('ascii', errors='strict')
        if '/' in name or not name:
            raise SystemExit(f'error: bfs file name {name!r} must be a non-empty root entry name')
        if len(encoded_name) > 14:
            raise SystemExit(f'error: bfs file name {name!r} exceeds the 14-character BFS limit')
        if name in seen_names:
            raise SystemExit(f'error: duplicate bfs file name {name!r}')
        seen_names.add(name)
        normalized_files.append((name, data))

    required_slots = len(normalized_files) + 1
    total_dirent_slots = max(required_slots, dirent_slots or max(16, required_slots))
    data_start = ((BFS_SUPER_SIZE + (total_dirent_slots * BFS_DIRENT_SIZE) + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE
    root_directory_bytes = len(normalized_files) * BFS_LDIR_SIZE
    root_directory_allocation = max(SECTOR_SIZE, ((max(root_directory_bytes, 1) + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE)
    next_offset = data_start + root_directory_allocation
    if next_offset > size_bytes:
        raise SystemExit('error: bfs slice is too small for the requested dirent table and root directory')

    file_layouts: list[tuple[int, str, bytes, int, int, int]] = []
    current_offset = next_offset
    for index, (name, data) in enumerate(normalized_files, start=1):
        inode_number = BFS_ROOT_INODE + index
        if data:
            allocation = ((len(data) + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE
            start_offset = current_offset
            end_offset = start_offset + len(data) - 1
            end_block = ((start_offset + allocation) // SECTOR_SIZE) - 1
            if start_offset + allocation > size_bytes:
                raise SystemExit(f'error: bfs slice is too small for file {name!r}')
            file_layouts.append((inode_number, name, data, start_offset, end_block, end_offset))
            current_offset += allocation
        else:
            file_layouts.append((inode_number, name, data, 0, 0, 0))

    image = bytearray(size_bytes)
    image[0:4] = BFS_MAGIC.to_bytes(4, 'little', signed=False)
    image[4:8] = data_start.to_bytes(4, 'little', signed=False)
    image[8:12] = (size_bytes - 1).to_bytes(4, 'little', signed=False)

    created_at = int(time()) if timestamp is None else int(timestamp)
    root_start_block = data_start // SECTOR_SIZE
    root_end_block = ((data_start + root_directory_allocation) // SECTOR_SIZE) - 1
    root_end_offset = (data_start + root_directory_bytes - 1) if root_directory_bytes else (data_start - 1)
    image[BFS_SUPER_SIZE:BFS_SUPER_SIZE + BFS_DIRENT_SIZE] = build_bfs_dirent_bytes(
        BFS_ROOT_INODE,
        root_start_block,
        root_end_block,
        root_end_offset,
        file_type=BFS_VDIR,
        mode=0o755,
        nlink=2,
        timestamp=created_at,
    )

    directory_offset = data_start
    for index, (inode_number, name, data, start_offset, end_block, end_offset) in enumerate(file_layouts):
        inode_offset = BFS_SUPER_SIZE + ((index + 1) * BFS_DIRENT_SIZE)
        if data:
            start_block = start_offset // SECTOR_SIZE
            image[start_offset:start_offset + len(data)] = data
            image[inode_offset:inode_offset + BFS_DIRENT_SIZE] = build_bfs_dirent_bytes(
                inode_number,
                start_block,
                end_block,
                end_offset,
                file_type=BFS_VREG,
                mode=0o644,
                nlink=1,
                timestamp=created_at,
            )
        else:
            image[inode_offset:inode_offset + BFS_DIRENT_SIZE] = build_bfs_dirent_bytes(
                inode_number,
                0,
                0,
                0,
                file_type=BFS_VREG,
                mode=0o644,
                nlink=1,
                timestamp=created_at,
            )
        image[directory_offset:directory_offset + 2] = int(inode_number).to_bytes(2, 'little', signed=False)
        image[directory_offset + 2:directory_offset + 16] = name.encode('ascii').ljust(14, b'\0')
        directory_offset += BFS_LDIR_SIZE

    return bytes(image)


def format_bfs_filesystem(image: bytearray, files: list[tuple[str, bytes]], *, dirent_slots: int | None = None) -> dict[str, int]:
    formatted = build_bfs_filesystem_image(len(image), files, dirent_slots=dirent_slots)
    image[:] = formatted
    return {
        'file_count': len(files),
        'dirent_slots': max(len(files) + 1, dirent_slots or max(16, len(files) + 1)),
        'image_size': len(image),
    }


def apply_bfs_inplace_replacement(image: bytearray, filesystem: FilesystemCandidate, target_path: str, new_data: bytes) -> dict[str, int | str]:
    inode_number, inode, old_data = read_bfs_path_bytes(image, filesystem, target_path)
    allocated_bytes = bfs_allocated_bytes(inode)
    if allocated_bytes <= 0:
        raise SystemExit(f'error: bfs file {target_path} has no writable allocated extent')
    if len(new_data) == 0:
        raise SystemExit('error: zero-length bfs replacements are not supported by the conservative in-place API')
    if len(new_data) > allocated_bytes:
        raise SystemExit(
            f'error: replacement for {target_path} exceeds its allocated bfs extent ({len(new_data)} > {allocated_bytes})'
        )

    d_sblock = int(inode['d_sblock'])
    block_offset = filesystem.start_offset + (d_sblock * SECTOR_SIZE)
    image[block_offset:block_offset + allocated_bytes] = b'\0' * allocated_bytes
    image[block_offset:block_offset + len(new_data)] = new_data

    updated_inode = dict(inode)
    updated_inode['d_eoffset'] = (d_sblock * SECTOR_SIZE) + len(new_data) - 1
    write_bfs_inode(image, filesystem, inode_number, updated_inode)

    return {
        'target_path': target_path,
        'inode': inode_number,
        'old_size': len(old_data),
        'new_size': len(new_data),
        'capacity': allocated_bytes,
    }


def apply_bfs_replacement(image: bytearray, filesystem: FilesystemCandidate, target_path: str, new_data: bytes) -> dict[str, int | str]:
    inode_number, inode, old_data = read_bfs_path_bytes(image, filesystem, target_path)
    current_capacity = bfs_allocated_bytes(inode)
    if len(new_data) <= current_capacity and current_capacity > 0:
        return apply_bfs_inplace_replacement(image, filesystem, target_path, new_data)

    superblock = read_bfs_superblock(image, filesystem)
    data_start_block = superblock['data_start'] // SECTOR_SIZE
    data_end_block = superblock['data_end'] // SECTOR_SIZE
    target_record = None
    movable_records: list[BfsDirentRecord] = []
    for record in valid_bfs_file_records(image, filesystem):
        if record.inode_number == inode_number:
            target_record = record
        else:
            movable_records.append(record)
    if target_record is None:
        raise SystemExit(f'error: could not locate bfs dirent for inode {inode_number}')

    source_image = bytes(image)
    for record in [*movable_records, target_record]:
        start = filesystem.start_offset + (record.d_sblock * SECTOR_SIZE)
        end = filesystem.start_offset + ((record.d_eblock + 1) * SECTOR_SIZE)
        image[start:end] = b'\0' * (end - start)

    next_block = data_start_block
    moved_blocks = 0
    for record in sorted(movable_records, key=lambda item: item.d_sblock):
        current_inode = bfs_dirent_to_inode(record)
        old_size = bfs_file_size(current_inode)
        old_capacity = bfs_allocated_bytes(current_inode)
        if old_capacity <= 0:
            continue
        new_start_block = next_block
        new_end_block = new_start_block + (old_capacity // SECTOR_SIZE) - 1
        if new_end_block > data_end_block:
            raise SystemExit('error: bfs compaction would exceed the filesystem bounds')
        old_start = filesystem.start_offset + (record.d_sblock * SECTOR_SIZE)
        new_start = filesystem.start_offset + (new_start_block * SECTOR_SIZE)
        image[new_start:new_start + old_capacity] = b'\0' * old_capacity
        image[new_start:new_start + old_size] = source_image[old_start:old_start + old_size]
        updated_inode = dict(current_inode)
        updated_inode['d_sblock'] = new_start_block
        updated_inode['d_eblock'] = new_end_block
        updated_inode['d_eoffset'] = (new_start_block * SECTOR_SIZE) + max(old_size - 1, 0)
        write_bfs_inode(image, filesystem, record.inode_number, updated_inode)
        if record.d_sblock != new_start_block:
            moved_blocks += old_capacity // SECTOR_SIZE
        next_block = new_end_block + 1

    needed_blocks = max(1, (len(new_data) + SECTOR_SIZE - 1) // SECTOR_SIZE)
    target_end_block = next_block + needed_blocks - 1
    if target_end_block > data_end_block:
        raise SystemExit(
            f'error: replacement for {target_path} exceeds the compacted bfs free space ({len(new_data)} bytes requested)'
        )
    target_start = filesystem.start_offset + (next_block * SECTOR_SIZE)
    target_capacity = needed_blocks * SECTOR_SIZE
    image[target_start:target_start + target_capacity] = b'\0' * target_capacity
    image[target_start:target_start + len(new_data)] = new_data
    updated_target = dict(inode)
    updated_target['d_sblock'] = next_block
    updated_target['d_eblock'] = target_end_block
    updated_target['d_eoffset'] = (next_block * SECTOR_SIZE) + len(new_data) - 1
    write_bfs_inode(image, filesystem, inode_number, updated_target)
    return {
        'target_path': target_path,
        'inode': inode_number,
        'old_size': len(old_data),
        'new_size': len(new_data),
        'old_capacity': current_capacity,
        'new_capacity': target_capacity,
        'moved_blocks': moved_blocks,
    }