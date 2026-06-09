from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .common import FilesystemCandidate, SECTOR_SIZE, UFS_NDADDR, UFS_ROOT_INODE
from .ufs_directory import UFS_DIRBLKSIZ, UFSDirectoryEntry, UFSDirectoryInsertSlot, decode_ufs_directory_entry, encode_ufs_directory_entry, find_ufs_directory_insert_slot, insert_ufs_directory_entry, iter_ufs_directory_records, remove_ufs_directory_entry, rewrite_ufs_directory_entry_inode, ufs_dirsiz
from .ufs_lowlevel import ImageBuffer, MAXCPG, MAXFRAG, MAXIPG, NBBY, NRPOS, UFS_CG_B_OFFSET, UFS_CG_BTOT_OFFSET, UFS_CG_CGX_OFFSET, UFS_CG_CS_NBFREE_OFFSET, UFS_CG_CS_NDIR_OFFSET, UFS_CG_CS_NIFREE_OFFSET, UFS_CG_FROTOR_OFFSET, UFS_CG_FRSUM_OFFSET, UFS_CG_FREE_OFFSET, UFS_CG_IROTOR_OFFSET, UFS_CG_IUSED_OFFSET, UFS_CG_MAGIC, UFS_CG_MAGIC_OFFSET, UFS_CG_NCYL_OFFSET, UFS_CG_NDBLK_OFFSET, UFS_CG_NIBLK_OFFSET, UFS_CG_ROTOR_OFFSET, UFS_CG_TIME_OFFSET, UFS_DINODE_SIZE, UFS_DI_ATIME_OFFSET, UFS_DI_BLOCKS_OFFSET, UFS_DI_CTIME_OFFSET, UFS_DI_DB_OFFSET, UFS_DI_EFTFLAG_OFFSET, UFS_DI_FLAGS_OFFSET, UFS_DI_GEN_OFFSET, UFS_DI_GID_OFFSET, UFS_DI_IB_OFFSET, UFS_DI_MODE_OFFSET, UFS_DI_MTIME_OFFSET, UFS_DI_NLINK_OFFSET, UFS_DI_SGID_OFFSET, UFS_DI_SIZE_OFFSET, UFS_DI_SUID_OFFSET, UFS_DI_UID_OFFSET, UFS_EFT_MAGIC, UFS_FS_BSIZE_OFFSET, UFS_FS_CBLKNO_OFFSET, UFS_FS_CGMASK_OFFSET, UFS_FS_CGOFFSET_OFFSET, UFS_FS_CSADDR_OFFSET, UFS_FS_CSSIZE_OFFSET, UFS_FS_CSTOTAL_NBFREE_OFFSET, UFS_FS_CSTOTAL_NDIR_OFFSET, UFS_FS_CSTOTAL_NIFREE_OFFSET, UFS_FS_DBLKNO_OFFSET, UFS_FS_DSIZE_OFFSET, UFS_FS_FPG_OFFSET, UFS_FS_FRAG_OFFSET, UFS_FS_FSBTODB_OFFSET, UFS_FS_FSIZE_OFFSET, UFS_FS_IBLKNO_OFFSET, UFS_FS_INOPB_OFFSET, UFS_FS_IPG_OFFSET, UFS_FS_MAGIC_OFFSET, UFS_FS_MINFREE_OFFSET, UFS_FS_NCG_OFFSET, UFS_FS_NCYL_OFFSET, UFS_FS_NINDIR_OFFSET, UFS_FS_NSECT_OFFSET, UFS_FS_NSPF_OFFSET, UFS_FS_SPC_OFFSET, UFS_IFBLK, UFS_IFCHR, UFS_IFDIR, UFS_IFLNK, UFS_IFMT, UFS_IFREG, UFS_MAGIC, UFS_SB_OFFSET, UFS_SB_SIZE, adjust_cg_directory_count, adjust_cg_free_blocks, adjust_cg_free_inodes, adjust_superblock_directory_count, adjust_superblock_free_blocks, adjust_superblock_free_inodes, allocate_ufs_allocation, allocate_ufs_block, allocate_ufs_fragments, cg_block_offset, clear_ufs_inode, collect_indirect_data_blocks, collect_indirect_pointer_blocks, detect_ufs as detect_ufs_lowlevel, detect_ufs_at_start as detect_ufs_at_start_lowlevel, free_ufs_allocation, free_ufs_block, free_ufs_inode, i32, initialize_ufs_inode, is_frag_free, is_ufs_inode_used, read_cg_block, read_ufs_file, read_ufs_inode, read_ufs_pointer_block, set_frag_state, set_ufs_inode_state, u16, u32, ufs_allocation_byte_sizes, ufs_blkstofrags, ufs_cgbase, ufs_cgdmin, ufs_cgimin, ufs_cgstart, ufs_cgtod, ufs_data_block_offset, ufs_file_type, ufs_fragroundup, ufs_fsbtobytes, ufs_inode_byte_offset, ufs_inode_data_blocks, ufs_inode_offset, ufs_inode_pointer_blocks, ufs_is_directory, ufs_is_symlink, ufs_itod, ufs_itog, ufs_itoo, ufs_path_components, write_cg_block, write_ufs_block_lists, write_ufs_inode_blocks, write_ufs_inode_mode, write_ufs_inode_nlink, write_ufs_inode_size, write_ufs_inode_time, write_ufs_inode_times, write_ufs_inode_uid_gid, write_ufs_pointer_block


_UFS_CG_BLOCK_ALLOCATION_HINTS: dict[tuple[int, int, int, int], int] = {}
_UFS_ALLOCATABLE_CG_BLOCK_CACHE: dict[tuple[int, int, int, int], bytearray] = {}
_UFS_METADATA_NORMALIZATION_STATE: set[tuple[int, int, int]] = set()
_UFS_POINTER_BLOCK_CACHE: dict[tuple[int, int, int, int], list[int]] = {}

UFS_FS_CSTOTAL_NFFREE_OFFSET = 204
UFS_CG_CS_NFFREE_OFFSET = 36
UFS_CSUM_SIZE = 16
UFS_FS_SBLKNO_OFFSET = 8
UFS_FS_TIME_OFFSET = 32
UFS_FS_SIZE_OFFSET = 36
UFS_FS_ROTDLY_OFFSET = 64
UFS_FS_RPS_OFFSET = 68
UFS_FS_BMASK_OFFSET = 72
UFS_FS_FMASK_OFFSET = 76
UFS_FS_BSHIFT_OFFSET = 80
UFS_FS_FSHIFT_OFFSET = 84
UFS_FS_MAXCONTIG_OFFSET = 88
UFS_FS_MAXBPG_OFFSET = 92
UFS_FS_FRAGSHIFT_OFFSET = 96
UFS_FS_SBSIZE_OFFSET = 104
UFS_FS_CSMASK_OFFSET = 108
UFS_FS_CSSHIFT_OFFSET = 112
UFS_FS_OPTIM_OFFSET = 128
UFS_FS_STATE_OFFSET = 132
UFS_FS_CGSIZE_OFFSET = 160
UFS_FS_NTRAK_OFFSET = 164
UFS_FS_CPG_OFFSET = 180
UFS_FS_FMOD_OFFSET = 208
UFS_FS_CLEAN_OFFSET = 209
UFS_FS_RONLY_OFFSET = 210

UFS_FS_OKAY = 0x7C269D38


def _ufs_runtime_state(filesystem: FilesystemCandidate) -> dict[str, Any]:
    state = filesystem.details.get('_runtime_state')
    if isinstance(state, dict):
        return state
    state = {
        'cg_block_hints': {},
        'allocatable_cg_blocks': {},
        'metadata_normalized': False,
        'pointer_blocks': {},
    }
    filesystem.details['_runtime_state'] = state
    return state


def clear_ufs_filesystem_runtime_caches(filesystem: FilesystemCandidate) -> None:
    filesystem.details.pop('_runtime_state', None)


def _ufs_pointer_block_cache_key(image: ImageBuffer, filesystem: FilesystemCandidate, fs_block: int) -> tuple[int, int, int, int]:
    return (id(image), filesystem.start_offset, filesystem.super_offset, fs_block)


def _clear_ufs_pointer_block_cache(image: ImageBuffer) -> None:
    image_id = id(image)
    stale_keys = [cache_key for cache_key in _UFS_POINTER_BLOCK_CACHE if cache_key[0] == image_id]
    for cache_key in stale_keys:
        del _UFS_POINTER_BLOCK_CACHE[cache_key]


def clear_ufs_runtime_caches(image: ImageBuffer | None = None) -> None:
    del image
    _UFS_CG_BLOCK_ALLOCATION_HINTS.clear()
    _UFS_ALLOCATABLE_CG_BLOCK_CACHE.clear()
    _UFS_METADATA_NORMALIZATION_STATE.clear()
    _UFS_POINTER_BLOCK_CACHE.clear()


def _ufs_allocatable_cg_block_cache_key(image: ImageBuffer, filesystem: FilesystemCandidate, cg: int) -> tuple[int, int, int, int]:
    return (id(image), filesystem.start_offset, filesystem.super_offset, cg)


def _clear_ufs_allocatable_cg_block_cache(image: ImageBuffer) -> None:
    image_id = id(image)
    stale_keys = [cache_key for cache_key in _UFS_ALLOCATABLE_CG_BLOCK_CACHE if cache_key[0] == image_id]
    for cache_key in stale_keys:
        del _UFS_ALLOCATABLE_CG_BLOCK_CACHE[cache_key]


def detect_ufs(image: ImageBuffer) -> list[FilesystemCandidate]:
    return detect_ufs_lowlevel(image)


def detect_ufs_at_start(image: ImageBuffer, fs_start: int = 0) -> FilesystemCandidate | None:
    return detect_ufs_at_start_lowlevel(image, fs_start)


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
    inode_offset = ufs_inode_byte_offset(fs_start, fs, inode_number)
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


def _ufs_inode_block_cache_key(inode: dict[str, Any]) -> tuple[int, tuple[int, ...], tuple[int, ...]] | None:
    direct_blocks = inode.get('direct_blocks')
    indirect_blocks = inode.get('indirect_blocks')
    if not isinstance(direct_blocks, list) or not isinstance(indirect_blocks, list):
        return None
    return (
        int(inode['size']),
        tuple(int(fs_block) for fs_block in direct_blocks),
        tuple(int(fs_block) for fs_block in indirect_blocks),
    )


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
    needed_blocks = (size + block_size - 1) // block_size
    allocations: list[int] = []
    remaining = size
    block_index = 0
    while remaining > 0:
        logical_bytes = min(block_size, remaining)
        block_index += 1
        if logical_bytes == block_size or needed_blocks > UFS_NDADDR:
            allocations.append(block_size)
        else:
            allocations.append(ufs_fragroundup(fs, logical_bytes))
        remaining -= block_size
    return allocations


def extend_ufs_allocation_byte_sizes(
    fs: dict[str, Any],
    current_allocations: list[int],
    old_size: int,
    new_size: int,
) -> list[int]:
    if new_size <= old_size:
        return ufs_allocation_byte_sizes(fs, new_size)
    block_size = int(fs['bsize'])
    old_needed_blocks = 0 if old_size <= 0 else (old_size + block_size - 1) // block_size
    new_needed_blocks = (new_size + block_size - 1) // block_size

    if len(current_allocations) != old_needed_blocks:
        return ufs_allocation_byte_sizes(fs, new_size)
    if old_needed_blocks <= UFS_NDADDR and new_needed_blocks > UFS_NDADDR:
        return ufs_allocation_byte_sizes(fs, new_size)
    if new_needed_blocks == old_needed_blocks:
        requested_allocations = ufs_allocation_byte_sizes(fs, new_size)
        if requested_allocations == current_allocations:
            return list(current_allocations)
        return requested_allocations

    allocations = list(current_allocations)
    remaining = new_size - (old_needed_blocks * block_size)
    for block_index in range(old_needed_blocks, new_needed_blocks):
        logical_bytes = min(block_size, remaining)
        if logical_bytes == block_size or new_needed_blocks > UFS_NDADDR:
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


