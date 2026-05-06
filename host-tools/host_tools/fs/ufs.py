from __future__ import annotations

from typing import Any

from .common import FilesystemCandidate, SECTOR_SIZE, UFS_NDADDR, UFS_ROOT_INODE
from .ufs_directory import UFS_DIRBLKSIZ, UFSDirectoryEntry, UFSDirectoryInsertSlot, decode_ufs_directory_entry, encode_ufs_directory_entry, find_ufs_directory_insert_slot, insert_ufs_directory_entry, iter_ufs_directory_records, remove_ufs_directory_entry, rewrite_ufs_directory_entry_inode, ufs_dirsiz
from .ufs_lowlevel import ImageBuffer, MAXCPG, MAXFRAG, MAXIPG, NBBY, UFS_CG_CS_NBFREE_OFFSET, UFS_CG_CS_NDIR_OFFSET, UFS_CG_CS_NIFREE_OFFSET, UFS_CG_FREE_OFFSET, UFS_CG_IROTOR_OFFSET, UFS_CG_IUSED_OFFSET, UFS_CG_MAGIC, UFS_CG_MAGIC_OFFSET, UFS_CG_NDBLK_OFFSET, UFS_DINODE_SIZE, UFS_DI_ATIME_OFFSET, UFS_DI_BLOCKS_OFFSET, UFS_DI_CTIME_OFFSET, UFS_DI_DB_OFFSET, UFS_DI_EFTFLAG_OFFSET, UFS_DI_FLAGS_OFFSET, UFS_DI_GEN_OFFSET, UFS_DI_GID_OFFSET, UFS_DI_IB_OFFSET, UFS_DI_MODE_OFFSET, UFS_DI_MTIME_OFFSET, UFS_DI_NLINK_OFFSET, UFS_DI_SGID_OFFSET, UFS_DI_SIZE_OFFSET, UFS_DI_SUID_OFFSET, UFS_DI_UID_OFFSET, UFS_EFT_MAGIC, UFS_FS_BSIZE_OFFSET, UFS_FS_CBLKNO_OFFSET, UFS_FS_CGMASK_OFFSET, UFS_FS_CGOFFSET_OFFSET, UFS_FS_CSTOTAL_NBFREE_OFFSET, UFS_FS_CSTOTAL_NDIR_OFFSET, UFS_FS_CSTOTAL_NIFREE_OFFSET, UFS_FS_DBLKNO_OFFSET, UFS_FS_FPG_OFFSET, UFS_FS_FRAG_OFFSET, UFS_FS_FSBTODB_OFFSET, UFS_FS_FSIZE_OFFSET, UFS_FS_IBLKNO_OFFSET, UFS_FS_INOPB_OFFSET, UFS_FS_IPG_OFFSET, UFS_FS_MAGIC_OFFSET, UFS_FS_MINFREE_OFFSET, UFS_FS_NCG_OFFSET, UFS_FS_NINDIR_OFFSET, UFS_IFDIR, UFS_IFLNK, UFS_IFMT, UFS_IFREG, UFS_MAGIC, UFS_SB_OFFSET, UFS_SB_SIZE, adjust_cg_directory_count, adjust_cg_free_blocks, adjust_cg_free_inodes, adjust_superblock_directory_count, adjust_superblock_free_blocks, adjust_superblock_free_inodes, allocate_ufs_allocation, allocate_ufs_block, allocate_ufs_fragments, allocate_ufs_inode, build_ufs_pointer_tree, cg_block_offset, clear_ufs_inode, collect_indirect_data_blocks, collect_indirect_pointer_blocks, detect_ufs, free_ufs_allocation, free_ufs_block, free_ufs_inode, i32, initialize_ufs_inode, is_frag_free, is_ufs_inode_used, read_cg_block, read_ufs_file, read_ufs_inode, read_ufs_pointer_block, set_frag_state, set_ufs_inode_state, u16, u32, ufs_allocation_byte_sizes, ufs_blkstofrags, ufs_cgbase, ufs_cgdmin, ufs_cgimin, ufs_cgstart, ufs_cgtod, ufs_file_type, ufs_fragroundup, ufs_fsbtobytes, ufs_inode_data_blocks, ufs_inode_offset, ufs_inode_pointer_blocks, ufs_is_directory, ufs_is_symlink, ufs_itod, ufs_itog, ufs_itoo, ufs_path_components, write_cg_block, write_ufs_block_lists, write_ufs_inode_blocks, write_ufs_inode_mode, write_ufs_inode_nlink, write_ufs_inode_size, write_ufs_inode_time, write_ufs_inode_times, write_ufs_inode_uid_gid, write_ufs_pointer_block


def split_ufs_parent_path(path: str) -> tuple[str, str]:
    parts = ufs_path_components(path)
    if not parts:
        raise SystemExit('error: path must not be the filesystem root')
    name = parts[-1]
    if name in {'.', '..'}:
        raise SystemExit('error: refusing to mutate special directory entries . or ..')
    try:
        name.encode('ascii')
    except UnicodeEncodeError as error:
        raise SystemExit(f'error: UFS path component {name!r} is not ASCII') from error
    if len(name) > 255:
        raise SystemExit(f'error: UFS path component {name!r} exceeds the 255-byte limit')
    parent_path = '/' if len(parts) == 1 else '/' + '/'.join(parts[:-1])
    return parent_path, name


def resolve_ufs_parent(image: ImageBuffer, filesystem: FilesystemCandidate, path: str) -> tuple[str, str, int, dict[str, int | list[int]]]:
    parent_path, name = split_ufs_parent_path(path)
    resolved_parent = resolve_ufs_path(image, filesystem, parent_path)
    if resolved_parent is None:
        raise SystemExit(f'error: could not resolve parent path {parent_path} inside the ufs filesystem')
    parent_inode_number, parent_inode = resolved_parent
    if not ufs_is_directory(parent_inode):
        raise SystemExit(f'error: parent path {parent_path} is not a UFS directory')
    return parent_path, name, parent_inode_number, parent_inode


def build_ufs_directory_block(self_inode_number: int, parent_inode_number: int) -> bytes:
    dot = encode_ufs_directory_entry(self_inode_number, '.', ufs_dirsiz('.'))
    dotdot = encode_ufs_directory_entry(parent_inode_number, '..', UFS_DIRBLKSIZ - len(dot))
    return dot + dotdot


def iter_ufs_directory_entries(image: ImageBuffer, filesystem: FilesystemCandidate, inode: dict[str, int | list[int]]) -> list[dict[str, int | str]]:
    fs = filesystem.details
    entries: list[dict[str, int | str]] = []
    directory_bytes = read_ufs_file(image, filesystem.start_offset, fs, inode)
    for record in iter_ufs_directory_records(directory_bytes, int(inode['size'])):
        if record.inode != 0 and 0 < record.name_length <= 255:
            entry: dict[str, int | str] = {'name': record.name, 'inode': record.inode}
            child_inode = read_ufs_inode(image, filesystem.start_offset, fs, record.inode)
            if child_inode is not None:
                entry['size'] = int(child_inode['size'])
            entries.append(entry)
    entries.sort(key=lambda item: str(item['name']))
    return entries


def list_ufs_root(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[dict[str, int | str]]:
    root_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, UFS_ROOT_INODE)
    if root_inode is None:
        return []
    return iter_ufs_directory_entries(image, filesystem, root_inode)


def resolve_ufs_path(image: ImageBuffer, filesystem: FilesystemCandidate, path: str) -> tuple[int, dict[str, int | list[int]]] | None:
    current_inode_number = UFS_ROOT_INODE
    current_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, current_inode_number)
    if current_inode is None:
        return None
    parts = [part for part in path.split('/') if part]
    if not parts:
        return current_inode_number, current_inode
    for part in parts:
        next_inode_number = None
        for entry in iter_ufs_directory_entries(image, filesystem, current_inode):
            if entry['name'] == part:
                next_inode_number = int(entry['inode'])
                break
        if next_inode_number is None:
            return None
        current_inode_number = next_inode_number
        current_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, current_inode_number)
        if current_inode is None:
            return None
    return current_inode_number, current_inode


def read_ufs_path_bytes(image: ImageBuffer, filesystem: FilesystemCandidate, target_path: str) -> tuple[int, dict[str, int | list[int]], bytes]:
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: could not resolve {target_path} inside the ufs filesystem')
    inode_number, inode = resolved
    return inode_number, inode, read_ufs_file(image, filesystem.start_offset, filesystem.details, inode)


