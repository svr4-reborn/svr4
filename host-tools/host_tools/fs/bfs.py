from __future__ import annotations

from dataclasses import dataclass, replace
from time import time

from .common import BFS_DIRENT_SIZE, BFS_LDIR_SIZE, BFS_MAGIC, BFS_ROOT_INODE, BFS_SUPER_SIZE, FilesystemCandidate, SECTOR_SIZE, i32, u16, u32


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


@dataclass(frozen=True)
class BfsFileEntry:
    inode_number: int
    name: str | None
    data: bytes
    file_type: int
    mode: int
    uid: int
    gid: int
    nlink: int
    atime: int
    mtime: int
    ctime: int


def read_bfs_vattr(raw: ImageBuffer, offset: int = 16) -> dict[str, int]:
    return {
        'file_type': u32(raw, offset),
        'mode': u16(raw, offset + 4),
        'uid': u16(raw, offset + 6),
        'gid': u16(raw, offset + 8),
        'nlink': u16(raw, offset + 10),
        'atime': i32(raw, offset + 12),
        'mtime': i32(raw, offset + 16),
        'ctime': i32(raw, offset + 20),
    }


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
    inode = {'d_ino': u16(raw, 0), 'd_sblock': u32(raw, 4), 'd_eblock': u32(raw, 8), 'd_eoffset': u32(raw, 12)}
    inode.update(read_bfs_vattr(raw))
    return inode


def bfs_dirent_slot_count(image: ImageBuffer, filesystem: FilesystemCandidate) -> int:
    superblock = read_bfs_superblock(image, filesystem)
    table_bytes = max(superblock['data_start'] - BFS_SUPER_SIZE, 0)
    return table_bytes // BFS_DIRENT_SIZE