def lookup_ufs_directory_entry(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    directory_inode: dict[str, int | list[int]],
    entry_name: str,
) -> tuple[int, dict[str, int | list[int]]] | None:
    fs = filesystem.details
    directory_size = int(directory_inode['size'])
    if directory_size <= 0:
        return None
    directory_bytes = read_ufs_inode_bytes(image, filesystem, directory_inode)
    for block_offset in range(0, directory_size, UFS_DIRBLKSIZ):
        block_span = min(UFS_DIRBLKSIZ, directory_size - block_offset)
        block_bytes = directory_bytes[block_offset:block_offset + block_span]
        for record in iter_ufs_directory_records(block_bytes, block_span):
            if record.inode == 0 or record.name != entry_name:
                continue
            child_inode = read_ufs_inode(image, filesystem.start_offset, fs, record.inode)
            if child_inode is None:
                return None
            return record.inode, child_inode
    return None


def resolve_ufs_creation_parent(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    target_path: str,
    *,
    parent_inode_number: int | None = None,
) -> tuple[str, str, int, dict[str, int | list[int]]]:
    parent_path, entry_name = split_ufs_parent_path(target_path)
    if parent_inode_number is None:
        resolved_parent = resolve_ufs_path(image, filesystem, parent_path)
        if resolved_parent is None:
            raise SystemExit(f'error: could not resolve parent path {parent_path} inside the ufs filesystem')
        parent_inode_number, parent_inode = resolved_parent
    else:
        parent_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, parent_inode_number)
        if parent_inode is None:
            raise SystemExit(f'error: could not read cached parent inode {parent_inode_number} for {target_path}')
    if not ufs_is_directory(parent_inode):
        raise SystemExit(f'error: parent path {parent_path} is not a UFS directory')
    if lookup_ufs_directory_entry(image, filesystem, parent_inode, entry_name) is not None:
        raise SystemExit(f'error: target path {target_path} already exists inside the ufs filesystem')
    return parent_path, entry_name, parent_inode_number, parent_inode


def build_ufs_directory_block(self_inode_number: int, parent_inode_number: int) -> bytes:
    dot = encode_ufs_directory_entry(self_inode_number, '.', ufs_dirsiz('.'))
    dotdot = encode_ufs_directory_entry(parent_inode_number, '..', UFS_DIRBLKSIZ - len(dot))
    return dot + dotdot


def _u32_mask(value: int) -> int:
    return value & 0xFFFFFFFF


def _power_of_two_shift(value: int) -> int:
    if value <= 0 or value & (value - 1):
        raise SystemExit(f'error: expected a positive power-of-two value, got {value}')
    return value.bit_length() - 1