def apply_ufs_inplace_replacement(image: bytearray, filesystem: FilesystemCandidate, target_path: str, new_data: bytes) -> dict[str, int | str]:
    inode_number, inode, old_data = read_ufs_path_bytes(image, filesystem, target_path)
    block_size = int(filesystem.details['bsize'])
    data_blocks = ufs_inode_data_blocks(image, filesystem, inode)
    capacity = len(data_blocks) * block_size
    if capacity <= 0:
        raise SystemExit(f'error: ufs file {target_path} has no writable allocated blocks')
    if len(new_data) > capacity:
        raise SystemExit(f'error: replacement for {target_path} exceeds its allocated UFS capacity ({len(new_data)} > {capacity})')

    remaining = new_data
    for fs_block in data_blocks:
        block_offset = filesystem.start_offset + ufs_fsbtobytes(filesystem.details, int(fs_block))
        chunk = remaining[:block_size]
        image[block_offset:block_offset + block_size] = chunk.ljust(block_size, b'\0')
        remaining = remaining[block_size:]
        if not remaining:
            break

    write_ufs_inode_size(image, filesystem, inode_number, len(new_data))
    return {
        'target_path': target_path,
        'inode': inode_number,
        'old_size': len(old_data),
        'new_size': len(new_data),
        'capacity': capacity,
    }


def detect_ufs(image: ImageBuffer) -> list[FilesystemCandidate]:
    candidates: list[FilesystemCandidate] = []
    for fs_start in range(0, max(0, len(image) - (UFS_SB_OFFSET + UFS_FS_MAGIC_OFFSET + 4)) + 1, SECTOR_SIZE):
        super_offset = fs_start + UFS_SB_OFFSET
        if super_offset + UFS_SB_SIZE > len(image):
            break
        if u32(image, super_offset + UFS_FS_MAGIC_OFFSET) != UFS_MAGIC:
            continue
        block_size = u32(image, super_offset + UFS_FS_BSIZE_OFFSET)
        fragment_size = u32(image, super_offset + UFS_FS_FSIZE_OFFSET)
        inodes_per_block = u32(image, super_offset + UFS_FS_INOPB_OFFSET)
        inodes_per_group = u32(image, super_offset + UFS_FS_IPG_OFFSET)
        fragments_per_group = u32(image, super_offset + UFS_FS_FPG_OFFSET)
        if block_size < 4096 or block_size > UFS_SB_SIZE:
            continue
        if fragment_size < SECTOR_SIZE or fragment_size > block_size:
            continue
        if inodes_per_block == 0 or inodes_per_group == 0 or fragments_per_group == 0:
            continue
        candidates.append(
            FilesystemCandidate(
                kind='ufs',
                start_offset=fs_start,
                super_offset=super_offset,
                block_size=block_size,
                details={
                    'bsize': block_size,
                    'fsize': fragment_size,
                    'frag': u32(image, super_offset + UFS_FS_FRAG_OFFSET),
                    'ipg': inodes_per_group,
                    'fpg': fragments_per_group,
                    'inopb': inodes_per_block,
                    'fsbtodb': u32(image, super_offset + UFS_FS_FSBTODB_OFFSET),
                    'cgoffset': u32(image, super_offset + UFS_FS_CGOFFSET_OFFSET),
                    'cgmask': u32(image, super_offset + UFS_FS_CGMASK_OFFSET),
                    'cblkno': u32(image, super_offset + UFS_FS_CBLKNO_OFFSET),
                    'iblkno': u32(image, super_offset + UFS_FS_IBLKNO_OFFSET),
                    'dblkno': u32(image, super_offset + UFS_FS_DBLKNO_OFFSET),
                    'ncg': u32(image, super_offset + UFS_FS_NCG_OFFSET),
                    'minfree': u32(image, super_offset + UFS_FS_MINFREE_OFFSET),
                    'fragshift': i32(image, super_offset + 96),
                    'nindir': u32(image, super_offset + UFS_FS_NINDIR_OFFSET),
                },
            )
        )
    return candidates


def ufs_fsbtobytes(fs: dict[str, Any], fs_block: int) -> int:
    return (fs_block << int(fs['fsbtodb'])) * SECTOR_SIZE


def ufs_itoo(fs: dict[str, Any], inode_number: int) -> int:
    return inode_number % int(fs['inopb'])


def ufs_itog(fs: dict[str, Any], inode_number: int) -> int:
    return inode_number // int(fs['ipg'])


def ufs_blkstofrags(fs: dict[str, Any], blocks: int) -> int:
    return blocks << int(fs['fragshift'])


def ufs_cgbase(fs: dict[str, Any], cg: int) -> int:
    return int(fs['fpg']) * cg


def ufs_cgstart(fs: dict[str, Any], cg: int) -> int:
    return ufs_cgbase(fs, cg) + int(fs['cgoffset']) * (cg & ~int(fs['cgmask']))


def ufs_cgimin(fs: dict[str, Any], cg: int) -> int:
    return ufs_cgstart(fs, cg) + int(fs['iblkno'])