def read_bfs_root_directory_entries(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[dict[str, int | str]]:
    root_dirent = read_bfs_dirent(image, filesystem.start_offset, BFS_ROOT_INODE)
    if root_dirent is None:
        return []
    directory_bytes = read_bfs_file(image, filesystem, root_dirent)
    entries: list[dict[str, int | str]] = []
    for offset in range(0, len(directory_bytes), BFS_LDIR_SIZE):
        if offset + BFS_LDIR_SIZE > len(directory_bytes):
            break
        inode_number = u16(directory_bytes, offset)
        if inode_number == 0:
            continue
        name = directory_bytes[offset + 2:offset + 16].split(b'\0', 1)[0].decode('ascii', errors='replace').strip()
        if not name:
            continue
        entries.append({'name': name, 'inode': inode_number, 'offset': offset})
    return entries


def iter_bfs_directory_entries(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[dict[str, int | str]]:
    entries: list[dict[str, int | str]] = []
    for directory_entry in read_bfs_root_directory_entries(image, filesystem):
        inode_number = int(directory_entry['inode'])
        inode = read_bfs_dirent(image, filesystem.start_offset, inode_number)
        if inode is None or int(inode['d_ino']) == 0:
            continue
        entries.append(
            {
                'name': str(directory_entry['name']),
                'inode': inode_number,
                'size': bfs_file_size(inode),
                'mode': int(inode['mode']),
                'uid': int(inode['uid']),
                'gid': int(inode['gid']),
                'nlink': int(inode['nlink']),
                'file_type': int(inode['file_type']),
            }
        )
    return entries


def list_bfs_root(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[dict[str, int | str]]:
    entries = iter_bfs_directory_entries(image, filesystem)
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
    if 'file_type' in inode:
        image[inode_offset + 16:inode_offset + 20] = int(inode['file_type']).to_bytes(4, 'little', signed=False)
    if 'mode' in inode:
        image[inode_offset + 20:inode_offset + 22] = int(inode['mode']).to_bytes(2, 'little', signed=False)
    if 'uid' in inode:
        image[inode_offset + 22:inode_offset + 24] = int(inode['uid']).to_bytes(2, 'little', signed=False)
    if 'gid' in inode:
        image[inode_offset + 24:inode_offset + 26] = int(inode['gid']).to_bytes(2, 'little', signed=False)
    if 'nlink' in inode:
        image[inode_offset + 26:inode_offset + 28] = int(inode['nlink']).to_bytes(2, 'little', signed=False)
    if 'atime' in inode:
        image[inode_offset + 28:inode_offset + 32] = int(inode['atime']).to_bytes(4, 'little', signed=True)
    if 'mtime' in inode:
        image[inode_offset + 32:inode_offset + 36] = int(inode['mtime']).to_bytes(4, 'little', signed=True)
    if 'ctime' in inode:
        image[inode_offset + 36:inode_offset + 40] = int(inode['ctime']).to_bytes(4, 'little', signed=True)


def build_bfs_vattr(
    file_type: int,
    mode: int,
    *,
    uid: int = 0,
    gid: int = 0,
    nlink: int = 1,
    timestamp: int = 0,
    atime: int | None = None,
    mtime: int | None = None,
    ctime: int | None = None,
) -> bytes:
    raw = bytearray(40)
    raw[0:4] = int(file_type).to_bytes(4, 'little', signed=False)
    raw[4:6] = int(mode).to_bytes(2, 'little', signed=False)
    raw[6:8] = int(uid).to_bytes(2, 'little', signed=False)
    raw[8:10] = int(gid).to_bytes(2, 'little', signed=False)
    raw[10:12] = int(nlink).to_bytes(2, 'little', signed=False)
    raw[12:16] = int(timestamp if atime is None else atime).to_bytes(4, 'little', signed=True)
    raw[16:20] = int(timestamp if mtime is None else mtime).to_bytes(4, 'little', signed=True)
    raw[20:24] = int(timestamp if ctime is None else ctime).to_bytes(4, 'little', signed=True)
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
    atime: int | None = None,
    mtime: int | None = None,
    ctime: int | None = None,
) -> bytes:
    raw = bytearray(BFS_DIRENT_SIZE)
    raw[0:2] = int(inode_number).to_bytes(2, 'little', signed=False)
    raw[4:8] = int(start_block).to_bytes(4, 'little', signed=False)
    raw[8:12] = int(end_block).to_bytes(4, 'little', signed=False)
    raw[12:16] = int(end_offset).to_bytes(4, 'little', signed=False)
    raw[16:56] = build_bfs_vattr(
        file_type,
        mode,
        uid=uid,
        gid=gid,
        nlink=nlink,
        timestamp=timestamp,
        atime=atime,
        mtime=mtime,
        ctime=ctime,
    )
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


def normalize_bfs_path(path: str) -> str:
    parts = [part for part in path.split('/') if part]
    if not parts:
        return '/'
    if len(parts) > 1:
        raise SystemExit(f'error: bfs only supports the root directory, so nested path {path!r} is invalid')
    name = parts[0]
    try:
        encoded_name = name.encode('ascii', errors='strict')
    except UnicodeEncodeError as error:
        raise SystemExit(f'error: bfs file name {name!r} is not ASCII') from error
    if len(encoded_name) > 14:
        raise SystemExit(f'error: bfs file name {name!r} exceeds the 14-character BFS limit')
    return '/' + name


def bfs_name_from_path(path: str) -> str:
    normalized = normalize_bfs_path(path)
    if normalized == '/':
        raise SystemExit('error: bfs root cannot be used as a regular file path')
    return normalized[1:]


def bfs_root_inode(image: ImageBuffer, filesystem: FilesystemCandidate) -> dict[str, int]:
    root_inode = read_bfs_dirent(image, filesystem.start_offset, BFS_ROOT_INODE)
    if root_inode is None or int(root_inode['d_ino']) == 0:
        raise SystemExit('error: bfs root inode is missing')
    return root_inode


def snapshot_bfs_entries(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[BfsFileEntry]:
    names_by_inode = {int(entry['inode']): str(entry['name']) for entry in read_bfs_root_directory_entries(image, filesystem)}
    entries: list[BfsFileEntry] = []
    for record in scan_bfs_dirents(image, filesystem):
        if record.inode_number == BFS_ROOT_INODE or record.d_ino == 0:
            continue
        inode = read_bfs_dirent(image, filesystem.start_offset, record.inode_number)
        if inode is None or int(inode['d_ino']) == 0:
            continue
        entries.append(
            BfsFileEntry(
                inode_number=record.inode_number,
                name=names_by_inode.get(record.inode_number),
                data=read_bfs_file(image, filesystem, inode),
                file_type=int(inode['file_type']),
                mode=int(inode['mode']),
                uid=int(inode['uid']),
                gid=int(inode['gid']),
                nlink=int(inode['nlink']),
                atime=int(inode['atime']),
                mtime=int(inode['mtime']),
                ctime=int(inode['ctime']),
            )
        )
    entries.sort(key=lambda entry: entry.inode_number)
    return entries


def build_bfs_filesystem_image_with_entries(
    size_bytes: int,
    entries: list[BfsFileEntry],
    *,
    dirent_slots: int,
    root_inode: dict[str, int] | None = None,
    data_end: int | None = None,
) -> bytes:
    if dirent_slots < 1:
        raise SystemExit('error: bfs dirent slot count must be at least one')

    normalized: dict[int, BfsFileEntry] = {}
    seen_names: set[str] = set()
    max_inode_number = BFS_ROOT_INODE + dirent_slots - 1
    for entry in entries:
        if entry.inode_number <= BFS_ROOT_INODE or entry.inode_number > max_inode_number:
            raise SystemExit(f'error: bfs inode {entry.inode_number} is outside the reserved dirent table')
        if entry.inode_number in normalized:
            raise SystemExit(f'error: duplicate bfs inode slot {entry.inode_number}')
        if entry.name is not None:
            normalized_name = bfs_name_from_path('/' + entry.name)
            if normalized_name in seen_names:
                raise SystemExit(f'error: duplicate bfs file name {entry.name!r}')
            seen_names.add(normalized_name)
        normalized[entry.inode_number] = entry

    filesystem_end = size_bytes - 1 if data_end is None else min(size_bytes - 1, int(data_end))
    data_start = ((BFS_SUPER_SIZE + (dirent_slots * BFS_DIRENT_SIZE) + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE
    root_directory_entries = [entry for entry in normalized.values() if entry.name is not None]
    root_directory_bytes = len(root_directory_entries) * BFS_LDIR_SIZE
    root_directory_allocation = max(SECTOR_SIZE, ((max(root_directory_bytes, 1) + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE)
    next_offset = data_start + root_directory_allocation
    if next_offset - 1 > filesystem_end:
        raise SystemExit('error: bfs root directory would exceed the filesystem bounds')

    file_layouts: dict[int, tuple[int, int, int]] = {}
    current_offset = next_offset
    for inode_number in sorted(normalized):
        entry = normalized[inode_number]
        if entry.data:
            allocation = ((len(entry.data) + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE
            start_offset = current_offset
            end_offset = start_offset + len(entry.data) - 1
            end_block = ((start_offset + allocation) // SECTOR_SIZE) - 1
            if start_offset + allocation - 1 > filesystem_end:
                raise SystemExit(f'error: bfs filesystem does not have enough contiguous space for inode {inode_number}')
            file_layouts[inode_number] = (start_offset, end_block, end_offset)
            current_offset += allocation
        else:
            file_layouts[inode_number] = (0, 0, 0)

    image = bytearray(size_bytes)
    image[0:4] = BFS_MAGIC.to_bytes(4, 'little', signed=False)
    image[4:8] = data_start.to_bytes(4, 'little', signed=False)
    image[8:12] = filesystem_end.to_bytes(4, 'little', signed=False)

    root_metadata = dict(root_inode or {})
    root_mode = int(root_metadata.get('mode', 0o755))
    root_uid = int(root_metadata.get('uid', 0))
    root_gid = int(root_metadata.get('gid', 0))
    root_nlink = int(root_metadata.get('nlink', 2))
    root_atime = int(root_metadata.get('atime', 0))
    root_mtime = int(root_metadata.get('mtime', 0))
    root_ctime = int(root_metadata.get('ctime', 0))
    root_start_block = data_start // SECTOR_SIZE
    root_end_block = ((data_start + root_directory_allocation) // SECTOR_SIZE) - 1
    root_end_offset = (data_start + root_directory_bytes - 1) if root_directory_bytes else (data_start - 1)
    image[BFS_SUPER_SIZE:BFS_SUPER_SIZE + BFS_DIRENT_SIZE] = build_bfs_dirent_bytes(
        BFS_ROOT_INODE,
        root_start_block,
        root_end_block,
        root_end_offset,
        file_type=BFS_VDIR,
        mode=root_mode,
        uid=root_uid,
        gid=root_gid,
        nlink=root_nlink,
        atime=root_atime,
        mtime=root_mtime,
        ctime=root_ctime,
    )

    directory_offset = data_start
    for inode_number in sorted(normalized):
        entry = normalized[inode_number]
        start_offset, end_block, end_offset = file_layouts[inode_number]
        start_block = 0 if start_offset == 0 else start_offset // SECTOR_SIZE
        inode_offset = BFS_SUPER_SIZE + ((inode_number - BFS_ROOT_INODE) * BFS_DIRENT_SIZE)
        image[inode_offset:inode_offset + BFS_DIRENT_SIZE] = build_bfs_dirent_bytes(
            inode_number,
            start_block,
            end_block,
            end_offset,
            file_type=entry.file_type,
            mode=entry.mode,
            uid=entry.uid,
            gid=entry.gid,
            nlink=entry.nlink,
            atime=entry.atime,
            mtime=entry.mtime,
            ctime=entry.ctime,
        )
        if entry.data:
            image[start_offset:start_offset + len(entry.data)] = entry.data
        if entry.name is not None:
            image[directory_offset:directory_offset + 2] = int(inode_number).to_bytes(2, 'little', signed=False)
            image[directory_offset + 2:directory_offset + 16] = entry.name.encode('ascii').ljust(14, b'\0')
            directory_offset += BFS_LDIR_SIZE

    return bytes(image)


def rebuild_bfs_region(
    image: bytearray,
    filesystem: FilesystemCandidate,
    entries: list[BfsFileEntry],
    *,
    root_inode: dict[str, int] | None = None,
) -> None:
    slot_count = bfs_dirent_slot_count(image, filesystem)
    superblock = read_bfs_superblock(image, filesystem)
    filesystem_size = len(image) - filesystem.start_offset
    rebuilt = build_bfs_filesystem_image_with_entries(
        filesystem_size,
        entries,
        dirent_slots=slot_count,
        root_inode=root_inode,
        data_end=int(superblock['data_end']),
    )
    end_offset = filesystem.start_offset + filesystem_size
    image[filesystem.start_offset:end_offset] = rebuilt


def create_bfs_file(
    image: bytearray,
    filesystem: FilesystemCandidate,
    target_path: str,
    data: bytes,
    *,
    mode: int = 0o644,
    uid: int = 0,
    gid: int = 0,
    timestamp: int | None = None,
) -> dict[str, int | str]:
    name = bfs_name_from_path(target_path)
    snapshot = snapshot_bfs_entries(image, filesystem)
    if any(entry.name == name for entry in snapshot):
        raise SystemExit(f'error: bfs file {target_path} already exists')

    used_inodes = {entry.inode_number for entry in snapshot}
    max_inode_number = BFS_ROOT_INODE + bfs_dirent_slot_count(image, filesystem) - 1
    inode_number = 0
    for candidate in range(BFS_ROOT_INODE + 1, max_inode_number + 1):
        if candidate not in used_inodes:
            inode_number = candidate
            break
    if inode_number == 0:
        raise SystemExit('error: no free BFS dirent slots remain')

    updated_snapshot = snapshot + [
        BfsFileEntry(
            inode_number=inode_number,
            name=name,
            data=data,
            file_type=BFS_VREG,
            mode=mode,
            uid=uid,
            gid=gid,
            nlink=1,
            atime=int(time()) if timestamp is None else int(timestamp),
            mtime=int(time()) if timestamp is None else int(timestamp),
            ctime=int(time()) if timestamp is None else int(timestamp),
        )
    ]
    rebuild_bfs_region(image, filesystem, updated_snapshot, root_inode=bfs_root_inode(image, filesystem))
    return {'target_path': normalize_bfs_path(target_path), 'inode': inode_number, 'size': len(data)}


def remove_bfs_path(image: bytearray, filesystem: FilesystemCandidate, target_path: str) -> dict[str, int | str]:
    name = bfs_name_from_path(target_path)
    snapshot = snapshot_bfs_entries(image, filesystem)
    target_entry = None
    remaining_entries: list[BfsFileEntry] = []
    for entry in snapshot:
        if entry.name == name:
            target_entry = entry
            continue
        remaining_entries.append(entry)
    if target_entry is None:
        raise SystemExit(f'error: could not resolve {target_path} inside the bfs filesystem')
    rebuild_bfs_region(image, filesystem, remaining_entries, root_inode=bfs_root_inode(image, filesystem))
    return {'target_path': normalize_bfs_path(target_path), 'inode': target_entry.inode_number}


def detach_bfs_path(image: bytearray, filesystem: FilesystemCandidate, target_path: str) -> dict[str, int | str]:
    name = bfs_name_from_path(target_path)
    snapshot = snapshot_bfs_entries(image, filesystem)
    target_entry = None
    updated_entries: list[BfsFileEntry] = []
    timestamp = int(time())
    for entry in snapshot:
        if entry.name == name:
            target_entry = replace(entry, name=None, nlink=0, ctime=timestamp)
            updated_entries.append(target_entry)
            continue
        updated_entries.append(entry)
    if target_entry is None:
        raise SystemExit(f'error: could not resolve {target_path} inside the bfs filesystem')
    rebuild_bfs_region(image, filesystem, updated_entries, root_inode=bfs_root_inode(image, filesystem))
    return {'target_path': normalize_bfs_path(target_path), 'inode': target_entry.inode_number}


def finalize_bfs_unlinked_inode(image: bytearray, filesystem: FilesystemCandidate, inode_number: int) -> dict[str, int]:
    if inode_number == BFS_ROOT_INODE:
        raise SystemExit('error: refusing to finalize the BFS root inode')
    snapshot = snapshot_bfs_entries(image, filesystem)
    target_entry = None
    remaining_entries: list[BfsFileEntry] = []
    for entry in snapshot:
        if entry.inode_number == inode_number:
            target_entry = entry
            continue
        remaining_entries.append(entry)
    if target_entry is None:
        raise SystemExit(f'error: bfs inode {inode_number} does not exist')
    if target_entry.name is not None:
        raise SystemExit(f'error: refusing to finalize linked bfs inode {inode_number}')
    rebuild_bfs_region(image, filesystem, remaining_entries, root_inode=bfs_root_inode(image, filesystem))
    return {'inode': inode_number}


def replace_bfs_inode_data(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, new_data: bytes) -> dict[str, int | str]:
    if inode_number == BFS_ROOT_INODE:
        raise SystemExit('error: refusing to replace the BFS root directory contents as a regular file')
    snapshot = snapshot_bfs_entries(image, filesystem)
    target_entry = None
    updated_entries: list[BfsFileEntry] = []
    timestamp = int(time())
    for entry in snapshot:
        if entry.inode_number == inode_number:
            target_entry = replace(entry, data=new_data, mtime=timestamp, ctime=timestamp)
            updated_entries.append(target_entry)
            continue
        updated_entries.append(entry)
    if target_entry is None:
        raise SystemExit(f'error: bfs inode {inode_number} does not exist')
    rebuild_bfs_region(image, filesystem, updated_entries, root_inode=bfs_root_inode(image, filesystem))
    return {
        'inode': inode_number,
        'name': '' if target_entry.name is None else target_entry.name,
        'new_size': len(new_data),
    }


def rename_bfs_path(
    image: bytearray,
    filesystem: FilesystemCandidate,
    source_path: str,
    target_path: str,
    *,
    detach_target: bool = False,
) -> dict[str, int | str]:
    source_name = bfs_name_from_path(source_path)
    target_name = bfs_name_from_path(target_path)
    if source_name == target_name:
        return {'source_path': normalize_bfs_path(source_path), 'target_path': normalize_bfs_path(target_path)}

    snapshot = snapshot_bfs_entries(image, filesystem)
    source_entry = None
    overwritten_inode = 0
    updated_entries: list[BfsFileEntry] = []
    timestamp = int(time())
    for entry in snapshot:
        if entry.name == source_name:
            source_entry = replace(entry, name=target_name, ctime=timestamp)
            updated_entries.append(source_entry)
            continue
        if entry.name == target_name:
            overwritten_inode = entry.inode_number
            if detach_target:
                updated_entries.append(replace(entry, name=None, nlink=0, ctime=timestamp))
            continue
        updated_entries.append(entry)
    if source_entry is None:
        raise SystemExit(f'error: could not resolve {source_path} inside the bfs filesystem')
    rebuild_bfs_region(image, filesystem, updated_entries, root_inode=bfs_root_inode(image, filesystem))
    result: dict[str, int | str] = {
        'source_path': normalize_bfs_path(source_path),
        'target_path': normalize_bfs_path(target_path),
        'inode': source_entry.inode_number,
    }
    if overwritten_inode != 0:
        result['overwritten_inode'] = overwritten_inode
    return result


def write_bfs_inode_fields(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    *,
    mode: int | None = None,
    uid: int | None = None,
    gid: int | None = None,
    nlink: int | None = None,
    atime: int | None = None,
    mtime: int | None = None,
    ctime: int | None = None,
) -> dict[str, int]:
    inode = read_bfs_dirent(image, filesystem.start_offset, inode_number)
    if inode is None or int(inode['d_ino']) == 0:
        raise SystemExit(f'error: bfs inode {inode_number} does not exist')
    if mode is not None:
        inode['mode'] = int(mode)
    if uid is not None:
        inode['uid'] = int(uid)
    if gid is not None:
        inode['gid'] = int(gid)
    if nlink is not None:
        inode['nlink'] = int(nlink)
    if atime is not None:
        inode['atime'] = int(atime)
    if mtime is not None:
        inode['mtime'] = int(mtime)
    if ctime is not None:
        inode['ctime'] = int(ctime)
    write_bfs_inode(image, filesystem, inode_number, inode)
    return inode


def bfs_filesystem_stats(image: ImageBuffer, filesystem: FilesystemCandidate) -> dict[str, int]:
    superblock = read_bfs_superblock(image, filesystem)
    entries = snapshot_bfs_entries(image, filesystem)
    visible_count = sum(1 for entry in entries if entry.name is not None)
    root_directory_bytes = max(1, visible_count * BFS_LDIR_SIZE)
    root_directory_allocation = ((root_directory_bytes + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE
    allocated_bytes = root_directory_allocation
    for entry in entries:
        if not entry.data:
            continue
        allocated_bytes += ((len(entry.data) + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE

    total_bytes = (int(superblock['data_end']) - int(superblock['data_start'])) + 1
    if total_bytes < 0:
        total_bytes = 0
    free_bytes = max(total_bytes - allocated_bytes, 0)

    slot_count = bfs_dirent_slot_count(image, filesystem)
    free_slots = (slot_count - 1) - len(entries)
    if free_slots < 0:
        free_slots = 0

    return {
        'bsize': SECTOR_SIZE,
        'blocks': total_bytes // SECTOR_SIZE,
        'bfree': free_bytes // SECTOR_SIZE,
        'files': max(slot_count - 1, 0),
        'ffree': free_slots,
        'namemax': 14,
    }