def _align_up(value: int, alignment: int) -> int:
    if alignment <= 0:
        return value
    return ((value + alignment - 1) // alignment) * alignment


def _compute_inode_block_count(
    image_size: int,
    *,
    block_size: int,
    cylinder_groups: int,
    fragments_per_group: int,
    inode_block_number: int,
    bytes_per_inode: int,
) -> int:
    if bytes_per_inode <= 0:
        raise SystemExit('error: bytes_per_inode must be positive')

    inodes_per_block = block_size // UFS_DINODE_SIZE
    target_inodes = max((image_size + bytes_per_inode - 1) // bytes_per_inode, 1)
    target_ipg = max((target_inodes + cylinder_groups - 1) // cylinder_groups, 1)
    inode_block_count = max((target_ipg + inodes_per_block - 1) // inodes_per_block, 1)

    max_inode_blocks = (fragments_per_group // (block_size // SECTOR_SIZE)) - inode_block_number - 1
    if max_inode_blocks <= 0:
        raise SystemExit('error: UFS cylinder group is too small to reserve inode blocks')

    inode_block_count = min(inode_block_count, max_inode_blocks)
    inodes_per_group = inode_block_count * inodes_per_block
    if inodes_per_group > MAXIPG:
        inode_block_count = MAXIPG // inodes_per_block
        inodes_per_group = inode_block_count * inodes_per_block
    if inode_block_count <= 0 or inodes_per_group <= 0:
        raise SystemExit('error: UFS inode layout could not reserve any usable inodes')
    return inode_block_count


def build_ufs_filesystem_image(
    image_size: int,
    *,
    target_image: ImageBuffer | None = None,
    timestamp: int = 0,
    block_size: int = 8192,
    fragment_size: int = SECTOR_SIZE,
    bytes_per_inode: int = 8192,
    summary_block_number: int = 4,
    cylinder_group_block_number: int = 5,
    inode_block_number: int = 6,
    tracks_per_cylinder: int | None = None,
    sectors_per_track: int | None = None,
) -> tuple[ImageBuffer, FilesystemCandidate]:
    if image_size <= 0 or image_size % SECTOR_SIZE != 0:
        raise SystemExit('error: UFS image size must be a positive multiple of 512 bytes')
    if block_size < 4096 or block_size > UFS_SB_SIZE:
        raise SystemExit('error: UFS block size must be between 4096 and 8192 bytes')
    if fragment_size != SECTOR_SIZE:
        raise SystemExit('error: the current UFS formatter only supports 512-byte fragments')
    if block_size % fragment_size != 0:
        raise SystemExit('error: UFS block size must be a whole multiple of the fragment size')
    if (tracks_per_cylinder is None) != (sectors_per_track is None):
        raise SystemExit('error: tracks_per_cylinder and sectors_per_track must be specified together')
    if tracks_per_cylinder is not None and tracks_per_cylinder <= 0:
        raise SystemExit('error: tracks_per_cylinder must be positive')
    if sectors_per_track is not None and sectors_per_track <= 0:
        raise SystemExit('error: sectors_per_track must be positive')

    fragments_per_block = block_size // fragment_size
    block_shift = _power_of_two_shift(fragments_per_block)

    fsbtodb = _power_of_two_shift(fragment_size // SECTOR_SIZE)
    bshift = _power_of_two_shift(block_size)
    fshift = _power_of_two_shift(fragment_size)
    fragshift = _power_of_two_shift(fragments_per_block)
    inodes_per_block = block_size // UFS_DINODE_SIZE

    total_fragments = image_size // fragment_size
    if tracks_per_cylinder is None or sectors_per_track is None:
        tracks_per_cylinder = 1
        sectors_per_track = block_size // SECTOR_SIZE
        total_cylinders = 1
        cylinders_per_group = 1
        cylinder_groups = 1
        fragments_per_group = total_fragments
    else:
        sectors_per_cylinder = tracks_per_cylinder * sectors_per_track
        if total_fragments % sectors_per_cylinder != 0:
            raise SystemExit('error: UFS slice size must be an exact whole number of cylinders')
        total_cylinders = total_fragments // sectors_per_cylinder
        if total_cylinders <= 0:
            raise SystemExit('error: UFS slice must contain at least one cylinder')
        max_cg_data_fragments = (block_size - UFS_CG_FREE_OFFSET) * NBBY
        max_cylinders_per_group = max_cg_data_fragments // sectors_per_cylinder
        if max_cylinders_per_group <= 0:
            raise SystemExit('error: UFS cylinder-group bitmap cannot represent even one cylinder with this geometry')
        cylinders_per_group = min(total_cylinders, MAXCPG, max_cylinders_per_group)
        cylinder_groups = (total_cylinders + cylinders_per_group - 1) // cylinders_per_group
        fragments_per_group = cylinders_per_group * sectors_per_cylinder

    summary_frag_number = summary_block_number << block_shift
    summary_bytes = cylinder_groups * UFS_CSUM_SIZE
    summary_area_bytes = _align_up(summary_bytes, fragment_size)
    summary_fragments = summary_area_bytes // fragment_size
    minimum_cylinder_group_block = _align_up(summary_frag_number + summary_fragments, fragments_per_block) // fragments_per_block
    if cylinder_group_block_number < minimum_cylinder_group_block:
        metadata_block_delta = minimum_cylinder_group_block - cylinder_group_block_number
        cylinder_group_block_number += metadata_block_delta
        inode_block_number += metadata_block_delta
    if inode_block_number <= cylinder_group_block_number:
        inode_block_number = cylinder_group_block_number + 1

    cylinder_group_frag_number = cylinder_group_block_number << block_shift
    inode_frag_number = inode_block_number << block_shift

    inode_block_count = _compute_inode_block_count(
        image_size,
        block_size=block_size,
        cylinder_groups=cylinder_groups,
        fragments_per_group=fragments_per_group,
        inode_block_number=inode_block_number,
        bytes_per_inode=bytes_per_inode,
    )
    inodes_per_group = inode_block_count * inodes_per_block
    data_frag_number = (inode_block_number + inode_block_count) << block_shift
    required_bytes = (data_frag_number + fragments_per_block) * fragment_size
    if image_size < required_bytes:
        raise SystemExit(f'error: UFS slice is too small ({image_size} bytes); need at least {required_bytes} bytes')

    csums_per_block = block_size // UFS_CSUM_SIZE
    csshift = _power_of_two_shift(csums_per_block)
    csmask = _u32_mask(-csums_per_block)
    if summary_frag_number + summary_fragments > cylinder_group_frag_number:
        raise SystemExit('error: UFS cylinder summary area overlaps the cylinder group block')

    image = bytearray(image_size) if target_image is None else target_image
    if len(image) != image_size:
        raise SystemExit('error: target UFS image size does not match the requested filesystem size')
    filesystem = FilesystemCandidate(
        kind='ufs',
        start_offset=0,
        super_offset=UFS_SB_OFFSET,
        block_size=block_size,
        details={
            'bsize': block_size,
            'fsize': fragment_size,
            'frag': fragments_per_block,
            'dsize': total_fragments,
            'ipg': inodes_per_group,
            'fpg': fragments_per_group,
            'inopb': inodes_per_block,
            'fsbtodb': fsbtodb,
            'cgoffset': 0,
            'cgmask': 0,
            'cblkno': cylinder_group_frag_number,
            'iblkno': inode_frag_number,
            'dblkno': data_frag_number,
            'ncg': cylinder_groups,
            'minfree': 0,
            'fragshift': fragshift,
            'nindir': block_size // 4,
            'nspf': fragment_size // SECTOR_SIZE,
            'csaddr': summary_frag_number,
            'cssize': summary_area_bytes,
            'csmask': csmask,
            'csshift': csshift,
            'nsect': sectors_per_track,
            'spc': tracks_per_cylinder * sectors_per_track,
            'ncyl': total_cylinders,
            'cpg': cylinders_per_group,
            'ntrak': tracks_per_cylinder,
        },
    )

    super_offset = filesystem.super_offset
    image[super_offset + UFS_FS_SBLKNO_OFFSET:super_offset + UFS_FS_SBLKNO_OFFSET + 4] = (UFS_SB_OFFSET // fragment_size).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CBLKNO_OFFSET:super_offset + UFS_FS_CBLKNO_OFFSET + 4] = cylinder_group_frag_number.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_IBLKNO_OFFSET:super_offset + UFS_FS_IBLKNO_OFFSET + 4] = inode_frag_number.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_DBLKNO_OFFSET:super_offset + UFS_FS_DBLKNO_OFFSET + 4] = data_frag_number.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CGOFFSET_OFFSET:super_offset + UFS_FS_CGOFFSET_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CGMASK_OFFSET:super_offset + UFS_FS_CGMASK_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_TIME_OFFSET:super_offset + UFS_FS_TIME_OFFSET + 4] = timestamp.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_SIZE_OFFSET:super_offset + UFS_FS_SIZE_OFFSET + 4] = total_fragments.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_DSIZE_OFFSET:super_offset + UFS_FS_DSIZE_OFFSET + 4] = total_fragments.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_NCG_OFFSET:super_offset + UFS_FS_NCG_OFFSET + 4] = cylinder_groups.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_BSIZE_OFFSET:super_offset + UFS_FS_BSIZE_OFFSET + 4] = block_size.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_FSIZE_OFFSET:super_offset + UFS_FS_FSIZE_OFFSET + 4] = fragment_size.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_FRAG_OFFSET:super_offset + UFS_FS_FRAG_OFFSET + 4] = fragments_per_block.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_MINFREE_OFFSET:super_offset + UFS_FS_MINFREE_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_ROTDLY_OFFSET:super_offset + UFS_FS_ROTDLY_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_RPS_OFFSET:super_offset + UFS_FS_RPS_OFFSET + 4] = (60).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_BMASK_OFFSET:super_offset + UFS_FS_BMASK_OFFSET + 4] = _u32_mask(-(block_size)).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_FMASK_OFFSET:super_offset + UFS_FS_FMASK_OFFSET + 4] = _u32_mask(-(fragment_size)).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_BSHIFT_OFFSET:super_offset + UFS_FS_BSHIFT_OFFSET + 4] = bshift.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_FSHIFT_OFFSET:super_offset + UFS_FS_FSHIFT_OFFSET + 4] = fshift.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_MAXCONTIG_OFFSET:super_offset + UFS_FS_MAXCONTIG_OFFSET + 4] = (1).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_MAXBPG_OFFSET:super_offset + UFS_FS_MAXBPG_OFFSET + 4] = (
        max((fragments_per_group - data_frag_number) // fragments_per_block, 0)
    ).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_FRAGSHIFT_OFFSET:super_offset + UFS_FS_FRAGSHIFT_OFFSET + 4] = fragshift.to_bytes(4, 'little', signed=True)
    image[super_offset + UFS_FS_FSBTODB_OFFSET:super_offset + UFS_FS_FSBTODB_OFFSET + 4] = fsbtodb.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_SBSIZE_OFFSET:super_offset + UFS_FS_SBSIZE_OFFSET + 4] = min(UFS_SB_SIZE, block_size).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CSMASK_OFFSET:super_offset + UFS_FS_CSMASK_OFFSET + 4] = csmask.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CSSHIFT_OFFSET:super_offset + UFS_FS_CSSHIFT_OFFSET + 4] = csshift.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_NINDIR_OFFSET:super_offset + UFS_FS_NINDIR_OFFSET + 4] = (block_size // 4).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_INOPB_OFFSET:super_offset + UFS_FS_INOPB_OFFSET + 4] = inodes_per_block.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_NSPF_OFFSET:super_offset + UFS_FS_NSPF_OFFSET + 4] = (fragment_size // SECTOR_SIZE).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_OPTIM_OFFSET:super_offset + UFS_FS_OPTIM_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_STATE_OFFSET:super_offset + UFS_FS_STATE_OFFSET + 4] = (UFS_FS_OKAY - timestamp).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CSADDR_OFFSET:super_offset + UFS_FS_CSADDR_OFFSET + 4] = summary_frag_number.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CSSIZE_OFFSET:super_offset + UFS_FS_CSSIZE_OFFSET + 4] = summary_area_bytes.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CGSIZE_OFFSET:super_offset + UFS_FS_CGSIZE_OFFSET + 4] = block_size.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_NTRAK_OFFSET:super_offset + UFS_FS_NTRAK_OFFSET + 4] = tracks_per_cylinder.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_NSECT_OFFSET:super_offset + UFS_FS_NSECT_OFFSET + 4] = sectors_per_track.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_SPC_OFFSET:super_offset + UFS_FS_SPC_OFFSET + 4] = (tracks_per_cylinder * sectors_per_track).to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_NCYL_OFFSET:super_offset + UFS_FS_NCYL_OFFSET + 4] = total_cylinders.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CPG_OFFSET:super_offset + UFS_FS_CPG_OFFSET + 4] = cylinders_per_group.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_IPG_OFFSET:super_offset + UFS_FS_IPG_OFFSET + 4] = inodes_per_group.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_FPG_OFFSET:super_offset + UFS_FS_FPG_OFFSET + 4] = fragments_per_group.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_MAGIC_OFFSET:super_offset + UFS_FS_MAGIC_OFFSET + 4] = UFS_MAGIC.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_FMOD_OFFSET] = 0
    image[super_offset + UFS_FS_CLEAN_OFFSET] = 1
    image[super_offset + UFS_FS_RONLY_OFFSET] = 0

    for cg in range(cylinder_groups):
        cg_bytes = initialize_pristine_ufs_cg(image, filesystem, cg)
        if cg == 0:
            set_ufs_inode_state(cg_bytes, UFS_ROOT_INODE, used=True)
            write_cg_block(image, filesystem, cg, cg_bytes)

    initialize_ufs_inode(image, filesystem, UFS_ROOT_INODE, UFS_IFDIR | 0o755, nlink=2, timestamp=timestamp)
    root_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, UFS_ROOT_INODE)
    if root_inode is None:
        raise SystemExit('error: failed to initialize the UFS root inode')
    apply_ufs_inode_replacement(
        image,
        filesystem,
        UFS_ROOT_INODE,
        root_inode,
        build_ufs_directory_block(UFS_ROOT_INODE, UFS_ROOT_INODE),
        target_path='/',
    )
    recompute_ufs_summary_counts(image, filesystem)
    return image, filesystem


def format_ufs_filesystem(
    image: bytearray,
    *,
    timestamp: int = 0,
    block_size: int = 8192,
    bytes_per_inode: int = 8192,
    tracks_per_cylinder: int | None = None,
    sectors_per_track: int | None = None,
) -> FilesystemCandidate:
    clear_ufs_runtime_caches(image)
    formatted, filesystem = build_ufs_filesystem_image(
        len(image),
        target_image=image,
        timestamp=timestamp,
        block_size=block_size,
        bytes_per_inode=bytes_per_inode,
        tracks_per_cylinder=tracks_per_cylinder,
        sectors_per_track=sectors_per_track,
    )
    clear_ufs_runtime_caches(image)
    return filesystem


def read_ufs_pointer_block(image: ImageBuffer, filesystem: FilesystemCandidate, fs_block: int) -> list[int]:
    pointer_cache = _ufs_runtime_state(filesystem)['pointer_blocks']
    cached_pointers = pointer_cache.get(fs_block)
    if cached_pointers is not None:
        return cached_pointers

    block_offset = ufs_data_block_offset(filesystem.start_offset, filesystem.details, fs_block)
    block_size = int(filesystem.details['bsize'])
    raw = image[block_offset:block_offset + block_size]
    pointers = [u32(raw, index * 4) for index in range(int(filesystem.details['nindir']))]
    pointer_cache[fs_block] = pointers
    return pointers


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
    cache_key = _ufs_inode_block_cache_key(inode)
    cached_blocks = inode.get('_cached_data_blocks')
    if cache_key is not None and inode.get('_cached_data_blocks_key') == cache_key and isinstance(cached_blocks, list):
        return cached_blocks

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
            resolved_blocks = blocks[:needed_blocks]
            if cache_key is not None:
                inode['_cached_data_blocks_key'] = cache_key
                inode['_cached_data_blocks'] = resolved_blocks
            return resolved_blocks
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
            resolved_blocks = blocks[:needed_blocks]
            if cache_key is not None:
                inode['_cached_data_blocks_key'] = cache_key
                inode['_cached_data_blocks'] = resolved_blocks
            return resolved_blocks
    resolved_blocks = blocks[:needed_blocks]
    if cache_key is not None:
        inode['_cached_data_blocks_key'] = cache_key
        inode['_cached_data_blocks'] = resolved_blocks
    return resolved_blocks


def ufs_inode_pointer_blocks(image: ImageBuffer, filesystem: FilesystemCandidate, inode: dict[str, int | list[int]]) -> list[int]:
    cache_key = _ufs_inode_block_cache_key(inode)
    cached_blocks = inode.get('_cached_pointer_blocks')
    if cache_key is not None and inode.get('_cached_pointer_blocks_key') == cache_key and isinstance(cached_blocks, list):
        return cached_blocks

    indirect_blocks = inode['indirect_blocks']
    if not isinstance(indirect_blocks, list):
        return []
    blocks: list[int] = []
    for levels, root_block in enumerate(indirect_blocks, start=1):
        blocks.extend(collect_indirect_pointer_blocks(image, filesystem, int(root_block), levels))
    if cache_key is not None:
        inode['_cached_pointer_blocks_key'] = cache_key
        inode['_cached_pointer_blocks'] = blocks
    return blocks


def read_ufs_inode_bytes(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    inode: dict[str, int | list[int]],
) -> bytes:
    inode_size = int(inode['size'])
    if inode_size <= 0:
        return b''
    return read_ufs_data_range(
        image,
        filesystem,
        ufs_inode_data_blocks(image, filesystem, inode),
        0,
        inode_size,
    )


def read_ufs_file(image: ImageBuffer, fs_start: int, fs: dict[str, Any], inode: dict[str, int | list[int]]) -> bytes:
    filesystem = FilesystemCandidate(kind='ufs', start_offset=fs_start, super_offset=fs_start + UFS_SB_OFFSET, block_size=int(fs['bsize']), details=fs)
    size = int(inode['size'])
    block_size = int(fs['bsize'])
    data = bytearray()
    for fs_block in ufs_inode_data_blocks(image, filesystem, inode):
        block_offset = ufs_data_block_offset(fs_start, fs, fs_block)
        data.extend(image[block_offset:block_offset + block_size])
        if len(data) >= size:
            break
    return bytes(data[:size])


def iter_ufs_inode_directory_records(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    inode: dict[str, int | list[int]],
) -> list[UFSDirectoryEntry]:
    size = int(inode['size'])
    records: list[UFSDirectoryEntry] = []
    directory_bytes = read_ufs_inode_bytes(image, filesystem, inode)
    for block_offset in range(0, size, UFS_DIRBLKSIZ):
        block_span = min(UFS_DIRBLKSIZ, size - block_offset)
        block_bytes = directory_bytes[block_offset:block_offset + block_span]
        for record in iter_ufs_directory_records(block_bytes, block_span):
            records.append(
                UFSDirectoryEntry(
                    inode=record.inode,
                    record_length=record.record_length,
                    name_length=record.name_length,
                    name=record.name,
                    offset=block_offset + record.offset,
                )
            )
    return records


def iter_ufs_directory_entries(image: ImageBuffer, filesystem: FilesystemCandidate, inode: dict[str, int | list[int]]) -> list[dict[str, int | str]]:
    fs = filesystem.details
    entries: list[dict[str, int | str]] = []
    for record in iter_ufs_inode_directory_records(image, filesystem, inode):
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
        resolved_entry = lookup_ufs_directory_entry(image, filesystem, current_inode, part)
        if resolved_entry is None:
            return None
        current_inode_number, current_inode = resolved_entry
    return current_inode_number, current_inode


def read_ufs_path_bytes(image: ImageBuffer, filesystem: FilesystemCandidate, target_path: str) -> tuple[int, dict[str, int | list[int]], bytes]:
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: could not resolve {target_path} inside the ufs filesystem')
    inode_number, inode = resolved
    return inode_number, inode, read_ufs_file(image, filesystem.start_offset, filesystem.details, inode)


def read_ufs_path_range(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    target_path: str,
    offset: int = 0,
    size: int | None = None,
) -> tuple[int, dict[str, int | list[int]], bytes]:
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: could not resolve {target_path} inside the ufs filesystem')
    inode_number, inode = resolved
    inode_size = int(inode['size'])
    read_size = inode_size - offset if size is None else size
    return inode_number, inode, read_ufs_inode_range(image, filesystem, inode, offset, read_size)


def ufs_inode_offset(filesystem: FilesystemCandidate, inode_number: int) -> int:
    return ufs_inode_byte_offset(filesystem.start_offset, filesystem.details, inode_number)


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
    image[inode_offset:inode_offset + 2] = mode.to_bytes(2, 'little', signed=False)
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
    image[inode_offset:inode_offset + 2] = mode.to_bytes(2, 'little', signed=False)
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


def _frag_block_free_bits(cg_bytes: bytes, frag_index: int, frags_per_block: int) -> int:
    if frags_per_block <= 0:
        return 0
    bit_offset = frag_index % NBBY
    byte_offset = UFS_CG_FREE_OFFSET + (frag_index // NBBY)
    bits_to_cover = bit_offset + frags_per_block
    bytes_to_cover = (bits_to_cover + NBBY - 1) // NBBY
    window = int.from_bytes(cg_bytes[byte_offset:byte_offset + bytes_to_cover], 'little', signed=False)
    return (window >> bit_offset) & ((1 << frags_per_block) - 1)


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


def ufs_cg_metadata_size(filesystem: FilesystemCandidate) -> int:
    return max(
        UFS_CG_MAGIC_OFFSET + 4,
        UFS_CG_FREE_OFFSET + ((int(filesystem.details['fpg']) + NBBY - 1) // NBBY),
    )


def write_cg_block(image: bytearray, filesystem: FilesystemCandidate, cg: int, cg_bytes: bytearray) -> None:
    offset = cg_block_offset(filesystem, cg)
    metadata_size = min(len(cg_bytes), ufs_cg_metadata_size(filesystem))
    image[offset:offset + metadata_size] = cg_bytes[:metadata_size]
    _ufs_runtime_state(filesystem)['allocatable_cg_blocks'][cg] = cg_bytes


def ufs_cg_data_frag_count(fs: dict[str, Any], cg: int) -> int:
    frags_per_group = int(fs['fpg'])
    total_data_frags = int(fs.get('dsize', frags_per_group * int(fs['ncg'])))
    remaining = total_data_frags - (cg * frags_per_group)
    if remaining <= 0:
        return 0
    return min(frags_per_group, remaining)


def _looks_like_pristine_ufs_cg(cg_bytes: bytes) -> bool:
    return not any(cg_bytes)


def initialize_pristine_ufs_cg(image: bytearray, filesystem: FilesystemCandidate, cg: int) -> bytearray:
    fs = filesystem.details
    block_size = int(fs['bsize'])
    cg_bytes = bytearray(block_size)
    cg_ndblk = ufs_cg_data_frag_count(fs, cg)
    data_start_frag = ufs_cgdmin(fs, cg) % int(fs['fpg'])
    free_fragments = max(cg_ndblk - data_start_frag, 0)
    free_blocks = free_fragments // int(fs['frag'])
    free_fragment_remainder = free_fragments % int(fs['frag'])

    cg_ncyl = 0
    cpg = int(fs.get('cpg', 0))
    ncyl = int(fs.get('ncyl', 0))
    if cpg > 0:
        cg_ncyl = (ncyl % cpg) if cg == int(fs['ncg']) - 1 else cpg
    cg_bytes[UFS_CG_CGX_OFFSET:UFS_CG_CGX_OFFSET + 4] = cg.to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_NCYL_OFFSET:UFS_CG_NCYL_OFFSET + 2] = cg_ncyl.to_bytes(2, 'little', signed=False)
    cg_bytes[UFS_CG_NIBLK_OFFSET:UFS_CG_NIBLK_OFFSET + 2] = int(fs['ipg']).to_bytes(2, 'little', signed=False)
    cg_bytes[UFS_CG_NDBLK_OFFSET:UFS_CG_NDBLK_OFFSET + 4] = cg_ndblk.to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_CS_NDIR_OFFSET:UFS_CG_CS_NDIR_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_CS_NBFREE_OFFSET:UFS_CG_CS_NBFREE_OFFSET + 4] = free_blocks.to_bytes(4, 'little', signed=False)
    initial_nifree = int(fs['ipg']) - (2 if cg == 0 else 0)
    cg_bytes[UFS_CG_CS_NIFREE_OFFSET:UFS_CG_CS_NIFREE_OFFSET + 4] = initial_nifree.to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_CS_NFFREE_OFFSET:UFS_CG_CS_NFFREE_OFFSET + 4] = free_fragment_remainder.to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_IROTOR_OFFSET:UFS_CG_IROTOR_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_MAGIC_OFFSET:UFS_CG_MAGIC_OFFSET + 4] = UFS_CG_MAGIC.to_bytes(4, 'little', signed=False)

    if cg == 0:
        set_ufs_inode_state(cg_bytes, 0, used=True)
        set_ufs_inode_state(cg_bytes, 1, used=True)

    for frag_index in range(data_start_frag, cg_ndblk):
        set_frag_state(cg_bytes, frag_index, free=True)

    write_cg_block(image, filesystem, cg, cg_bytes)
    return cg_bytes