def ufs_itod(fs: dict[str, Any], inode_number: int) -> int:
    group = ufs_itog(fs, inode_number)
    return ufs_cgimin(fs, group) + ufs_blkstofrags(fs, ((inode_number % int(fs['ipg'])) // int(fs['inopb'])))


def ufs_cgtod(fs: dict[str, Any], cg: int) -> int:
    return ufs_cgstart(fs, cg) + int(fs['cblkno'])


def ufs_cgdmin(fs: dict[str, Any], cg: int) -> int:
    return ufs_cgstart(fs, cg) + int(fs['dblkno'])


def cg_block_offset(filesystem: FilesystemCandidate, cg: int) -> int:
    return filesystem.start_offset + ufs_fsbtobytes(filesystem.details, ufs_cgtod(filesystem.details, cg))


def read_ufs_inode(image: ImageBuffer, fs_start: int, fs: dict[str, Any], inode_number: int) -> dict[str, int | list[int]] | None:
    inode_block = ufs_itod(fs, inode_number)
    inode_offset = fs_start + ufs_fsbtobytes(fs, inode_block) + (ufs_itoo(fs, inode_number) * UFS_DINODE_SIZE)
    if inode_offset < fs_start or inode_offset + UFS_DINODE_SIZE > len(image):
        return None
    raw = image[inode_offset:inode_offset + UFS_DINODE_SIZE]
    direct_blocks = [u32(raw, UFS_DI_DB_OFFSET + (index * 4)) for index in range(UFS_NDADDR)]
    indirect_blocks = [u32(raw, UFS_DI_IB_OFFSET + (index * 4)) for index in range(3)]
    size = int.from_bytes(raw[UFS_DI_SIZE_OFFSET:UFS_DI_SIZE_OFFSET + 8], 'little', signed=False)
    return {
        'mode': u32(raw, UFS_DI_MODE_OFFSET),
        'nlink': u16(raw, UFS_DI_NLINK_OFFSET),
        'uid': u32(raw, UFS_DI_UID_OFFSET),
        'gid': u32(raw, UFS_DI_GID_OFFSET),
        'atime': u32(raw, UFS_DI_ATIME_OFFSET),
        'mtime': u32(raw, UFS_DI_MTIME_OFFSET),
        'ctime': u32(raw, UFS_DI_CTIME_OFFSET),
        'size': size,
        'direct_blocks': direct_blocks,
        'indirect_blocks': indirect_blocks,
        'blocks': u32(raw, UFS_DI_BLOCKS_OFFSET),
    }


def ufs_file_type(mode: int) -> int:
    return mode & UFS_IFMT


def ufs_is_directory(inode: dict[str, int | list[int]]) -> bool:
    return ufs_file_type(int(inode['mode'])) == UFS_IFDIR


def ufs_is_symlink(inode: dict[str, int | list[int]]) -> bool:
    return ufs_file_type(int(inode['mode'])) == UFS_IFLNK


def ufs_fragroundup(fs: dict[str, Any], size: int) -> int:
    fragment_size = int(fs['fsize'])
    if size <= 0:
        return 0
    return ((size + fragment_size - 1) // fragment_size) * fragment_size


def ufs_allocation_byte_sizes(fs: dict[str, Any], size: int) -> list[int]:
    if size <= 0:
        return []
    block_size = int(fs['bsize'])
    allocations: list[int] = []
    remaining = size
    while remaining > 0:
        logical_bytes = min(block_size, remaining)
        if logical_bytes == block_size:
            allocations.append(block_size)
        else:
            allocations.append(ufs_fragroundup(fs, logical_bytes))
        remaining -= block_size
    return allocations


def ufs_path_components(path: str) -> list[str]:
    return [part for part in path.split('/') if part]


def split_ufs_parent_path(path: str) -> tuple[str, str]:
    parts = ufs_path_components(path)
    if not parts:
        raise SystemExit('error: path must not be the filesystem root')
    name = parts[-1]
    if name in {'.', '..'}:
        raise SystemExit('error: refusing to mutate special directory entries . or ..')
    try:
        name.encode('ascii')
    except UnicodeEncodeError as error:
        raise SystemExit(f'error: UFS path component {name!r} is not ASCII') from error
    if len(name) > 255:
        raise SystemExit(f'error: UFS path component {name!r} exceeds the 255-byte limit')
    parent_path = '/' if len(parts) == 1 else '/' + '/'.join(parts[:-1])
    return parent_path, name


def resolve_ufs_parent(image: bytes, filesystem: FilesystemCandidate, path: str) -> tuple[str, str, int, dict[str, int | list[int]]]:
    parent_path, name = split_ufs_parent_path(path)
    resolved_parent = resolve_ufs_path(image, filesystem, parent_path)
    if resolved_parent is None:
        raise SystemExit(f'error: could not resolve parent path {parent_path} inside the ufs filesystem')
    parent_inode_number, parent_inode = resolved_parent
    if not ufs_is_directory(parent_inode):
        raise SystemExit(f'error: parent path {parent_path} is not a UFS directory')
    return parent_path, name, parent_inode_number, parent_inode


def build_ufs_directory_block(self_inode_number: int, parent_inode_number: int) -> bytes:
    dot = encode_ufs_directory_entry(self_inode_number, '.', ufs_dirsiz('.'))
    dotdot = encode_ufs_directory_entry(parent_inode_number, '..', UFS_DIRBLKSIZ - len(dot))
    return dot + dotdot


def read_ufs_pointer_block(image: ImageBuffer, filesystem: FilesystemCandidate, fs_block: int) -> list[int]:
    block_offset = filesystem.start_offset + ufs_fsbtobytes(filesystem.details, fs_block)
    block_size = int(filesystem.details['bsize'])
    raw = image[block_offset:block_offset + block_size]
    return [u32(raw, index * 4) for index in range(int(filesystem.details['nindir']))]


def collect_indirect_data_blocks(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    fs_block: int,
    levels: int,
    max_blocks: int | None = None,
) -> list[int]:
    if fs_block == 0 or levels <= 0 or max_blocks == 0:
        return []
    blocks: list[int] = []
    for pointer in read_ufs_pointer_block(image, filesystem, fs_block):
        if pointer == 0:
            continue
        if levels == 1:
            blocks.append(pointer)
        else:
            blocks.extend(
                collect_indirect_data_blocks(
                    image,
                    filesystem,
                    pointer,
                    levels - 1,
                    None if max_blocks is None else max(0, max_blocks - len(blocks)),
                )
            )
        if max_blocks is not None and len(blocks) >= max_blocks:
            return blocks[:max_blocks]
    return blocks


def collect_indirect_pointer_blocks(image: ImageBuffer, filesystem: FilesystemCandidate, fs_block: int, levels: int) -> list[int]:
    if fs_block == 0 or levels <= 0:
        return []
    blocks = [fs_block]
    if levels == 1:
        return blocks
    for child in read_ufs_pointer_block(image, filesystem, fs_block):
        if child == 0:
            continue
        blocks.extend(collect_indirect_pointer_blocks(image, filesystem, child, levels - 1))
    return blocks


def ufs_inode_data_blocks(image: ImageBuffer, filesystem: FilesystemCandidate, inode: dict[str, int | list[int]]) -> list[int]:
    direct_blocks = inode['direct_blocks']
    indirect_blocks = inode['indirect_blocks']
    if not isinstance(direct_blocks, list) or not isinstance(indirect_blocks, list):
        return []
    block_size = int(filesystem.details['bsize'])
    needed_blocks = 0 if int(inode['size']) == 0 else (int(inode['size']) + block_size - 1) // block_size
    blocks: list[int] = []
    for fs_block in direct_blocks:
        if int(fs_block) == 0:
            continue
        blocks.append(int(fs_block))
        if len(blocks) >= needed_blocks:
            return blocks[:needed_blocks]
    for levels, root_block in enumerate(indirect_blocks, start=1):
        blocks.extend(
            collect_indirect_data_blocks(
                image,
                filesystem,
                int(root_block),
                levels,
                max_blocks=max(0, needed_blocks - len(blocks)),
            )
        )
        if len(blocks) >= needed_blocks:
            return blocks[:needed_blocks]
    return blocks[:needed_blocks]


def ufs_inode_pointer_blocks(image: ImageBuffer, filesystem: FilesystemCandidate, inode: dict[str, int | list[int]]) -> list[int]:
    indirect_blocks = inode['indirect_blocks']
    if not isinstance(indirect_blocks, list):
        return []
    blocks: list[int] = []
    for levels, root_block in enumerate(indirect_blocks, start=1):
        blocks.extend(collect_indirect_pointer_blocks(image, filesystem, int(root_block), levels))
    return blocks


def read_ufs_file(image: ImageBuffer, fs_start: int, fs: dict[str, Any], inode: dict[str, int | list[int]]) -> bytes:
    filesystem = FilesystemCandidate(kind='ufs', start_offset=fs_start, super_offset=fs_start + UFS_SB_OFFSET, block_size=int(fs['bsize']), details=fs)
    size = int(inode['size'])
    block_size = int(fs['bsize'])
    data = bytearray()
    for fs_block in ufs_inode_data_blocks(image, filesystem, inode):
        block_offset = fs_start + ufs_fsbtobytes(fs, fs_block)
        data.extend(image[block_offset:block_offset + block_size])
        if len(data) >= size:
            break
    return bytes(data[:size])


def iter_ufs_directory_entries(image: ImageBuffer, filesystem: FilesystemCandidate, inode: dict[str, int | list[int]]) -> list[dict[str, int | str]]:
    fs = filesystem.details
    entries: list[dict[str, int | str]] = []
    directory_bytes = read_ufs_file(image, filesystem.start_offset, fs, inode)
    for record in iter_ufs_directory_records(directory_bytes, int(inode['size'])):
        if record.inode != 0 and 0 < record.name_length <= 255:
            entry: dict[str, int | str] = {'name': record.name, 'inode': record.inode}
            child_inode = read_ufs_inode(image, filesystem.start_offset, fs, record.inode)
            if child_inode is not None:
                entry['size'] = int(child_inode['size'])
            entries.append(entry)
    entries.sort(key=lambda item: str(item['name']))
    return entries


def list_ufs_root(image: ImageBuffer, filesystem: FilesystemCandidate) -> list[dict[str, int | str]]:
    root_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, UFS_ROOT_INODE)
    if root_inode is None:
        return []
    return iter_ufs_directory_entries(image, filesystem, root_inode)


def resolve_ufs_path(image: ImageBuffer, filesystem: FilesystemCandidate, path: str) -> tuple[int, dict[str, int | list[int]]] | None:
    current_inode_number = UFS_ROOT_INODE
    current_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, current_inode_number)
    if current_inode is None:
        return None
    parts = [part for part in path.split('/') if part]
    if not parts:
        return current_inode_number, current_inode
    for part in parts:
        next_inode_number = None
        for entry in iter_ufs_directory_entries(image, filesystem, current_inode):
            if entry['name'] == part:
                next_inode_number = int(entry['inode'])
                break
        if next_inode_number is None:
            return None
        current_inode_number = next_inode_number
        current_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, current_inode_number)
        if current_inode is None:
            return None
    return current_inode_number, current_inode


def read_ufs_path_bytes(image: ImageBuffer, filesystem: FilesystemCandidate, target_path: str) -> tuple[int, dict[str, int | list[int]], bytes]:
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: could not resolve {target_path} inside the ufs filesystem')
    inode_number, inode = resolved
    return inode_number, inode, read_ufs_file(image, filesystem.start_offset, filesystem.details, inode)