def read_allocatable_cg_block(image: bytearray, filesystem: FilesystemCandidate, cg: int) -> bytearray:
    cache = _ufs_runtime_state(filesystem)['allocatable_cg_blocks']
    cached = cache.get(cg)
    if cached is not None:
        return cached

    cg_bytes = read_cg_block(image, filesystem, cg)
    if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) == UFS_CG_MAGIC:
        cache[cg] = cg_bytes
        return cg_bytes
    if _looks_like_pristine_ufs_cg(cg_bytes):
        initialized = initialize_pristine_ufs_cg(image, filesystem, cg)
        cache[cg] = initialized
        return initialized
    cache[cg] = cg_bytes
    return cg_bytes


def _ufs_cg_block_hint_key(image: ImageBuffer, filesystem: FilesystemCandidate, cg: int) -> tuple[int, int, int, int]:
    return (id(image), filesystem.start_offset, filesystem.super_offset, cg)


def _normalize_ufs_cg_block_hint(fs: dict[str, Any], cg: int, cg_ndblk: int, frags_per_block: int, hint_frag: int | None) -> int:
    data_start_frag = ufs_cgdmin(fs, cg) % int(fs['fpg'])
    last_start_frag = cg_ndblk - frags_per_block
    if hint_frag is None or hint_frag < data_start_frag or hint_frag > last_start_frag:
        return data_start_frag
    return data_start_frag + (((hint_frag - data_start_frag) // frags_per_block) * frags_per_block)


def _set_ufs_cg_block_hint(image: ImageBuffer, filesystem: FilesystemCandidate, cg: int, cg_ndblk: int, frags_per_block: int, next_frag: int) -> None:
    del image
    hint = _normalize_ufs_cg_block_hint(filesystem.details, cg, cg_ndblk, frags_per_block, next_frag)
    _ufs_runtime_state(filesystem)['cg_block_hints'][cg] = hint


def _ufs_metadata_normalization_key(image: ImageBuffer, filesystem: FilesystemCandidate) -> tuple[int, int, int]:
    return (id(image), filesystem.start_offset, filesystem.super_offset)


def _ufs_partial_fragment_contribution(free_fragments: int, frags_per_block: int) -> int:
    if free_fragments <= 0 or free_fragments >= frags_per_block:
        return 0
    return free_fragments


def _ufs_cbtocylno(fs: dict[str, Any], frag_base: int) -> int:
    sectors_per_cylinder = int(fs.get('spc', 0))
    sectors_per_fragment = int(fs.get('nspf', 0))
    if sectors_per_cylinder <= 0 or sectors_per_fragment <= 0:
        return 0
    return (frag_base * sectors_per_fragment) // sectors_per_cylinder


def _ufs_cbtorpos(fs: dict[str, Any], frag_base: int) -> int:
    sectors_per_cylinder = int(fs.get('spc', 0))
    sectors_per_track = int(fs.get('nsect', 0))
    sectors_per_fragment = int(fs.get('nspf', 0))
    if sectors_per_cylinder <= 0 or sectors_per_track <= 0 or sectors_per_fragment <= 0:
        return 0
    return ((frag_base * sectors_per_fragment) % sectors_per_cylinder % sectors_per_track * NRPOS) // sectors_per_track


def _ufs_account_fragment_run(free_flags: list[bool], frsum: list[int]) -> None:
    run_length = 0
    for free in free_flags + [False]:
        if free:
            run_length += 1
            continue
        if 0 < run_length < len(frsum):
            frsum[run_length] += 1
        run_length = 0


def expected_ufs_cg_header(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    cg: int,
    cg_bytes: bytearray | bytes,
    *,
    trust_current_inode_counts: bool = False,
) -> tuple[bytearray, tuple[int, int, int, int]]:
    fs = filesystem.details
    ipg = int(fs['ipg'])
    ncg = int(fs['ncg'])
    cpg = int(fs.get('cpg', 0))
    ncyl = int(fs.get('ncyl', 0))
    frags_per_block = int(fs['frag'])
    cg_ndblk = u32(cg_bytes, UFS_CG_NDBLK_OFFSET)
    expected = bytearray(int(fs['bsize']))
    current_time = u32(cg_bytes, UFS_CG_TIME_OFFSET)
    expected_time = min(current_time, int(time.time())) if current_time else 0
    expected[UFS_CG_TIME_OFFSET:UFS_CG_TIME_OFFSET + 4] = expected_time.to_bytes(4, 'little', signed=False)
    expected[UFS_CG_CGX_OFFSET:UFS_CG_CGX_OFFSET + 4] = cg.to_bytes(4, 'little', signed=False)
    cg_ncyl = 0
    if cpg > 0:
        cg_ncyl = (ncyl % cpg) if cg == ncg - 1 else cpg
    expected[UFS_CG_NCYL_OFFSET:UFS_CG_NCYL_OFFSET + 2] = cg_ncyl.to_bytes(2, 'little', signed=False)
    expected[UFS_CG_NIBLK_OFFSET:UFS_CG_NIBLK_OFFSET + 2] = ipg.to_bytes(2, 'little', signed=False)
    expected[UFS_CG_NDBLK_OFFSET:UFS_CG_NDBLK_OFFSET + 4] = cg_ndblk.to_bytes(4, 'little', signed=False)

    if trust_current_inode_counts:
        ndir = u32(cg_bytes, UFS_CG_CS_NDIR_OFFSET)
        nifree = u32(cg_bytes, UFS_CG_CS_NIFREE_OFFSET)
    else:
        ndir = 0
        nifree = ipg
        if cg == 0:
            nifree -= 2

        for inode_index in range(ipg):
            if cg == 0 and inode_index < 2:
                continue
            if not is_ufs_inode_used(cg_bytes, inode_index):
                continue
            nifree -= 1
            inode_number = (cg * ipg) + inode_index
            inode = read_ufs_inode(image, filesystem.start_offset, fs, inode_number)
            if inode is not None and ufs_is_directory(inode):
                ndir += 1

    nbfree = 0
    nffree = 0
    frsum = [0] * MAXFRAG
    btot = [0] * MAXCPG
    bpos = [0] * (MAXCPG * NRPOS)
    full_frag_mask = (1 << frags_per_block) - 1

    full_block_limit = cg_ndblk - frags_per_block + 1
    frag_base = 0
    while frag_base < full_block_limit:
        free_bits = _frag_block_free_bits(cg_bytes, frag_base, frags_per_block)
        free_fragments = free_bits.bit_count()
        if free_fragments == frags_per_block:
            nbfree += 1
            cyl = _ufs_cbtocylno(fs, frag_base)
            pos = _ufs_cbtorpos(fs, frag_base)
            if 0 <= cyl < MAXCPG and 0 <= pos < NRPOS:
                btot[cyl] += 1
                bpos[(cyl * NRPOS) + pos] += 1
        elif free_fragments > 0:
            nffree += free_fragments
            free_flags = [bool(free_bits & (1 << frag_offset)) for frag_offset in range(frags_per_block)]
            _ufs_account_fragment_run(free_flags, frsum)
        frag_base += frags_per_block

    if frag_base < cg_ndblk:
        trailing_flags = [is_frag_free(cg_bytes, frag_index) for frag_index in range(frag_base, cg_ndblk)]
        trailing_free = sum(1 for flag in trailing_flags if flag)
        if trailing_free > 0:
            nffree += trailing_free
            _ufs_account_fragment_run(trailing_flags, frsum)

    expected[UFS_CG_CS_NDIR_OFFSET:UFS_CG_CS_NDIR_OFFSET + 4] = ndir.to_bytes(4, 'little', signed=False)
    expected[UFS_CG_CS_NBFREE_OFFSET:UFS_CG_CS_NBFREE_OFFSET + 4] = nbfree.to_bytes(4, 'little', signed=False)
    expected[UFS_CG_CS_NIFREE_OFFSET:UFS_CG_CS_NIFREE_OFFSET + 4] = nifree.to_bytes(4, 'little', signed=False)
    expected[UFS_CG_CS_NFFREE_OFFSET:UFS_CG_CS_NFFREE_OFFSET + 4] = nffree.to_bytes(4, 'little', signed=False)

    current_rotor = u32(cg_bytes, UFS_CG_ROTOR_OFFSET)
    current_frotor = u32(cg_bytes, UFS_CG_FROTOR_OFFSET)
    current_irotor = u32(cg_bytes, UFS_CG_IROTOR_OFFSET)
    expected[UFS_CG_ROTOR_OFFSET:UFS_CG_ROTOR_OFFSET + 4] = (current_rotor if current_rotor < cg_ndblk else 0).to_bytes(4, 'little', signed=False)
    expected[UFS_CG_FROTOR_OFFSET:UFS_CG_FROTOR_OFFSET + 4] = (current_frotor if current_frotor < cg_ndblk else 0).to_bytes(4, 'little', signed=False)
    expected[UFS_CG_IROTOR_OFFSET:UFS_CG_IROTOR_OFFSET + 4] = (current_irotor if current_irotor < ipg else 0).to_bytes(4, 'little', signed=False)

    for index, value in enumerate(frsum):
        start = UFS_CG_FRSUM_OFFSET + (index * 4)
        expected[start:start + 4] = value.to_bytes(4, 'little', signed=False)
    for index, value in enumerate(btot):
        start = UFS_CG_BTOT_OFFSET + (index * 4)
        expected[start:start + 4] = value.to_bytes(4, 'little', signed=False)
    for index, value in enumerate(bpos):
        start = UFS_CG_B_OFFSET + (index * 2)
        expected[start:start + 2] = value.to_bytes(2, 'little', signed=False)

    return expected, (ndir, nbfree, nifree, nffree)


def adjust_superblock_free_frags(image: bytearray, filesystem: FilesystemCandidate, delta: int) -> None:
    super_offset = filesystem.super_offset
    current = u32(image, super_offset + UFS_FS_CSTOTAL_NFFREE_OFFSET)
    image[super_offset + UFS_FS_CSTOTAL_NFFREE_OFFSET:super_offset + UFS_FS_CSTOTAL_NFFREE_OFFSET + 4] = (current + delta).to_bytes(4, 'little', signed=False)


def adjust_cg_free_frags(cg_bytes: bytearray, delta: int) -> None:
    current = u32(cg_bytes, UFS_CG_CS_NFFREE_OFFSET)
    cg_bytes[UFS_CG_CS_NFFREE_OFFSET:UFS_CG_CS_NFFREE_OFFSET + 4] = (current + delta).to_bytes(4, 'little', signed=False)


def ufs_csum_offset(filesystem: FilesystemCandidate, fs: dict[str, Any], cg: int) -> int | None:
    csaddr = int(fs.get('csaddr', 0))
    cssize = int(fs.get('cssize', 0))
    if csaddr <= 0 or cssize < (cg + 1) * UFS_CSUM_SIZE:
        return None
    return filesystem.start_offset + ufs_fsbtobytes(fs, csaddr) + (cg * UFS_CSUM_SIZE)


def _write_ufs_summary_counts(
    image: bytearray,
    filesystem: FilesystemCandidate,
    *,
    trust_current_inode_counts: bool,
) -> None:
    fs = filesystem.details
    total_ndir = 0
    total_nbfree = 0
    total_nifree = 0
    total_nffree = 0

    for cg in range(int(fs['ncg'])):
        cg_bytes = read_cg_block(image, filesystem, cg)
        if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
            if not _looks_like_pristine_ufs_cg(cg_bytes):
                raise SystemExit(f'error: invalid cylinder group {cg} while normalizing UFS metadata')
            cg_bytes = initialize_pristine_ufs_cg(image, filesystem, cg)

        expected, (ndir, nbfree, nifree, nffree) = expected_ufs_cg_header(
            image,
            filesystem,
            cg,
            cg_bytes,
            trust_current_inode_counts=trust_current_inode_counts,
        )
        cg_bytes[:UFS_CG_IUSED_OFFSET] = expected[:UFS_CG_IUSED_OFFSET]
        cg_bytes[UFS_CG_CS_NDIR_OFFSET:UFS_CG_CS_NDIR_OFFSET + 4] = ndir.to_bytes(4, 'little', signed=False)
        cg_bytes[UFS_CG_CS_NBFREE_OFFSET:UFS_CG_CS_NBFREE_OFFSET + 4] = nbfree.to_bytes(4, 'little', signed=False)
        cg_bytes[UFS_CG_CS_NIFREE_OFFSET:UFS_CG_CS_NIFREE_OFFSET + 4] = nifree.to_bytes(4, 'little', signed=False)
        cg_bytes[UFS_CG_CS_NFFREE_OFFSET:UFS_CG_CS_NFFREE_OFFSET + 4] = nffree.to_bytes(4, 'little', signed=False)
        write_cg_block(image, filesystem, cg, cg_bytes)

        csum_offset = ufs_csum_offset(filesystem, fs, cg)
        if csum_offset is not None:
            image[csum_offset:csum_offset + 4] = ndir.to_bytes(4, 'little', signed=False)
            image[csum_offset + 4:csum_offset + 8] = nbfree.to_bytes(4, 'little', signed=False)
            image[csum_offset + 8:csum_offset + 12] = nifree.to_bytes(4, 'little', signed=False)
            image[csum_offset + 12:csum_offset + 16] = nffree.to_bytes(4, 'little', signed=False)

        total_ndir += ndir
        total_nbfree += nbfree
        total_nifree += nifree
        total_nffree += nffree

    super_offset = filesystem.super_offset
    image[super_offset + UFS_FS_CSTOTAL_NDIR_OFFSET:super_offset + UFS_FS_CSTOTAL_NDIR_OFFSET + 4] = total_ndir.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CSTOTAL_NBFREE_OFFSET:super_offset + UFS_FS_CSTOTAL_NBFREE_OFFSET + 4] = total_nbfree.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CSTOTAL_NIFREE_OFFSET:super_offset + UFS_FS_CSTOTAL_NIFREE_OFFSET + 4] = total_nifree.to_bytes(4, 'little', signed=False)
    image[super_offset + UFS_FS_CSTOTAL_NFFREE_OFFSET:super_offset + UFS_FS_CSTOTAL_NFFREE_OFFSET + 4] = total_nffree.to_bytes(4, 'little', signed=False)


def recompute_ufs_summary_counts(image: bytearray, filesystem: FilesystemCandidate) -> None:
    _write_ufs_summary_counts(image, filesystem, trust_current_inode_counts=False)


def refresh_ufs_summary_layout(image: bytearray, filesystem: FilesystemCandidate) -> None:
    _write_ufs_summary_counts(image, filesystem, trust_current_inode_counts=True)


def maybe_recompute_ufs_summary_counts(
    image: bytearray,
    filesystem: FilesystemCandidate,
    *,
    recompute_summary: bool,
) -> None:
    if recompute_summary:
        recompute_ufs_summary_counts(image, filesystem)


def ensure_ufs_metadata_normalized(image: bytearray, filesystem: FilesystemCandidate) -> None:
    state = _ufs_runtime_state(filesystem)
    if state.get('metadata_normalized'):
        return
    recompute_ufs_summary_counts(image, filesystem)
    state['metadata_normalized'] = True


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
    ensure_ufs_metadata_normalized(image, filesystem)
    fs = filesystem.details
    total_cg = int(fs['ncg'])
    start_cg = 0 if preferred_inode is None else ufs_itog(fs, preferred_inode)
    preferred_local_inode = None if preferred_inode is None else preferred_inode % int(fs['ipg'])
    for attempt in range(total_cg):
        cg = (start_cg + attempt) % total_cg
        cg_bytes = read_allocatable_cg_block(image, filesystem, cg)
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
    ensure_ufs_metadata_normalized(image, filesystem)
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
    clear_ufs_inode(image, filesystem, inode_number)


def allocate_ufs_block(image: bytearray, filesystem: FilesystemCandidate, inode_number: int) -> int:
    ensure_ufs_metadata_normalized(image, filesystem)
    fs = filesystem.details
    start_cg = ufs_itog(fs, inode_number)
    total_cg = int(fs['ncg'])
    frags_per_block = int(fs['frag'])
    block_size = int(fs['bsize'])
    full_frag_mask = (1 << frags_per_block) - 1
    for attempt in range(total_cg):
        cg = (start_cg + attempt) % total_cg
        cg_bytes = read_allocatable_cg_block(image, filesystem, cg)
        if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
            continue
        if u32(cg_bytes, UFS_CG_CS_NBFREE_OFFSET) == 0:
            continue
        cg_ndblk = u32(cg_bytes, UFS_CG_NDBLK_OFFSET)
        data_start_frag = ufs_cgdmin(fs, cg) % int(fs['fpg'])
        last_start_frag = cg_ndblk - frags_per_block
        if last_start_frag < data_start_frag:
            continue
        start_frag = _normalize_ufs_cg_block_hint(
            fs,
            cg,
            cg_ndblk,
            frags_per_block,
            _ufs_runtime_state(filesystem)['cg_block_hints'].get(cg),
        )
        for frag_range_start, frag_range_stop in ((start_frag, last_start_frag + 1), (data_start_frag, start_frag)):
            for frag_index in range(frag_range_start, frag_range_stop, frags_per_block):
                if _frag_block_free_bits(cg_bytes, frag_index, frags_per_block) != full_frag_mask:
                    continue
                for frag_offset in range(frags_per_block):
                    set_frag_state(cg_bytes, frag_index + frag_offset, free=False)
                adjust_cg_free_blocks(cg_bytes, -1)
                write_cg_block(image, filesystem, cg, cg_bytes)
                adjust_superblock_free_blocks(image, filesystem, -1)
                _set_ufs_cg_block_hint(image, filesystem, cg, cg_ndblk, frags_per_block, frag_index + frags_per_block)
                fs_block = ufs_cgbase(fs, cg) + frag_index
                block_offset = ufs_data_block_offset(filesystem.start_offset, fs, fs_block)
                image[block_offset:block_offset + block_size] = b'\0' * block_size
                return fs_block
    raise SystemExit('error: no free UFS blocks remain for allocation')


def allocate_ufs_fragments(image: bytearray, filesystem: FilesystemCandidate, inode_number: int, allocation_bytes: int) -> int:
    ensure_ufs_metadata_normalized(image, filesystem)
    fs = filesystem.details
    fragment_size = int(fs['fsize'])
    frags_needed = allocation_bytes // fragment_size
    if frags_needed <= 0 or allocation_bytes >= int(fs['bsize']):
        raise SystemExit(f'error: invalid UFS fragment allocation request for {allocation_bytes} bytes')
    start_cg = ufs_itog(fs, inode_number)
    total_cg = int(fs['ncg'])
    frags_per_block = int(fs['frag'])
    full_frag_mask = (1 << frags_per_block) - 1
    for attempt in range(total_cg):
        cg = (start_cg + attempt) % total_cg
        cg_bytes = read_allocatable_cg_block(image, filesystem, cg)
        if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) != UFS_CG_MAGIC:
            continue
        if u32(cg_bytes, UFS_CG_CS_NBFREE_OFFSET) == 0:
            continue
        cg_ndblk = u32(cg_bytes, UFS_CG_NDBLK_OFFSET)
        data_start_frag = ufs_cgdmin(fs, cg) % int(fs['fpg'])
        last_start_frag = cg_ndblk - frags_per_block
        if last_start_frag < data_start_frag:
            continue
        start_frag = _normalize_ufs_cg_block_hint(
            fs,
            cg,
            cg_ndblk,
            frags_per_block,
            _ufs_runtime_state(filesystem)['cg_block_hints'].get(cg),
        )
        for frag_range_start, frag_range_stop in ((start_frag, last_start_frag + 1), (data_start_frag, start_frag)):
            for frag_index in range(frag_range_start, frag_range_stop, frags_per_block):
                if _frag_block_free_bits(cg_bytes, frag_index, frags_per_block) != full_frag_mask:
                    continue
                for frag_offset in range(frags_needed):
                    set_frag_state(cg_bytes, frag_index + frag_offset, free=False)
                free_after = frags_per_block - frags_needed
                adjust_cg_free_blocks(cg_bytes, -1)
                adjust_cg_free_frags(
                    cg_bytes,
                    _ufs_partial_fragment_contribution(free_after, frags_per_block),
                )
                write_cg_block(image, filesystem, cg, cg_bytes)
                adjust_superblock_free_blocks(image, filesystem, -1)
                adjust_superblock_free_frags(
                    image,
                    filesystem,
                    _ufs_partial_fragment_contribution(free_after, frags_per_block),
                )
                _set_ufs_cg_block_hint(image, filesystem, cg, cg_ndblk, frags_per_block, frag_index + frags_per_block)
                fs_block = ufs_cgbase(fs, cg) + frag_index
                block_offset = ufs_data_block_offset(filesystem.start_offset, fs, fs_block)
                image[block_offset:block_offset + allocation_bytes] = b'\0' * allocation_bytes
                return fs_block
    raise SystemExit('error: no free UFS fragments remain for allocation')