def ufs_inode_offset(filesystem: FilesystemCandidate, inode_number: int) -> int:
    inode_block = ufs_itod(filesystem.details, inode_number)
    return filesystem.start_offset + ufs_fsbtobytes(filesystem.details, inode_block) + (ufs_itoo(filesystem.details, inode_number) * UFS_DINODE_SIZE)


def clear_ufs_inode(image: bytearray, filesystem: FilesystemCandidate, inode_number: int) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    image[inode_offset:inode_offset + UFS_DINODE_SIZE] = b'\0' * UFS_DINODE_SIZE


def write_ufs_inode_time(image: bytearray, inode_offset: int, field_offset: int, timestamp: int) -> None:
    image[inode_offset + field_offset:inode_offset + field_offset + 4] = timestamp.to_bytes(4, 'little', signed=False)
    image[inode_offset + field_offset + 4:inode_offset + field_offset + 8] = (0).to_bytes(4, 'little', signed=False)


def initialize_ufs_inode(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    mode: int,
    uid: int = 0,
    gid: int = 0,
    nlink: int = 1,
    timestamp: int = 0,
) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    clear_ufs_inode(image, filesystem, inode_number)
    image[inode_offset + UFS_DI_NLINK_OFFSET:inode_offset + UFS_DI_NLINK_OFFSET + 2] = nlink.to_bytes(2, 'little', signed=False)
    image[inode_offset + UFS_DI_SUID_OFFSET:inode_offset + UFS_DI_SUID_OFFSET + 2] = uid.to_bytes(2, 'little', signed=False)
    image[inode_offset + UFS_DI_SGID_OFFSET:inode_offset + UFS_DI_SGID_OFFSET + 2] = gid.to_bytes(2, 'little', signed=False)
    write_ufs_inode_time(image, inode_offset, UFS_DI_ATIME_OFFSET, timestamp)
    write_ufs_inode_time(image, inode_offset, UFS_DI_MTIME_OFFSET, timestamp)
    write_ufs_inode_time(image, inode_offset, UFS_DI_CTIME_OFFSET, timestamp)
    image[inode_offset + UFS_DI_MODE_OFFSET:inode_offset + UFS_DI_MODE_OFFSET + 4] = mode.to_bytes(4, 'little', signed=False)
    image[inode_offset + UFS_DI_UID_OFFSET:inode_offset + UFS_DI_UID_OFFSET + 4] = uid.to_bytes(4, 'little', signed=False)
    image[inode_offset + UFS_DI_GID_OFFSET:inode_offset + UFS_DI_GID_OFFSET + 4] = gid.to_bytes(4, 'little', signed=False)
    image[inode_offset + UFS_DI_EFTFLAG_OFFSET:inode_offset + UFS_DI_EFTFLAG_OFFSET + 4] = UFS_EFT_MAGIC.to_bytes(4, 'little', signed=False)


def write_ufs_inode_size(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, size: int) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    image[inode_offset + UFS_DI_SIZE_OFFSET:inode_offset + UFS_DI_SIZE_OFFSET + 8] = size.to_bytes(8, 'little', signed=False)


def write_ufs_inode_nlink(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, nlink: int) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    image[inode_offset + UFS_DI_NLINK_OFFSET:inode_offset + UFS_DI_NLINK_OFFSET + 2] = nlink.to_bytes(2, 'little', signed=False)


def write_ufs_inode_blocks(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, sectors: int) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    image[inode_offset + UFS_DI_BLOCKS_OFFSET:inode_offset + UFS_DI_BLOCKS_OFFSET + 4] = sectors.to_bytes(4, 'little', signed=False)


def write_ufs_inode_mode(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, mode: int) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    image[inode_offset + UFS_DI_MODE_OFFSET:inode_offset + UFS_DI_MODE_OFFSET + 4] = mode.to_bytes(4, 'little', signed=False)


def write_ufs_inode_uid_gid(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, uid: int, gid: int) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    image[inode_offset + UFS_DI_SUID_OFFSET:inode_offset + UFS_DI_SUID_OFFSET + 2] = uid.to_bytes(2, 'little', signed=False)
    image[inode_offset + UFS_DI_SGID_OFFSET:inode_offset + UFS_DI_SGID_OFFSET + 2] = gid.to_bytes(2, 'little', signed=False)
    image[inode_offset + UFS_DI_UID_OFFSET:inode_offset + UFS_DI_UID_OFFSET + 4] = uid.to_bytes(4, 'little', signed=False)
    image[inode_offset + UFS_DI_GID_OFFSET:inode_offset + UFS_DI_GID_OFFSET + 4] = gid.to_bytes(4, 'little', signed=False)


def write_ufs_inode_times(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    *,
    atime: int | None = None,
    mtime: int | None = None,
    ctime: int | None = None,
) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    if atime is not None:
        write_ufs_inode_time(image, inode_offset, UFS_DI_ATIME_OFFSET, atime)
    if mtime is not None:
        write_ufs_inode_time(image, inode_offset, UFS_DI_MTIME_OFFSET, mtime)
    if ctime is not None:
        write_ufs_inode_time(image, inode_offset, UFS_DI_CTIME_OFFSET, ctime)


def write_ufs_block_lists(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    direct_blocks: list[int],
    indirect_blocks: list[int],
) -> None:
    inode_offset = ufs_inode_offset(filesystem, inode_number)
    for index in range(UFS_NDADDR):
        value = int(direct_blocks[index]) if index < len(direct_blocks) else 0
        offset = inode_offset + UFS_DI_DB_OFFSET + (index * 4)
        image[offset:offset + 4] = value.to_bytes(4, 'little', signed=False)
    for index in range(3):
        value = int(indirect_blocks[index]) if index < len(indirect_blocks) else 0
        offset = inode_offset + UFS_DI_IB_OFFSET + (index * 4)
        image[offset:offset + 4] = value.to_bytes(4, 'little', signed=False)


def is_frag_free(cg_bytes: bytes, frag_index: int) -> bool:
    byte = cg_bytes[UFS_CG_FREE_OFFSET + (frag_index // NBBY)]
    return bool(byte & (1 << (frag_index % NBBY)))


def set_frag_state(cg_bytes: bytearray, frag_index: int, free: bool) -> None:
    byte_offset = UFS_CG_FREE_OFFSET + (frag_index // NBBY)
    mask = 1 << (frag_index % NBBY)
    if free:
        cg_bytes[byte_offset] |= mask
    else:
        cg_bytes[byte_offset] &= ~mask & 0xFF


def read_cg_block(image: ImageBuffer, filesystem: FilesystemCandidate, cg: int) -> bytearray:
    offset = cg_block_offset(filesystem, cg)
    block_size = int(filesystem.details['bsize'])
    return bytearray(image[offset:offset + block_size])


def write_cg_block(image: bytearray, filesystem: FilesystemCandidate, cg: int, cg_bytes: bytearray) -> None:
    offset = cg_block_offset(filesystem, cg)
    image[offset:offset + len(cg_bytes)] = cg_bytes


def adjust_superblock_free_blocks(image: bytearray, filesystem: FilesystemCandidate, delta: int) -> None:
    super_offset = filesystem.super_offset
    current = u32(image, super_offset + UFS_FS_CSTOTAL_NBFREE_OFFSET)
    image[super_offset + UFS_FS_CSTOTAL_NBFREE_OFFSET:super_offset + UFS_FS_CSTOTAL_NBFREE_OFFSET + 4] = (current + delta).to_bytes(4, 'little', signed=False)


def adjust_superblock_free_inodes(image: bytearray, filesystem: FilesystemCandidate, delta: int) -> None:
    super_offset = filesystem.super_offset
    current = u32(image, super_offset + UFS_FS_CSTOTAL_NIFREE_OFFSET)
    image[super_offset + UFS_FS_CSTOTAL_NIFREE_OFFSET:super_offset + UFS_FS_CSTOTAL_NIFREE_OFFSET + 4] = (current + delta).to_bytes(4, 'little', signed=False)


def adjust_superblock_directory_count(image: bytearray, filesystem: FilesystemCandidate, delta: int) -> None:
    super_offset = filesystem.super_offset
    current = u32(image, super_offset + UFS_FS_CSTOTAL_NDIR_OFFSET)
    image[super_offset + UFS_FS_CSTOTAL_NDIR_OFFSET:super_offset + UFS_FS_CSTOTAL_NDIR_OFFSET + 4] = (current + delta).to_bytes(4, 'little', signed=False)


def adjust_cg_free_blocks(cg_bytes: bytearray, delta: int) -> None:
    current = u32(cg_bytes, UFS_CG_CS_NBFREE_OFFSET)
    cg_bytes[UFS_CG_CS_NBFREE_OFFSET:UFS_CG_CS_NBFREE_OFFSET + 4] = (current + delta).to_bytes(4, 'little', signed=False)


def adjust_cg_free_inodes(cg_bytes: bytearray, delta: int) -> None:
    current = u32(cg_bytes, UFS_CG_CS_NIFREE_OFFSET)
    cg_bytes[UFS_CG_CS_NIFREE_OFFSET:UFS_CG_CS_NIFREE_OFFSET + 4] = (current + delta).to_bytes(4, 'little', signed=False)


def adjust_cg_directory_count(cg_bytes: bytearray, delta: int) -> None:
    current = u32(cg_bytes, UFS_CG_CS_NDIR_OFFSET)
    cg_bytes[UFS_CG_CS_NDIR_OFFSET:UFS_CG_CS_NDIR_OFFSET + 4] = (current + delta).to_bytes(4, 'little', signed=False)


def is_ufs_inode_used(cg_bytes: bytes, inode_index: int) -> bool:
    byte = cg_bytes[UFS_CG_IUSED_OFFSET + (inode_index // NBBY)]
    return bool(byte & (1 << (inode_index % NBBY)))


def set_ufs_inode_state(cg_bytes: bytearray, inode_index: int, used: bool) -> None:
    byte_offset = UFS_CG_IUSED_OFFSET + (inode_index // NBBY)
    mask = 1 << (inode_index % NBBY)
    if used:
        cg_bytes[byte_offset] |= mask
    else:
        cg_bytes[byte_offset] &= ~mask & 0xFF


def allocate_ufs_inode(
    image: bytearray,
    filesystem: FilesystemCandidate,
    preferred_inode: int | None = None,
    directory: bool = False,
) -> int:
    fs = filesystem.details
    total_cg = int(fs['ncg'])
    start_cg = 0 if preferred_inode is None else ufs_itog(fs, preferred_inode)
    preferred_local_inode = None if preferred_inode is None else preferred_inode % int(fs['ipg'])
    for attempt in range(total_cg):
        cg = (start_cg + attempt) % total_cg
        cg_bytes = read_cg_block(image, filesystem, cg)
        if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
            continue
        if u32(cg_bytes, UFS_CG_CS_NIFREE_OFFSET) == 0:
            continue

        local_inode = None
        if attempt == 0 and preferred_local_inode is not None and not is_ufs_inode_used(cg_bytes, preferred_local_inode):
            local_inode = preferred_local_inode
        else:
            start_inode = u32(cg_bytes, UFS_CG_IROTOR_OFFSET) % int(fs['ipg'])
            for offset in range(int(fs['ipg'])):
                candidate = (start_inode + offset) % int(fs['ipg'])
                if not is_ufs_inode_used(cg_bytes, candidate):
                    local_inode = candidate
                    break
        if local_inode is None:
            continue

        set_ufs_inode_state(cg_bytes, local_inode, used=True)
        cg_bytes[UFS_CG_IROTOR_OFFSET:UFS_CG_IROTOR_OFFSET + 4] = local_inode.to_bytes(4, 'little', signed=False)
        adjust_cg_free_inodes(cg_bytes, -1)
        if directory:
            adjust_cg_directory_count(cg_bytes, 1)
        write_cg_block(image, filesystem, cg, cg_bytes)
        adjust_superblock_free_inodes(image, filesystem, -1)
        if directory:
            adjust_superblock_directory_count(image, filesystem, 1)
        return (cg * int(fs['ipg'])) + local_inode
    raise SystemExit('error: no free UFS inodes remain for allocation')


def free_ufs_inode(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, directory: bool = False) -> None:
    fs = filesystem.details
    cg = ufs_itog(fs, inode_number)
    local_inode = inode_number % int(fs['ipg'])
    cg_bytes = read_cg_block(image, filesystem, cg)
    if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
        raise SystemExit(f'error: invalid cylinder group {cg} while freeing UFS inode {inode_number}')
    if not is_ufs_inode_used(cg_bytes, local_inode):
        raise SystemExit(f'error: UFS inode {inode_number} is already free')
    set_ufs_inode_state(cg_bytes, local_inode, used=False)
    adjust_cg_free_inodes(cg_bytes, 1)
    if directory:
        adjust_cg_directory_count(cg_bytes, -1)
    write_cg_block(image, filesystem, cg, cg_bytes)
    adjust_superblock_free_inodes(image, filesystem, 1)
    if directory:
        adjust_superblock_directory_count(image, filesystem, -1)


def allocate_ufs_block(image: bytearray, filesystem: FilesystemCandidate, inode_number: int) -> int:
    fs = filesystem.details
    start_cg = ufs_itog(fs, inode_number)
    total_cg = int(fs['ncg'])
    frags_per_block = int(fs['frag'])
    block_size = int(fs['bsize'])
    for attempt in range(total_cg):
        cg = (start_cg + attempt) % total_cg
        cg_bytes = read_cg_block(image, filesystem, cg)
        if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
            continue
        cg_ndblk = u32(cg_bytes, UFS_CG_NDBLK_OFFSET)
        data_start_frag = ufs_cgdmin(fs, cg) % int(fs['fpg'])
        for frag_index in range(data_start_frag, cg_ndblk - frags_per_block + 1, frags_per_block):
            if all(is_frag_free(cg_bytes, frag_index + frag_offset) for frag_offset in range(frags_per_block)):
                for frag_offset in range(frags_per_block):
                    set_frag_state(cg_bytes, frag_index + frag_offset, free=False)
                adjust_cg_free_blocks(cg_bytes, -1)
                write_cg_block(image, filesystem, cg, cg_bytes)
                adjust_superblock_free_blocks(image, filesystem, -1)
                fs_block = ufs_cgbase(fs, cg) + frag_index
                block_offset = filesystem.start_offset + ufs_fsbtobytes(fs, fs_block)
                image[block_offset:block_offset + block_size] = b'\0' * block_size
                return fs_block
    raise SystemExit('error: no free UFS blocks remain for allocation')


def allocate_ufs_fragments(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, allocation_bytes: int) -> int:
    fs = filesystem.details
    fragment_size = int(fs['fsize'])
    frags_needed = allocation_bytes // fragment_size
    if frags_needed <= 0 or allocation_bytes >= int(fs['bsize']):
        raise SystemExit(f'error: invalid UFS fragment allocation request for {allocation_bytes} bytes')
    start_cg = ufs_itog(fs, inode_number)
    total_cg = int(fs['ncg'])
    frags_per_block = int(fs['frag'])
    for attempt in range(total_cg):
        cg = (start_cg + attempt) % total_cg
        cg_bytes = read_cg_block(image, filesystem, cg)
        if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
            continue
        cg_ndblk = u32(cg_bytes, UFS_CG_NDBLK_OFFSET)
        data_start_frag = ufs_cgdmin(fs, cg) % int(fs['fpg'])
        for frag_index in range(data_start_frag, cg_ndblk - frags_per_block + 1, frags_per_block):
            if not all(is_frag_free(cg_bytes, frag_index + frag_offset) for frag_offset in range(frags_per_block)):
                continue
            for frag_offset in range(frags_needed):
                set_frag_state(cg_bytes, frag_index + frag_offset, free=False)
            adjust_cg_free_blocks(cg_bytes, -1)
            write_cg_block(image, filesystem, cg, cg_bytes)
            adjust_superblock_free_blocks(image, filesystem, -1)
            fs_block = ufs_cgbase(fs, cg) + frag_index
            block_offset = filesystem.start_offset + ufs_fsbtobytes(fs, fs_block)
            image[block_offset:block_offset + allocation_bytes] = b'\0' * allocation_bytes
            return fs_block
    raise SystemExit('error: no free UFS fragments remain for allocation')


def free_ufs_block(image: bytearray, filesystem: FilesystemCandidate, fs_block: int) -> None:
    fs = filesystem.details
    frags_per_group = int(fs['fpg'])
    frags_per_block = int(fs['frag'])
    cg = fs_block // frags_per_group
    frag_index = fs_block % frags_per_group
    cg_bytes = read_cg_block(image, filesystem, cg)
    if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
        raise SystemExit(f'error: invalid cylinder group {cg} while freeing UFS block {fs_block}')
    for frag_offset in range(frags_per_block):
        set_frag_state(cg_bytes, frag_index + frag_offset, free=True)
    adjust_cg_free_blocks(cg_bytes, 1)
    write_cg_block(image, filesystem, cg, cg_bytes)
    adjust_superblock_free_blocks(image, filesystem, 1)


def allocate_ufs_allocation(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, allocation_bytes: int) -> int:
    if allocation_bytes <= 0:
        raise SystemExit('error: UFS allocation size must be positive')
    if allocation_bytes == int(filesystem.details['bsize']):
        return allocate_ufs_block(image, filesystem, inode_number)
    return allocate_ufs_fragments(image, filesystem, inode_number, allocation_bytes)


def free_ufs_allocation(image: bytearray, filesystem: FilesystemCandidate, fs_block: int, allocation_bytes: int) -> None:
    if allocation_bytes <= 0:
        return
    fs = filesystem.details
    if allocation_bytes == int(fs['bsize']):
        free_ufs_block(image, filesystem, fs_block)
        return
    fragment_size = int(fs['fsize'])
    frags_to_free = allocation_bytes // fragment_size
    frags_per_group = int(fs['fpg'])
    frags_per_block = int(fs['frag'])
    cg = fs_block // frags_per_group
    frag_index = fs_block % frags_per_group
    cg_bytes = read_cg_block(image, filesystem, cg)
    if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
        raise SystemExit(f'error: invalid cylinder group {cg} while freeing UFS allocation at block {fs_block}')
    for frag_offset in range(frags_to_free):
        set_frag_state(cg_bytes, frag_index + frag_offset, free=True)
    block_base = frag_index - (frag_index % frags_per_block)
    if all(is_frag_free(cg_bytes, block_base + frag_offset) for frag_offset in range(frags_per_block)):
        adjust_cg_free_blocks(cg_bytes, 1)
        adjust_superblock_free_blocks(image, filesystem, 1)
    write_cg_block(image, filesystem, cg, cg_bytes)


def write_ufs_pointer_block(image: bytearray, filesystem: FilesystemCandidate, fs_block: int, pointers: list[int]) -> None:
    block_offset = filesystem.start_offset + ufs_fsbtobytes(filesystem.details, fs_block)
    block_size = int(filesystem.details['bsize'])
    raw = bytearray(block_size)
    for index, pointer in enumerate(pointers[:int(filesystem.details['nindir'])]):
        raw[index * 4:(index + 1) * 4] = int(pointer).to_bytes(4, 'little', signed=False)
    image[block_offset:block_offset + block_size] = raw


def build_ufs_pointer_tree(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    levels: int,
    data_blocks: list[int],
) -> tuple[int, int]:
    if not data_blocks:
        return 0, 0
    pointer_count = int(filesystem.details['nindir'])
    if levels == 1:
        root_block = allocate_ufs_block(image, filesystem, inode_number)
        write_ufs_pointer_block(image, filesystem, root_block, data_blocks[:pointer_count])
        return root_block, 1

    child_capacity = pointer_count ** (levels - 1)
    child_roots: list[int] = []
    total_pointer_blocks = 1
    remaining = list(data_blocks)
    while remaining:
        chunk = remaining[:child_capacity]
        remaining = remaining[child_capacity:]
        child_root, child_count = build_ufs_pointer_tree(image, filesystem, inode_number, levels - 1, chunk)
        child_roots.append(child_root)
        total_pointer_blocks += child_count
    root_block = allocate_ufs_block(image, filesystem, inode_number)
    write_ufs_pointer_block(image, filesystem, root_block, child_roots)
    return root_block, total_pointer_blocks


def apply_ufs_inplace_replacement(image: bytearray, filesystem: FilesystemCandidate, target_path: str, new_data: bytes) -> dict[str, int | str]:
    inode_number, inode, old_data = read_ufs_path_bytes(image, filesystem, target_path)
    block_size = int(filesystem.details['bsize'])
    data_blocks = ufs_inode_data_blocks(image, filesystem, inode)
    capacity = len(data_blocks) * block_size
    if capacity <= 0:
        raise SystemExit(f'error: ufs file {target_path} has no writable allocated blocks')
    if len(new_data) > capacity:
        raise SystemExit(f'error: replacement for {target_path} exceeds its allocated UFS capacity ({len(new_data)} > {capacity})')

    remaining = new_data
    for fs_block in data_blocks:
        block_offset = filesystem.start_offset + ufs_fsbtobytes(filesystem.details, int(fs_block))
        chunk = remaining[:block_size]
        image[block_offset:block_offset + block_size] = chunk.ljust(block_size, b'\0')
        remaining = remaining[block_size:]
        if not remaining:
            break

    write_ufs_inode_size(image, filesystem, inode_number, len(new_data))
    return {
        'target_path': target_path,
        'inode': inode_number,
        'old_size': len(old_data),
        'new_size': len(new_data),
        'capacity': capacity,
    }


def apply_ufs_inode_replacement(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    inode: dict[str, int | list[int]],
    new_data: bytes,
    target_path: str | None = None,
) -> dict[str, int | str]:
    old_data = read_ufs_file(image, filesystem.start_offset, filesystem.details, inode)
    block_size = int(filesystem.details['bsize'])
    nindir = int(filesystem.details['nindir'])
    max_blocks = UFS_NDADDR + nindir + (nindir ** 2) + (nindir ** 3)
    needed_blocks = 0 if len(new_data) == 0 else (len(new_data) + block_size - 1) // block_size
    target_label = target_path or f'inode {inode_number}'
    if needed_blocks > max_blocks:
        raise SystemExit(f'error: replacement for {target_label} exceeds the host-tool UFS addressing limit ({needed_blocks} blocks)')

    current_data_blocks = ufs_inode_data_blocks(image, filesystem, inode)
    current_allocation_sizes = ufs_allocation_byte_sizes(filesystem.details, int(inode['size']))
    current_pointer_blocks = ufs_inode_pointer_blocks(image, filesystem, inode)
    original_data_block_count = len(current_data_blocks)
    original_pointer_block_count = len(current_pointer_blocks)
    requested_allocation_sizes = ufs_allocation_byte_sizes(filesystem.details, len(new_data))

    for pointer_block in reversed(current_pointer_blocks):
        free_ufs_allocation(image, filesystem, pointer_block, block_size)

    for fs_block, allocation_bytes in zip(reversed(current_data_blocks), reversed(current_allocation_sizes)):
        free_ufs_allocation(image, filesystem, fs_block, allocation_bytes)
    current_data_blocks = [
        allocate_ufs_allocation(image, filesystem, inode_number, allocation_bytes)
        for allocation_bytes in requested_allocation_sizes
    ]

    remaining = new_data
    for fs_block, allocation_bytes in zip(current_data_blocks, requested_allocation_sizes):
        block_offset = filesystem.start_offset + ufs_fsbtobytes(filesystem.details, int(fs_block))
        chunk = remaining[:block_size]
        image[block_offset:block_offset + allocation_bytes] = chunk.ljust(allocation_bytes, b'\0')
        remaining = remaining[block_size:]

    direct_blocks = current_data_blocks[:UFS_NDADDR]
    indirect_roots: list[int] = []
    new_pointer_block_count = 0
    remaining_data_blocks = current_data_blocks[UFS_NDADDR:]
    for levels in range(1, 4):
        level_capacity = nindir ** levels
        level_data_blocks = remaining_data_blocks[:level_capacity]
        remaining_data_blocks = remaining_data_blocks[level_capacity:]
        if level_data_blocks:
            root_block, pointer_block_count = build_ufs_pointer_tree(image, filesystem, inode_number, levels, level_data_blocks)
            indirect_roots.append(root_block)
            new_pointer_block_count += pointer_block_count
        else:
            indirect_roots.append(0)

    write_ufs_block_lists(
        image,
        filesystem,
        inode_number,
        direct_blocks + ([0] * (UFS_NDADDR - len(direct_blocks))),
        indirect_roots,
    )
    write_ufs_inode_size(image, filesystem, inode_number, len(new_data))
    write_ufs_inode_blocks(
        image,
        filesystem,
        inode_number,
        (sum(allocation_bytes // SECTOR_SIZE for allocation_bytes in requested_allocation_sizes) + (new_pointer_block_count * (block_size // SECTOR_SIZE))),
    )
    return {
        'target_path': target_label,
        'inode': inode_number,
        'old_size': len(old_data),
        'new_size': len(new_data),
        'old_data_blocks': original_data_block_count,
        'new_data_blocks': len(current_data_blocks),
        'old_pointer_blocks': original_pointer_block_count,
        'new_pointer_blocks': new_pointer_block_count,
    }


def apply_ufs_replacement(image: bytearray, filesystem: FilesystemCandidate, target_path: str, new_data: bytes) -> dict[str, int | str]:
    inode_number, inode, _ = read_ufs_path_bytes(image, filesystem, target_path)
    return apply_ufs_inode_replacement(image, filesystem, inode_number, inode, new_data, target_path=target_path)


def add_ufs_directory_entry(
    image: bytearray,
    filesystem: FilesystemCandidate,
    directory_inode_number: int,
    directory_inode: dict[str, int | list[int]],
    entry_name: str,
    child_inode_number: int,
) -> dict[str, int | str]:
    directory_bytes = read_ufs_file(image, filesystem.start_offset, filesystem.details, directory_inode)
    directory_size = int(directory_inode['size'])
    try:
        updated_directory = insert_ufs_directory_entry(directory_bytes, directory_size, child_inode_number, entry_name)
    except ValueError:
        grown_directory = directory_bytes + (b'\0' * UFS_DIRBLKSIZ)
        updated_directory = insert_ufs_directory_entry(grown_directory, directory_size + UFS_DIRBLKSIZ, child_inode_number, entry_name)
    return apply_ufs_inode_replacement(image, filesystem, directory_inode_number, directory_inode, updated_directory)


def delete_ufs_directory_entry(
    image: bytearray,
    filesystem: FilesystemCandidate,
    directory_inode_number: int,
    directory_inode: dict[str, int | list[int]],
    entry_name: str,
) -> dict[str, int | str]:
    directory_bytes = read_ufs_file(image, filesystem.start_offset, filesystem.details, directory_inode)
    updated_directory = remove_ufs_directory_entry(directory_bytes, int(directory_inode['size']), entry_name)
    return apply_ufs_inode_replacement(image, filesystem, directory_inode_number, directory_inode, updated_directory)


def free_ufs_inode_contents(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    inode: dict[str, int | list[int]],
) -> None:
    apply_ufs_inode_replacement(image, filesystem, inode_number, inode, b'')


def update_ufs_directory_dotdot(
    image: bytearray,
    filesystem: FilesystemCandidate,
    directory_inode_number: int,
    directory_inode: dict[str, int | list[int]],
    parent_inode_number: int,
) -> None:
    directory_bytes = read_ufs_file(image, filesystem.start_offset, filesystem.details, directory_inode)
    updated_directory = rewrite_ufs_directory_entry_inode(directory_bytes, int(directory_inode['size']), '..', parent_inode_number)
    apply_ufs_inode_replacement(image, filesystem, directory_inode_number, directory_inode, updated_directory)


def create_ufs_file(
    image: bytearray,
    filesystem: FilesystemCandidate,
    target_path: str,
    file_bytes: bytes,
    mode: int = 0o644,
    uid: int = 0,
    gid: int = 0,
    timestamp: int = 0,
) -> dict[str, int | str]:
    if resolve_ufs_path(image, filesystem, target_path) is not None:
        raise SystemExit(f'error: target path {target_path} already exists inside the ufs filesystem')
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_parent(image, filesystem, target_path)
    new_inode_number = allocate_ufs_inode(image, filesystem, preferred_inode=parent_inode_number)
    file_type = ufs_file_type(mode) or UFS_IFREG
    permissions = mode & ~UFS_IFMT
    initialize_ufs_inode(image, filesystem, new_inode_number, file_type | permissions, uid=uid, gid=gid, nlink=1, timestamp=timestamp)
    new_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, new_inode_number)
    if new_inode is None:
        raise SystemExit(f'error: failed to re-read newly allocated UFS inode {new_inode_number}')
    try:
        apply_ufs_inode_replacement(image, filesystem, new_inode_number, new_inode, file_bytes, target_path=target_path)
        add_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name, new_inode_number)
    except Exception:
        rollback_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, new_inode_number)
        if rollback_inode is not None:
            free_ufs_inode_contents(image, filesystem, new_inode_number, rollback_inode)
        clear_ufs_inode(image, filesystem, new_inode_number)
        free_ufs_inode(image, filesystem, new_inode_number)
        raise
    return {'operation': 'create', 'path': target_path, 'inode': new_inode_number, 'size': len(file_bytes)}


def make_ufs_directory(
    image: bytearray,
    filesystem: FilesystemCandidate,
    target_path: str,
    mode: int = 0o755,
    uid: int = 0,
    gid: int = 0,
    timestamp: int = 0,
) -> dict[str, int | str]:
    if resolve_ufs_path(image, filesystem, target_path) is not None:
        raise SystemExit(f'error: target path {target_path} already exists inside the ufs filesystem')
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_parent(image, filesystem, target_path)
    new_inode_number = allocate_ufs_inode(image, filesystem, preferred_inode=parent_inode_number, directory=True)
    permissions = mode & ~UFS_IFMT
    initialize_ufs_inode(image, filesystem, new_inode_number, UFS_IFDIR | permissions, uid=uid, gid=gid, nlink=2, timestamp=timestamp)
    new_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, new_inode_number)
    if new_inode is None:
        raise SystemExit(f'error: failed to re-read newly allocated UFS inode {new_inode_number}')
    try:
        apply_ufs_inode_replacement(
            image,
            filesystem,
            new_inode_number,
            new_inode,
            build_ufs_directory_block(new_inode_number, parent_inode_number),
            target_path=target_path,
        )
        add_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name, new_inode_number)
        write_ufs_inode_nlink(image, filesystem, parent_inode_number, int(parent_inode['nlink']) + 1)
    except Exception:
        rollback_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, new_inode_number)
        if rollback_inode is not None:
            free_ufs_inode_contents(image, filesystem, new_inode_number, rollback_inode)
        clear_ufs_inode(image, filesystem, new_inode_number)
        free_ufs_inode(image, filesystem, new_inode_number, directory=True)
        raise
    return {'operation': 'mkdir', 'path': target_path, 'inode': new_inode_number}


def unlink_ufs_path(image: bytearray, filesystem: FilesystemCandidate, target_path: str) -> dict[str, int | str]:
    if target_path == '/':
        raise SystemExit('error: refusing to unlink the UFS root directory')
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: target path {target_path} does not exist inside the ufs filesystem')
    target_inode_number, target_inode = resolved
    if ufs_is_directory(target_inode):
        raise SystemExit(f'error: target path {target_path} is a directory; use rmdir instead')
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_parent(image, filesystem, target_path)
    delete_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name)
    current_nlink = int(target_inode['nlink'])
    if current_nlink > 1:
        write_ufs_inode_nlink(image, filesystem, target_inode_number, current_nlink - 1)
    else:
        refreshed_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, target_inode_number)
        if refreshed_inode is not None:
            free_ufs_inode_contents(image, filesystem, target_inode_number, refreshed_inode)
        clear_ufs_inode(image, filesystem, target_inode_number)
        free_ufs_inode(image, filesystem, target_inode_number)
    return {'operation': 'unlink', 'path': target_path, 'inode': target_inode_number}