def free_ufs_block(image: bytearray, filesystem: FilesystemCandidate, fs_block: int) -> None:
    ensure_ufs_metadata_normalized(image, filesystem)
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
    ensure_ufs_metadata_normalized(image, filesystem)
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
    block_base = frag_index - (frag_index % frags_per_block)
    full_frag_mask = (1 << frags_per_block) - 1
    free_before = _frag_block_free_bits(cg_bytes, block_base, frags_per_block).bit_count()
    for frag_offset in range(frags_to_free):
        set_frag_state(cg_bytes, frag_index + frag_offset, free=True)
    free_after_bits = _frag_block_free_bits(cg_bytes, block_base, frags_per_block)
    free_after = free_after_bits.bit_count()
    frag_delta = (
        _ufs_partial_fragment_contribution(free_after, frags_per_block)
        - _ufs_partial_fragment_contribution(free_before, frags_per_block)
    )
    if frag_delta:
        adjust_cg_free_frags(cg_bytes, frag_delta)
        adjust_superblock_free_frags(image, filesystem, frag_delta)
    if free_after_bits == full_frag_mask:
        adjust_cg_free_blocks(cg_bytes, 1)
        adjust_superblock_free_blocks(image, filesystem, 1)
    write_cg_block(image, filesystem, cg, cg_bytes)


def write_ufs_pointer_block(image: bytearray, filesystem: FilesystemCandidate, fs_block: int, pointers: list[int]) -> None:
    block_offset = ufs_data_block_offset(filesystem.start_offset, filesystem.details, fs_block)
    block_size = int(filesystem.details['bsize'])
    pointer_count = int(filesystem.details['nindir'])
    normalized_pointers = [int(pointer) for pointer in pointers[:pointer_count]]
    cached_pointers = normalized_pointers + ([0] * (pointer_count - len(normalized_pointers)))
    raw = bytearray(block_size)
    for index, pointer in enumerate(cached_pointers):
        raw[index * 4:(index + 1) * 4] = int(pointer).to_bytes(4, 'little', signed=False)
    image[block_offset:block_offset + block_size] = raw
    _ufs_runtime_state(filesystem)['pointer_blocks'][fs_block] = cached_pointers


def _get_ufs_pointer_block_cache_entry(
    image: bytearray,
    filesystem: FilesystemCandidate,
    fs_block: int,
    pointer_block_cache: dict[int, list[int]],
) -> list[int]:
    pointers = pointer_block_cache.get(fs_block)
    if pointers is None:
        pointers = read_ufs_pointer_block(image, filesystem, fs_block)
        pointer_block_cache[fs_block] = pointers
    return pointers


def _flush_ufs_pointer_block_cache(
    image: bytearray,
    filesystem: FilesystemCandidate,
    pointer_block_cache: dict[int, list[int]],
    dirty_pointer_blocks: set[int],
) -> None:
    for fs_block in dirty_pointer_blocks:
        write_ufs_pointer_block(image, filesystem, fs_block, pointer_block_cache[fs_block])


def build_ufs_pointer_tree(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    levels: int,
    data_blocks: list[int],
) -> tuple[int, list[int]]:
    if not data_blocks:
        return 0, []
    pointer_count = int(filesystem.details['nindir'])
    if levels == 1:
        root_block = allocate_ufs_block(image, filesystem, inode_number)
        write_ufs_pointer_block(image, filesystem, root_block, data_blocks[:pointer_count])
        return root_block, [root_block]

    child_capacity = pointer_count ** (levels - 1)
    child_roots: list[int] = []
    pointer_blocks: list[int] = []
    remaining = list(data_blocks)
    while remaining:
        chunk = remaining[:child_capacity]
        remaining = remaining[child_capacity:]
        child_root, child_pointer_blocks = build_ufs_pointer_tree(image, filesystem, inode_number, levels - 1, chunk)
        child_roots.append(child_root)
        pointer_blocks.extend(child_pointer_blocks)
    root_block = allocate_ufs_block(image, filesystem, inode_number)
    write_ufs_pointer_block(image, filesystem, root_block, child_roots)
    return root_block, [root_block] + pointer_blocks


def build_ufs_inode_pointer_structure(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    data_blocks: list[int],
) -> tuple[int, list[int]]:
    nindir = int(filesystem.details['nindir'])
    direct_blocks = data_blocks[:UFS_NDADDR]
    indirect_roots: list[int] = []
    new_pointer_blocks: list[int] = []
    remaining_data_blocks = data_blocks[UFS_NDADDR:]
    for levels in range(1, 4):
        level_capacity = nindir ** levels
        level_data_blocks = remaining_data_blocks[:level_capacity]
        remaining_data_blocks = remaining_data_blocks[level_capacity:]
        if level_data_blocks:
            root_block, pointer_blocks = build_ufs_pointer_tree(image, filesystem, inode_number, levels, level_data_blocks)
            indirect_roots.append(root_block)
            new_pointer_blocks.extend(pointer_blocks)
        else:
            indirect_roots.append(0)

    write_ufs_block_lists(
        image,
        filesystem,
        inode_number,
        direct_blocks + ([0] * (UFS_NDADDR - len(direct_blocks))),
        indirect_roots,
    )
    return len(new_pointer_blocks), new_pointer_blocks


def append_ufs_pointer_tree(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    root_block: int,
    levels: int,
    logical_index: int,
    data_block: int,
    pointer_block_cache: dict[int, list[int]] | None = None,
    dirty_pointer_blocks: set[int] | None = None,
) -> tuple[int, list[int]]:
    pointer_count = int(filesystem.details['nindir'])
    allocated_pointer_blocks: list[int] = []
    if pointer_block_cache is None:
        pointer_block_cache = {}
    if dirty_pointer_blocks is None:
        dirty_pointer_blocks = set()

    if root_block == 0:
        root_block = allocate_ufs_block(image, filesystem, inode_number)
        allocated_pointer_blocks.append(root_block)
        pointers = [0] * pointer_count
        pointer_block_cache[root_block] = pointers
    else:
        pointers = _get_ufs_pointer_block_cache_entry(image, filesystem, root_block, pointer_block_cache)

    if levels == 1:
        pointers[logical_index] = data_block
        dirty_pointer_blocks.add(root_block)
        return root_block, allocated_pointer_blocks

    child_capacity = pointer_count ** (levels - 1)
    child_slot = logical_index // child_capacity
    child_index = logical_index % child_capacity
    child_root, child_pointer_blocks = append_ufs_pointer_tree(
        image,
        filesystem,
        inode_number,
        int(pointers[child_slot]),
        levels - 1,
        child_index,
        data_block,
        pointer_block_cache,
        dirty_pointer_blocks,
    )
    pointers[child_slot] = child_root
    dirty_pointer_blocks.add(root_block)
    return root_block, allocated_pointer_blocks + child_pointer_blocks


def append_ufs_inode_pointer_structure(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    inode: dict[str, int | list[int]],
    existing_data_block_count: int,
    appended_data_blocks: list[int],
    current_pointer_blocks: list[int],
) -> list[int]:
    direct_blocks = inode['direct_blocks']
    indirect_blocks = inode['indirect_blocks']
    if not isinstance(direct_blocks, list) or not isinstance(indirect_blocks, list):
        raise SystemExit(f'error: inode {inode_number} does not have writable UFS block lists')

    updated_direct_blocks = list(direct_blocks)
    updated_indirect_blocks = list(indirect_blocks)
    pointer_blocks_state = list(current_pointer_blocks)
    pointer_block_cache: dict[int, list[int]] = {}
    dirty_pointer_blocks: set[int] = set()
    nindir = int(filesystem.details['nindir'])
    logical_block_index = existing_data_block_count

    for data_block in appended_data_blocks:
        if logical_block_index < UFS_NDADDR:
            updated_direct_blocks[logical_block_index] = data_block
            logical_block_index += 1
            continue

        remaining_index = logical_block_index - UFS_NDADDR
        for levels in range(1, 4):
            level_capacity = nindir ** levels
            if remaining_index < level_capacity:
                root_block, new_pointer_blocks = append_ufs_pointer_tree(
                    image,
                    filesystem,
                    inode_number,
                    int(updated_indirect_blocks[levels - 1]),
                    levels,
                    remaining_index,
                    data_block,
                    pointer_block_cache,
                    dirty_pointer_blocks,
                )
                updated_indirect_blocks[levels - 1] = root_block
                pointer_blocks_state.extend(new_pointer_blocks)
                break
            remaining_index -= level_capacity
        logical_block_index += 1

    if dirty_pointer_blocks:
        _flush_ufs_pointer_block_cache(image, filesystem, pointer_block_cache, dirty_pointer_blocks)

    inode['direct_blocks'] = updated_direct_blocks
    inode['indirect_blocks'] = updated_indirect_blocks
    write_ufs_block_lists(
        image,
        filesystem,
        inode_number,
        updated_direct_blocks,
        updated_indirect_blocks,
    )
    return pointer_blocks_state