def detach_ufs_path(image: bytearray, filesystem: FilesystemCandidate, target_path: str) -> dict[str, int | str]:
    if target_path == '/':
        raise SystemExit('error: refusing to unlink the UFS root directory')
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: target path {target_path} does not exist inside the ufs filesystem')
    target_inode_number, target_inode = resolved
    if ufs_is_directory(target_inode):
        raise SystemExit(f'error: target path {target_path} is a directory; use rmdir instead')
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_parent(image, filesystem, target_path)
    delete_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name)
    current_nlink = int(target_inode['nlink'])
    write_ufs_inode_nlink(image, filesystem, target_inode_number, max(0, current_nlink - 1))
    return {'operation': 'detach-unlink', 'path': target_path, 'inode': target_inode_number}


def directory_is_empty(directory_bytes: bytes, size: int) -> bool:
    for record in iter_ufs_directory_records(directory_bytes, size):
        if record.inode != 0 and record.name not in {'.', '..'}:
            return False
    return True


def remove_ufs_directory(image: bytearray, filesystem: FilesystemCandidate, target_path: str) -> dict[str, int | str]:
    if target_path == '/':
        raise SystemExit('error: refusing to remove the UFS root directory')
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: target path {target_path} does not exist inside the ufs filesystem')
    target_inode_number, target_inode = resolved
    if not ufs_is_directory(target_inode):
        raise SystemExit(f'error: target path {target_path} is not a directory')
    directory_bytes = read_ufs_file(image, filesystem.start_offset, filesystem.details, target_inode)
    if not directory_is_empty(directory_bytes, int(target_inode['size'])):
        raise SystemExit(f'error: target directory {target_path} is not empty')
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_parent(image, filesystem, target_path)
    delete_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name)
    write_ufs_inode_nlink(image, filesystem, parent_inode_number, max(0, int(parent_inode['nlink']) - 1))
    refreshed_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, target_inode_number)
    if refreshed_inode is not None:
        free_ufs_inode_contents(image, filesystem, target_inode_number, refreshed_inode)
    clear_ufs_inode(image, filesystem, target_inode_number)
    free_ufs_inode(image, filesystem, target_inode_number, directory=True)
    return {'operation': 'rmdir', 'path': target_path, 'inode': target_inode_number}


def detach_ufs_directory(image: bytearray, filesystem: FilesystemCandidate, target_path: str) -> dict[str, int | str]:
    if target_path == '/':
        raise SystemExit('error: refusing to remove the UFS root directory')
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: target path {target_path} does not exist inside the ufs filesystem')
    target_inode_number, target_inode = resolved
    if not ufs_is_directory(target_inode):
        raise SystemExit(f'error: target path {target_path} is not a directory')
    directory_bytes = read_ufs_file(image, filesystem.start_offset, filesystem.details, target_inode)
    if not directory_is_empty(directory_bytes, int(target_inode['size'])):
        raise SystemExit(f'error: target directory {target_path} is not empty')
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_parent(image, filesystem, target_path)
    delete_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name)
    write_ufs_inode_nlink(image, filesystem, parent_inode_number, max(0, int(parent_inode['nlink']) - 1))
    write_ufs_inode_nlink(image, filesystem, target_inode_number, 0)
    return {'operation': 'detach-rmdir', 'path': target_path, 'inode': target_inode_number}


def finalize_ufs_unlinked_inode(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    *,
    directory: bool = False,
) -> None:
    inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, inode_number)
    if inode is None:
        return
    if int(inode['mode']) == 0:
        return
    free_ufs_inode_contents(image, filesystem, inode_number, inode)
    clear_ufs_inode(image, filesystem, inode_number)
    free_ufs_inode(image, filesystem, inode_number, directory=directory)