def read_ufs_data_range(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    data_blocks: list[int],
    offset: int,
    size: int,
) -> bytes:
    if size <= 0:
        return b''

    block_size = int(filesystem.details['bsize'])
    end_offset = offset + size
    data = bytearray()
    start_block = max(0, offset // block_size)
    end_block = min(len(data_blocks), (end_offset + block_size - 1) // block_size)
    for block_index in range(start_block, end_block):
        fs_block = data_blocks[block_index]
        logical_start = block_index * block_size
        logical_end = logical_start + block_size

        block_inner_start = max(0, offset - logical_start)
        block_inner_end = min(block_size, end_offset - logical_start)
        if block_inner_start >= block_inner_end:
            continue

        block_offset = ufs_data_block_offset(filesystem.start_offset, filesystem.details, int(fs_block))
        data.extend(image[block_offset + block_inner_start:block_offset + block_inner_end])
    return bytes(data)


def read_ufs_inode_range(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    inode: dict[str, int | list[int]],
    offset: int,
    size: int,
) -> bytes:
    inode_size = int(inode['size'])
    if size <= 0 or offset >= inode_size:
        return b''
    clamped_offset = max(0, offset)
    clamped_size = min(size, inode_size - clamped_offset)
    if clamped_size <= 0:
        return b''
    return read_ufs_data_range(
        image,
        filesystem,
        ufs_inode_data_blocks(image, filesystem, inode),
        clamped_offset,
        clamped_size,
    )


def write_ufs_data_range(
    image: bytearray,
    filesystem: FilesystemCandidate,
    data_blocks: list[int],
    allocation_sizes: list[int],
    offset: int,
    data: bytes,
) -> None:
    if not data:
        return

    block_size = int(filesystem.details['bsize'])
    end_offset = offset + len(data)
    start_block = max(0, offset // block_size)
    end_block = min(len(data_blocks), len(allocation_sizes), (end_offset + block_size - 1) // block_size)
    for block_index in range(start_block, end_block):
        fs_block = data_blocks[block_index]
        allocation_bytes = allocation_sizes[block_index]
        logical_start = block_index * block_size
        logical_end = logical_start + block_size

        block_inner_start = max(0, offset - logical_start)
        block_inner_end = min(block_size, end_offset - logical_start, allocation_bytes)
        if block_inner_start >= block_inner_end:
            continue

        data_start = logical_start + block_inner_start - offset
        data_end = logical_start + block_inner_end - offset
        block_offset = ufs_data_block_offset(filesystem.start_offset, filesystem.details, int(fs_block))
        image[block_offset + block_inner_start:block_offset + block_inner_end] = data[data_start:data_end]


def zero_ufs_data_range(
    image: bytearray,
    filesystem: FilesystemCandidate,
    data_blocks: list[int],
    allocation_sizes: list[int],
    offset: int,
    size: int,
) -> None:
    if size <= 0:
        return

    block_size = int(filesystem.details['bsize'])
    end_offset = offset + size
    start_block = max(0, offset // block_size)
    end_block = min(len(data_blocks), len(allocation_sizes), (end_offset + block_size - 1) // block_size)
    for block_index in range(start_block, end_block):
        fs_block = data_blocks[block_index]
        allocation_bytes = allocation_sizes[block_index]
        logical_start = block_index * block_size
        logical_end = logical_start + block_size

        block_inner_start = max(0, offset - logical_start)
        block_inner_end = min(block_size, end_offset - logical_start, allocation_bytes)
        if block_inner_start >= block_inner_end:
            continue

        block_offset = ufs_data_block_offset(filesystem.start_offset, filesystem.details, int(fs_block))
        image[block_offset + block_inner_start:block_offset + block_inner_end] = b'\0' * (block_inner_end - block_inner_start)


def common_ufs_allocation_prefix(current_allocation_sizes: list[int], requested_allocation_sizes: list[int]) -> int:
    prefix = 0
    max_prefix = min(len(current_allocation_sizes), len(requested_allocation_sizes))
    while prefix < max_prefix and current_allocation_sizes[prefix] == requested_allocation_sizes[prefix]:
        prefix += 1
    return prefix


def reallocate_ufs_inode_suffix(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    current_data_blocks: list[int],
    current_allocation_sizes: list[int],
    current_pointer_blocks: list[int],
    requested_allocation_sizes: list[int],
    preserved_size: int,
) -> tuple[list[int], int, int, list[int]]:
    block_size = int(filesystem.details['bsize'])
    prefix_blocks = common_ufs_allocation_prefix(current_allocation_sizes, requested_allocation_sizes)
    preserved_data_blocks = list(current_data_blocks[:prefix_blocks])
    old_suffix_blocks = current_data_blocks[prefix_blocks:]
    old_suffix_allocation_sizes = current_allocation_sizes[prefix_blocks:]
    new_suffix_allocation_sizes = requested_allocation_sizes[prefix_blocks:]
    prefix_offset = prefix_blocks * block_size
    preserved_suffix_bytes = max(0, preserved_size - prefix_offset)
    suffix_seed = read_ufs_data_range(image, filesystem, old_suffix_blocks, 0, preserved_suffix_bytes)

    for pointer_block in reversed(current_pointer_blocks):
        free_ufs_allocation(image, filesystem, pointer_block, block_size)
    for fs_block, allocation_bytes in zip(reversed(old_suffix_blocks), reversed(old_suffix_allocation_sizes)):
        free_ufs_allocation(image, filesystem, fs_block, allocation_bytes)

    new_suffix_blocks = [
        allocate_ufs_allocation(image, filesystem, inode_number, allocation_bytes)
        for allocation_bytes in new_suffix_allocation_sizes
    ]
    if suffix_seed:
        write_ufs_data_range(image, filesystem, new_suffix_blocks, new_suffix_allocation_sizes, 0, suffix_seed)

    rebuilt_data_blocks = preserved_data_blocks + new_suffix_blocks
    new_pointer_block_count, new_pointer_blocks = build_ufs_inode_pointer_structure(image, filesystem, inode_number, rebuilt_data_blocks)
    write_ufs_inode_blocks(
        image,
        filesystem,
        inode_number,
        sum(allocation_bytes // SECTOR_SIZE for allocation_bytes in requested_allocation_sizes)
        + (new_pointer_block_count * (block_size // SECTOR_SIZE)),
    )
    return rebuilt_data_blocks, prefix_blocks, new_pointer_block_count, new_pointer_blocks


def apply_ufs_inode_truncate(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    inode: dict[str, int | list[int]],
    size: int,
    target_path: str | None = None,
) -> dict[str, int | str | list[int] | None]:
    old_size = int(inode['size'])
    target_label = target_path or f'inode {inode_number}'
    if size == old_size:
        return {
            'target_path': target_label,
            'inode': inode_number,
            'old_size': old_size,
            'new_size': size,
            'strategy': 'in-place',
        }

    current_data_blocks = ufs_inode_data_blocks(image, filesystem, inode)
    current_allocation_sizes = ufs_allocation_byte_sizes(filesystem.details, old_size)
    requested_allocation_sizes = ufs_allocation_byte_sizes(filesystem.details, size)
    original_data_block_count = len(current_data_blocks)

    if requested_allocation_sizes == current_allocation_sizes:
        if size > old_size:
            zero_ufs_data_range(image, filesystem, current_data_blocks, current_allocation_sizes, old_size, size - old_size)
        write_ufs_inode_size(image, filesystem, inode_number, size)
        return {
            'target_path': target_label,
            'inode': inode_number,
            'old_size': old_size,
            'new_size': size,
            'old_data_blocks': original_data_block_count,
            'new_data_blocks': len(current_data_blocks),
            'old_pointer_blocks': 0,
            'new_pointer_blocks': 0,
            'strategy': 'in-place',
        }

    current_pointer_blocks = ufs_inode_pointer_blocks(image, filesystem, inode)
    original_pointer_block_count = len(current_pointer_blocks)
    rebuilt_data_blocks, _, new_pointer_block_count, _ = reallocate_ufs_inode_suffix(
        image,
        filesystem,
        inode_number,
        current_data_blocks,
        current_allocation_sizes,
        current_pointer_blocks,
        requested_allocation_sizes,
        min(old_size, size),
    )
    if size > old_size:
        zero_ufs_data_range(image, filesystem, rebuilt_data_blocks, requested_allocation_sizes, old_size, size - old_size)
    write_ufs_inode_size(image, filesystem, inode_number, size)
    return {
        'target_path': target_label,
        'inode': inode_number,
        'old_size': old_size,
        'new_size': size,
        'old_data_blocks': original_data_block_count,
        'new_data_blocks': len(rebuilt_data_blocks),
        'old_pointer_blocks': original_pointer_block_count,
        'new_pointer_blocks': new_pointer_block_count,
        'strategy': 'reallocated-suffix',
    }


def apply_ufs_inode_write(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    inode: dict[str, int | list[int]],
    offset: int,
    data: bytes,
    target_path: str | None = None,
    current_data_blocks: list[int] | None = None,
    current_allocation_sizes: list[int] | None = None,
    current_pointer_blocks: list[int] | None = None,
) -> dict[str, int | str | list[int] | None]:
    old_size = int(inode['size'])
    new_size = max(old_size, offset + len(data))
    target_label = target_path or f'inode {inode_number}'
    block_size = int(filesystem.details['bsize'])
    nindir = int(filesystem.details['nindir'])
    max_blocks = UFS_NDADDR + nindir + (nindir ** 2) + (nindir ** 3)
    needed_blocks = 0 if new_size == 0 else (new_size + block_size - 1) // block_size
    if needed_blocks > max_blocks:
        raise SystemExit(f'error: replacement for {target_label} exceeds the host-tool UFS addressing limit ({needed_blocks} blocks)')

    current_data_blocks = list(current_data_blocks) if current_data_blocks is not None else ufs_inode_data_blocks(image, filesystem, inode)
    current_allocation_sizes = list(current_allocation_sizes) if current_allocation_sizes is not None else ufs_allocation_byte_sizes(filesystem.details, old_size)
    requested_allocation_sizes = extend_ufs_allocation_byte_sizes(
        filesystem.details,
        current_allocation_sizes,
        old_size,
        new_size,
    )
    if requested_allocation_sizes[:len(current_allocation_sizes)] != current_allocation_sizes:
        pointer_blocks = list(current_pointer_blocks) if current_pointer_blocks is not None else ufs_inode_pointer_blocks(image, filesystem, inode)
        original_data_block_count = len(current_data_blocks)
        original_pointer_block_count = len(pointer_blocks)
        rebuilt_data_blocks, _, new_pointer_block_count, new_pointer_blocks = reallocate_ufs_inode_suffix(
            image,
            filesystem,
            inode_number,
            current_data_blocks,
            current_allocation_sizes,
            pointer_blocks,
            requested_allocation_sizes,
            old_size,
        )
        if offset > old_size:
            zero_ufs_data_range(
                image,
                filesystem,
                rebuilt_data_blocks,
                requested_allocation_sizes,
                old_size,
                offset - old_size,
            )
        write_ufs_data_range(image, filesystem, rebuilt_data_blocks, requested_allocation_sizes, offset, data)
        write_ufs_inode_size(image, filesystem, inode_number, new_size)
        return {
            'target_path': target_label,
            'inode': inode_number,
            'old_size': old_size,
            'new_size': new_size,
            'old_data_blocks': original_data_block_count,
            'new_data_blocks': len(rebuilt_data_blocks),
            'old_pointer_blocks': original_pointer_block_count,
            'new_pointer_blocks': new_pointer_block_count,
            'strategy': 'reallocated-suffix',
            'data_blocks_state': rebuilt_data_blocks,
            'allocation_sizes_state': requested_allocation_sizes,
            'pointer_blocks_state': new_pointer_blocks,
        }

    original_data_block_count = len(current_data_blocks)
    all_data_blocks = list(current_data_blocks)
    appended_allocation_sizes = requested_allocation_sizes[len(current_allocation_sizes):]
    original_pointer_block_count = 0
    new_pointer_block_count = 0
    pointer_blocks_state = list(current_pointer_blocks) if current_pointer_blocks is not None else None

    if appended_allocation_sizes:
        pointer_blocks = list(current_pointer_blocks) if current_pointer_blocks is not None else ufs_inode_pointer_blocks(image, filesystem, inode)
        original_pointer_block_count = len(pointer_blocks)
        new_pointer_block_count = original_pointer_block_count
        appended_data_blocks = [
            allocate_ufs_allocation(image, filesystem, inode_number, allocation_bytes)
            for allocation_bytes in appended_allocation_sizes
        ]
        all_data_blocks.extend(appended_data_blocks)
        pointer_blocks_state = append_ufs_inode_pointer_structure(
            image,
            filesystem,
            inode_number,
            inode,
            original_data_block_count,
            appended_data_blocks,
            pointer_blocks,
        )
        new_pointer_block_count = len(pointer_blocks_state)
        write_ufs_inode_blocks(
            image,
            filesystem,
            inode_number,
            int(inode['blocks'])
            + sum(allocation_bytes // SECTOR_SIZE for allocation_bytes in appended_allocation_sizes)
            + ((new_pointer_block_count - original_pointer_block_count) * (block_size // SECTOR_SIZE)),
        )
        inode['blocks'] = (
            int(inode['blocks'])
            + sum(allocation_bytes // SECTOR_SIZE for allocation_bytes in appended_allocation_sizes)
            + ((new_pointer_block_count - original_pointer_block_count) * (block_size // SECTOR_SIZE))
        )

    if offset > old_size:
        zero_ufs_data_range(
            image,
            filesystem,
            all_data_blocks,
            requested_allocation_sizes,
            old_size,
            offset - old_size,
        )
    write_ufs_data_range(image, filesystem, all_data_blocks, requested_allocation_sizes, offset, data)
    write_ufs_inode_size(image, filesystem, inode_number, new_size)
    return {
        'target_path': target_label,
        'inode': inode_number,
        'old_size': old_size,
        'new_size': new_size,
        'old_data_blocks': original_data_block_count,
        'new_data_blocks': len(all_data_blocks),
        'old_pointer_blocks': original_pointer_block_count,
        'new_pointer_blocks': new_pointer_block_count,
        'strategy': 'in-place',
        'data_blocks_state': all_data_blocks,
        'allocation_sizes_state': requested_allocation_sizes,
        'pointer_blocks_state': pointer_blocks_state,
    }


def apply_ufs_inode_replacement(
    image: bytearray,
    filesystem: FilesystemCandidate,
    inode_number: int,
    inode: dict[str, int | list[int]],
    new_data: bytes,
    target_path: str | None = None,
) -> dict[str, int | str]:
    old_size = int(inode['size'])
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
        block_offset = ufs_data_block_offset(filesystem.start_offset, filesystem.details, int(fs_block))
        chunk = remaining[:block_size]
        image[block_offset:block_offset + allocation_bytes] = chunk.ljust(allocation_bytes, b'\0')
        remaining = remaining[block_size:]

    new_pointer_block_count, _ = build_ufs_inode_pointer_structure(image, filesystem, inode_number, current_data_blocks)
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
        'old_size': old_size,
        'new_size': len(new_data),
        'old_data_blocks': original_data_block_count,
        'new_data_blocks': len(current_data_blocks),
        'old_pointer_blocks': original_pointer_block_count,
        'new_pointer_blocks': new_pointer_block_count,
    }


def apply_ufs_replacement(image: bytearray, filesystem: FilesystemCandidate, target_path: str, new_data: bytes) -> dict[str, int | str]:
    resolved = resolve_ufs_path(image, filesystem, target_path)
    if resolved is None:
        raise SystemExit(f'error: could not resolve {target_path} inside the ufs filesystem')
    inode_number, inode = resolved
    return apply_ufs_inode_replacement(image, filesystem, inode_number, inode, new_data, target_path=target_path)


def add_ufs_directory_entry(
    image: bytearray,
    filesystem: FilesystemCandidate,
    directory_inode_number: int,
    directory_inode: dict[str, int | list[int]],
    entry_name: str,
    child_inode_number: int,
) -> dict[str, int | str | list[int] | None]:
    directory_size = int(directory_inode['size'])
    rounded_length = ((directory_size + UFS_DIRBLKSIZ - 1) // UFS_DIRBLKSIZ) * UFS_DIRBLKSIZ
    if rounded_length == 0:
        rounded_length = UFS_DIRBLKSIZ

    # Fast path for the overwhelmingly common case of appending to a directory
    # that is being populated sequentially: free space lives in the final
    # directory block, so try inserting there before falling back to a full
    # scan. Reading and re-decoding the entire directory on every insert makes
    # populating a large directory (e.g. /usr/share/man with thousands of
    # entries) quadratic; this keeps the append case close to O(1).
    if rounded_length > UFS_DIRBLKSIZ:
        last_block_offset = rounded_length - UFS_DIRBLKSIZ
        last_block_span = max(0, min(UFS_DIRBLKSIZ, directory_size - last_block_offset))
        if last_block_span > 0:
            last_block_bytes = read_ufs_inode_range(
                image, filesystem, directory_inode, last_block_offset, last_block_span
            )
            try:
                updated_block = insert_ufs_directory_entry(
                    last_block_bytes, last_block_span, child_inode_number, entry_name
                )
            except ValueError:
                pass
            else:
                return apply_ufs_inode_write(
                    image, filesystem, directory_inode_number, directory_inode, last_block_offset, updated_block
                )

    directory_bytes = read_ufs_inode_bytes(image, filesystem, directory_inode)
    for block_offset in range(0, rounded_length, UFS_DIRBLKSIZ):
        block_span = max(0, min(UFS_DIRBLKSIZ, directory_size - block_offset))
        block_bytes = directory_bytes[block_offset:block_offset + block_span]
        try:
            updated_block = insert_ufs_directory_entry(block_bytes, block_span, child_inode_number, entry_name)
        except ValueError:
            continue
        return apply_ufs_inode_write(image, filesystem, directory_inode_number, directory_inode, block_offset, updated_block)

    new_block = insert_ufs_directory_entry(b'', 0, child_inode_number, entry_name)
    return apply_ufs_inode_write(image, filesystem, directory_inode_number, directory_inode, rounded_length, new_block)


def delete_ufs_directory_entry(
    image: bytearray,
    filesystem: FilesystemCandidate,
    directory_inode_number: int,
    directory_inode: dict[str, int | list[int]],
    entry_name: str,
) -> dict[str, int | str | list[int] | None]:
    directory_size = int(directory_inode['size'])
    directory_bytes = read_ufs_inode_bytes(image, filesystem, directory_inode)
    for block_offset in range(0, directory_size, UFS_DIRBLKSIZ):
        block_span = min(UFS_DIRBLKSIZ, directory_size - block_offset)
        block_bytes = directory_bytes[block_offset:block_offset + block_span]
        try:
            updated_block = remove_ufs_directory_entry(block_bytes, block_span, entry_name)
        except ValueError:
            continue
        return apply_ufs_inode_write(image, filesystem, directory_inode_number, directory_inode, block_offset, updated_block)
    raise SystemExit(f'error: could not find directory entry {entry_name!r} to remove')


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
    directory_size = int(directory_inode['size'])
    directory_bytes = read_ufs_inode_bytes(image, filesystem, directory_inode)
    for block_offset in range(0, directory_size, UFS_DIRBLKSIZ):
        block_span = min(UFS_DIRBLKSIZ, directory_size - block_offset)
        block_bytes = directory_bytes[block_offset:block_offset + block_span]
        try:
            updated_block = rewrite_ufs_directory_entry_inode(block_bytes, block_span, '..', parent_inode_number)
        except ValueError:
            continue
        apply_ufs_inode_write(image, filesystem, directory_inode_number, directory_inode, block_offset, updated_block)
        return
    raise SystemExit("error: could not find directory entry '..' to rewrite")


def create_ufs_file(
    image: bytearray,
    filesystem: FilesystemCandidate,
    target_path: str,
    file_bytes: bytes,
    mode: int = 0o644,
    uid: int = 0,
    gid: int = 0,
    timestamp: int = 0,
    *,
    parent_inode_number: int | None = None,
    recompute_summary: bool = True,
) -> dict[str, int | str]:
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_creation_parent(
        image,
        filesystem,
        target_path,
        parent_inode_number=parent_inode_number,
    )
    return create_ufs_file_in_parent(
        image,
        filesystem,
        parent_inode_number,
        parent_inode,
        entry_name,
        file_bytes,
        target_path=target_path,
        mode=mode,
        uid=uid,
        gid=gid,
        timestamp=timestamp,
        recompute_summary=recompute_summary,
    )


def create_ufs_file_in_parent(
    image: bytearray,
    filesystem: FilesystemCandidate,
    parent_inode_number: int,
    parent_inode: dict[str, int | list[int]],
    entry_name: str,
    file_bytes: bytes,
    *,
    target_path: str | None = None,
    mode: int = 0o644,
    uid: int = 0,
    gid: int = 0,
    timestamp: int = 0,
    recompute_summary: bool = True,
    check_existing: bool = True,
) -> dict[str, int | str]:
    if not ufs_is_directory(parent_inode):
        raise SystemExit('error: parent inode is not a UFS directory')
    if check_existing and lookup_ufs_directory_entry(image, filesystem, parent_inode, entry_name) is not None:
        label = target_path or entry_name
        raise SystemExit(f'error: target path {label} already exists inside the ufs filesystem')
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
    maybe_recompute_ufs_summary_counts(image, filesystem, recompute_summary=recompute_summary)
    return {'operation': 'create', 'path': target_path or entry_name, 'inode': new_inode_number, 'size': len(file_bytes)}


def create_ufs_special_file(
    image: bytearray,
    filesystem: FilesystemCandidate,
    target_path: str,
    *,
    file_type: int,
    major: int,
    minor: int,
    mode: int = 0o600,
    uid: int = 0,
    gid: int = 0,
    timestamp: int = 0,
    parent_inode_number: int | None = None,
    recompute_summary: bool = True,
) -> dict[str, int | str]:
    if file_type not in {UFS_IFBLK, UFS_IFCHR}:
        raise SystemExit(f'error: unsupported UFS special file type {file_type:o}')
    if major < 0 or minor < 0:
        raise SystemExit('error: UFS special-device major and minor numbers must be non-negative')
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_creation_parent(
        image,
        filesystem,
        target_path,
        parent_inode_number=parent_inode_number,
    )
    new_inode_number = allocate_ufs_inode(image, filesystem, preferred_inode=parent_inode_number)
    permissions = mode & ~UFS_IFMT
    expanded_device = (major << 18) | minor
    old_device = ((major & 0x7F) << 8) | (minor & 0xFF)
    initialize_ufs_inode(
        image,
        filesystem,
        new_inode_number,
        file_type | permissions,
        uid=uid,
        gid=gid,
        nlink=1,
        timestamp=timestamp,
    )
    try:
        write_ufs_inode_size(image, filesystem, new_inode_number, 0)
        write_ufs_inode_blocks(image, filesystem, new_inode_number, 0)
        write_ufs_block_lists(image, filesystem, new_inode_number, [old_device, expanded_device], [0, 0, 0])
        add_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name, new_inode_number)
    except Exception:
        clear_ufs_inode(image, filesystem, new_inode_number)
        free_ufs_inode(image, filesystem, new_inode_number)
        raise
    maybe_recompute_ufs_summary_counts(image, filesystem, recompute_summary=recompute_summary)
    return {'operation': 'mknod', 'path': target_path, 'inode': new_inode_number, 'major': major, 'minor': minor}


def make_ufs_directory(
    image: bytearray,
    filesystem: FilesystemCandidate,
    target_path: str,
    mode: int = 0o755,
    uid: int = 0,
    gid: int = 0,
    timestamp: int = 0,
    *,
    parent_inode_number: int | None = None,
    recompute_summary: bool = True,
) -> dict[str, int | str]:
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_creation_parent(
        image,
        filesystem,
        target_path,
        parent_inode_number=parent_inode_number,
    )
    return make_ufs_directory_in_parent(
        image,
        filesystem,
        parent_inode_number,
        parent_inode,
        entry_name,
        target_path=target_path,
        mode=mode,
        uid=uid,
        gid=gid,
        timestamp=timestamp,
        recompute_summary=recompute_summary,
    )


def make_ufs_directory_in_parent(
    image: bytearray,
    filesystem: FilesystemCandidate,
    parent_inode_number: int,
    parent_inode: dict[str, int | list[int]],
    entry_name: str,
    *,
    target_path: str | None = None,
    mode: int = 0o755,
    uid: int = 0,
    gid: int = 0,
    timestamp: int = 0,
    recompute_summary: bool = True,
    check_existing: bool = True,
) -> dict[str, int | str]:
    if not ufs_is_directory(parent_inode):
        raise SystemExit('error: parent inode is not a UFS directory')
    if check_existing and lookup_ufs_directory_entry(image, filesystem, parent_inode, entry_name) is not None:
        label = target_path or entry_name
        raise SystemExit(f'error: target path {label} already exists inside the ufs filesystem')
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
    maybe_recompute_ufs_summary_counts(image, filesystem, recompute_summary=recompute_summary)
    return {'operation': 'mkdir', 'path': target_path or entry_name, 'inode': new_inode_number}


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


def ufs_directory_inode_is_empty(
    image: ImageBuffer,
    filesystem: FilesystemCandidate,
    inode: dict[str, int | list[int]],
) -> bool:
    for record in iter_ufs_inode_directory_records(image, filesystem, inode):
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
    if not ufs_directory_inode_is_empty(image, filesystem, target_inode):
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
    if not ufs_directory_inode_is_empty(image, filesystem, target_inode):
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
    _, entry_name, parent_inode_number, parent_inode = resolve_ufs_creation_parent(image, filesystem, target_path)
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
    *,
    parent_inode_number: int | None = None,
    recompute_summary: bool = True,
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
        parent_inode_number=parent_inode_number,
        recompute_summary=recompute_summary,
    )


def rename_ufs_in_parent(
    image: bytearray,
    filesystem: FilesystemCandidate,
    source_parent_inode_number: int,
    source_parent_inode: dict[str, int | list[int]],
    source_name: str,
    source_inode_number: int,
    source_inode: dict[str, int | list[int]],
    target_parent_inode_number: int,
    target_parent_inode: dict[str, int | list[int]],
    target_name: str,
    *,
    check_existing: bool = True,
) -> dict[str, int | str]:
    if source_parent_inode_number == target_parent_inode_number and source_name == target_name:
        return {'operation': 'rename', 'source_path': source_name, 'target_path': target_name, 'inode': source_inode_number}

    if check_existing:
        existing_target = lookup_ufs_directory_entry(image, filesystem, target_parent_inode, target_name)
        if existing_target is not None:
            raise SystemExit('error: target already exists')

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
    return {'operation': 'rename', 'source_path': source_name, 'target_path': target_name, 'inode': source_inode_number}


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