def link_ufs_path(image: bytearray, filesystem: FilesystemCandidate, source_path: str, target_path: str) -> dict[str, int | str]:
    resolved_source = resolve_ufs_path(image, filesystem, source_path)
    if resolved_source is None:
        raise SystemExit(f'error: source path {source_path} does not exist inside the ufs filesystem')
    source_inode_number, source_inode = resolved_source
    if ufs_is_directory(source_inode):
        raise SystemExit(f'error: refusing to create a hard link to directory {source_path}')
    if resolve_ufs_path(image, filesystem, target_path) is not None:
        raise SystemExit(f'error: target path {target_path} already exists inside the ufs filesystem')
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_parent(image, filesystem, target_path)
    add_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name, source_inode_number)
    write_ufs_inode_nlink(image, filesystem, source_inode_number, int(source_inode['nlink']) + 1)
    return {'operation': 'link', 'source_path': source_path, 'target_path': target_path, 'inode': source_inode_number}


def symlink_ufs_path(
    image: bytearray,
    filesystem: FilesystemCandidate,
    target: str,
    link_path: str,
    mode: int = 0o777,
    uid: int = 0,
    gid: int = 0,
    timestamp: int = 0,
) -> dict[str, int | str]:
    return create_ufs_file(
        image,
        filesystem,
        link_path,
        target.encode('ascii'),
        mode=UFS_IFLNK | mode,
        uid=uid,
        gid=gid,
        timestamp=timestamp,
    )


def rename_ufs_path(image: bytearray, filesystem: FilesystemCandidate, source_path: str, target_path: str) -> dict[str, int | str]:
    if source_path == '/' or target_path == '/':
        raise SystemExit('error: refusing to rename the UFS root directory')
    if source_path == target_path:
        resolved = resolve_ufs_path(image, filesystem, source_path)
        if resolved is None:
            raise SystemExit(f'error: source path {source_path} does not exist inside the ufs filesystem')
        return {'operation': 'rename', 'source_path': source_path, 'target_path': target_path, 'inode': resolved[0]}

    resolved_source = resolve_ufs_path(image, filesystem, source_path)
    if resolved_source is None:
        raise SystemExit(f'error: source path {source_path} does not exist inside the ufs filesystem')
    source_inode_number, source_inode = resolved_source
    source_parent_path, source_name, source_parent_inode_number, source_parent_inode = resolve_ufs_parent(image, filesystem, source_path)
    target_parent_path, target_name, target_parent_inode_number, target_parent_inode = resolve_ufs_parent(image, filesystem, target_path)

    source_parts = ufs_path_components(source_path)
    target_parent_parts = ufs_path_components(target_parent_path)
    if ufs_is_directory(source_inode) and target_parent_parts[:len(source_parts)] == source_parts:
        raise SystemExit(f'error: cannot rename directory {source_path} into its own subtree {target_path}')

    existing_target = resolve_ufs_path(image, filesystem, target_path)
    if existing_target is not None:
        target_inode_number, target_inode = existing_target
        if target_inode_number == source_inode_number:
            return {'operation': 'rename', 'source_path': source_path, 'target_path': target_path, 'inode': source_inode_number}
        if ufs_is_directory(source_inode) != ufs_is_directory(target_inode):
            raise SystemExit('error: cannot rename across file and directory types')
        if ufs_is_directory(target_inode):
            remove_ufs_directory(image, filesystem, target_path)
        else:
            unlink_ufs_path(image, filesystem, target_path)
        source_parent_path, source_name, source_parent_inode_number, source_parent_inode = resolve_ufs_parent(image, filesystem, source_path)
        target_parent_path, target_name, target_parent_inode_number, target_parent_inode = resolve_ufs_parent(image, filesystem, target_path)
        source_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, source_inode_number)
        if source_inode is None:
            raise SystemExit(f'error: source inode {source_inode_number} disappeared during rename preparation')

    add_ufs_directory_entry(image, filesystem, target_parent_inode_number, target_parent_inode, target_name, source_inode_number)
    refreshed_source_parent_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, source_parent_inode_number)
    if refreshed_source_parent_inode is None:
        raise SystemExit(f'error: failed to refresh source parent inode {source_parent_inode_number}')
    source_parent_inode = refreshed_source_parent_inode
    if source_parent_inode_number == target_parent_inode_number:
        target_parent_inode = refreshed_source_parent_inode
    if ufs_is_directory(source_inode) and source_parent_inode_number != target_parent_inode_number:
        refreshed_source_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, source_inode_number)
        if refreshed_source_inode is None:
            raise SystemExit(f'error: failed to refresh source directory inode {source_inode_number}')
        update_ufs_directory_dotdot(image, filesystem, source_inode_number, refreshed_source_inode, target_parent_inode_number)
        write_ufs_inode_nlink(image, filesystem, source_parent_inode_number, max(0, int(source_parent_inode['nlink']) - 1))
        write_ufs_inode_nlink(image, filesystem, target_parent_inode_number, int(target_parent_inode['nlink']) + 1)
    delete_ufs_directory_entry(image, filesystem, source_parent_inode_number, source_parent_inode, source_name)
    return {'operation': 'rename', 'source_path': source_path, 'target_path': target_path, 'inode': source_inode_number}