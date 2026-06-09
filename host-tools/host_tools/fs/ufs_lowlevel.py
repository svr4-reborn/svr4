from __future__ import annotations

from typing import Any

from .common import FilesystemCandidate, SECTOR_SIZE, UFS_DI_DB_OFFSET, UFS_DI_IB_OFFSET, UFS_DI_MODE_OFFSET, UFS_DI_SIZE_OFFSET, UFS_DINODE_SIZE, UFS_FS_BSIZE_OFFSET, UFS_FS_CGMASK_OFFSET, UFS_FS_CGOFFSET_OFFSET, UFS_FS_FPG_OFFSET, UFS_FS_FRAG_OFFSET, UFS_FS_FSBTODB_OFFSET, UFS_FS_IBLKNO_OFFSET, UFS_FS_INOPB_OFFSET, UFS_FS_IPG_OFFSET, UFS_FS_FSIZE_OFFSET, UFS_FS_MAGIC_OFFSET, UFS_MAGIC, UFS_NDADDR, UFS_SB_OFFSET, UFS_SB_SIZE, i32, u16, u32


NBBY = 8
MAXFRAG = 8
MAXCPG = 32
MAXIPG = 2048
NRPOS = 8
UFS_FS_CBLKNO_OFFSET = 12
UFS_FS_DBLKNO_OFFSET = 20
UFS_FS_DSIZE_OFFSET = 40
UFS_FS_NCG_OFFSET = 44
UFS_FS_MINFREE_OFFSET = 60
UFS_FS_NINDIR_OFFSET = 116
UFS_FS_NSPF_OFFSET = 124
UFS_FS_CSADDR_OFFSET = 152
UFS_FS_CSSIZE_OFFSET = 156
UFS_FS_NSECT_OFFSET = 168
UFS_FS_SPC_OFFSET = 172
UFS_FS_NCYL_OFFSET = 176
UFS_FS_CPG_OFFSET = 180
UFS_FS_CSTOTAL_NDIR_OFFSET = 192
UFS_FS_CSTOTAL_NBFREE_OFFSET = 196
UFS_FS_CSTOTAL_NIFREE_OFFSET = 200
UFS_CG_TIME_OFFSET = 8
UFS_CG_CGX_OFFSET = 12
UFS_CG_NCYL_OFFSET = 16
UFS_CG_NIBLK_OFFSET = 18
UFS_CG_NDBLK_OFFSET = 20
UFS_CG_CS_NDIR_OFFSET = 24
UFS_CG_CS_NBFREE_OFFSET = 28
UFS_CG_CS_NIFREE_OFFSET = 32
UFS_CG_CS_NFFREE_OFFSET = 36
UFS_CG_ROTOR_OFFSET = 40
UFS_CG_FROTOR_OFFSET = 44
UFS_CG_IROTOR_OFFSET = 48
UFS_CG_FRSUM_OFFSET = 52
UFS_CG_BTOT_OFFSET = UFS_CG_FRSUM_OFFSET + (MAXFRAG * 4)
UFS_CG_B_OFFSET = UFS_CG_BTOT_OFFSET + (MAXCPG * 4)
UFS_CG_MAGIC_OFFSET = 980
UFS_CG_IUSED_OFFSET = UFS_CG_MAGIC_OFFSET - (MAXIPG // NBBY)
UFS_CG_FREE_OFFSET = UFS_CG_MAGIC_OFFSET + 4
UFS_CG_MAGIC = 0x090255
UFS_EFT_MAGIC = 0x90909090
UFS_DI_NLINK_OFFSET = 2
UFS_DI_SUID_OFFSET = 4
UFS_DI_SGID_OFFSET = 6
UFS_DI_ATIME_OFFSET = 16
UFS_DI_MTIME_OFFSET = 24
UFS_DI_CTIME_OFFSET = 32
UFS_DI_FLAGS_OFFSET = 100
UFS_DI_BLOCKS_OFFSET = 104
UFS_DI_GEN_OFFSET = 108
UFS_DI_UID_OFFSET = 116
UFS_DI_GID_OFFSET = 120
UFS_DI_EFTFLAG_OFFSET = 124
UFS_IFMT = 0o170000
UFS_IFCHR = 0o020000
UFS_IFDIR = 0o040000
UFS_IFBLK = 0o060000
UFS_IFREG = 0o100000
UFS_IFLNK = 0o120000
ImageBuffer = bytes | bytearray
UFS_PRIMARY_SUPERBLOCK_OFFSETS = (UFS_SB_OFFSET,)


def detect_ufs(image: ImageBuffer) -> list[FilesystemCandidate]:
    candidates_by_key: dict[tuple[int, int], FilesystemCandidate] = {}
    max_image_offset = len(image) - (UFS_FS_MAGIC_OFFSET + 4)
    for superblock_offset in UFS_PRIMARY_SUPERBLOCK_OFFSETS:
        for fs_start in range(0, max(0, max_image_offset - superblock_offset) + 1, SECTOR_SIZE):
            super_offset = fs_start + superblock_offset
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
            details: dict[str, int | str] = {
                'bsize': block_size,
                'fsize': fragment_size,
                'frag': u32(image, super_offset + UFS_FS_FRAG_OFFSET),
                'dsize': u32(image, super_offset + UFS_FS_DSIZE_OFFSET),
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
                'nspf': u32(image, super_offset + UFS_FS_NSPF_OFFSET),
                'csaddr': u32(image, super_offset + UFS_FS_CSADDR_OFFSET),
                'cssize': u32(image, super_offset + UFS_FS_CSSIZE_OFFSET),
                'nsect': u32(image, super_offset + UFS_FS_NSECT_OFFSET),
                'spc': u32(image, super_offset + UFS_FS_SPC_OFFSET),
                'ncyl': u32(image, super_offset + UFS_FS_NCYL_OFFSET),
                'cpg': u32(image, super_offset + UFS_FS_CPG_OFFSET),
            }
            candidate = FilesystemCandidate(
                kind='ufs',
                start_offset=fs_start,
                super_offset=super_offset,
                block_size=block_size,
                details=details,
            )
            candidate_key = (super_offset, fs_start)
            current = candidates_by_key.get(candidate_key)
            if current is None or _ufs_candidate_rank(candidate) < _ufs_candidate_rank(current):
                candidates_by_key[candidate_key] = candidate
    return sorted(candidates_by_key.values(), key=_ufs_candidate_rank)


def detect_ufs_at_start(image: ImageBuffer, fs_start: int = 0) -> FilesystemCandidate | None:
    super_offset = fs_start + UFS_SB_OFFSET
    if super_offset + UFS_SB_SIZE > len(image):
        return None
    if u32(image, super_offset + UFS_FS_MAGIC_OFFSET) != UFS_MAGIC:
        return None
    block_size = u32(image, super_offset + UFS_FS_BSIZE_OFFSET)
    fragment_size = u32(image, super_offset + UFS_FS_FSIZE_OFFSET)
    inodes_per_block = u32(image, super_offset + UFS_FS_INOPB_OFFSET)
    inodes_per_group = u32(image, super_offset + UFS_FS_IPG_OFFSET)
    fragments_per_group = u32(image, super_offset + UFS_FS_FPG_OFFSET)
    if block_size < 4096 or block_size > UFS_SB_SIZE:
        return None
    if fragment_size < SECTOR_SIZE or fragment_size > block_size:
        return None
    if inodes_per_block == 0 or inodes_per_group == 0 or fragments_per_group == 0:
        return None
    details: dict[str, int | str] = {
        'bsize': block_size,
        'fsize': fragment_size,
        'frag': u32(image, super_offset + UFS_FS_FRAG_OFFSET),
        'dsize': u32(image, super_offset + UFS_FS_DSIZE_OFFSET),
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
        'nspf': u32(image, super_offset + UFS_FS_NSPF_OFFSET),
        'csaddr': u32(image, super_offset + UFS_FS_CSADDR_OFFSET),
        'cssize': u32(image, super_offset + UFS_FS_CSSIZE_OFFSET),
        'nsect': u32(image, super_offset + UFS_FS_NSECT_OFFSET),
        'spc': u32(image, super_offset + UFS_FS_SPC_OFFSET),
        'ncyl': u32(image, super_offset + UFS_FS_NCYL_OFFSET),
        'cpg': u32(image, super_offset + UFS_FS_CPG_OFFSET),
    }
    return FilesystemCandidate(
        kind='ufs',
        start_offset=fs_start,
        super_offset=super_offset,
        block_size=block_size,
        details=details,
    )


def _ufs_candidate_rank(candidate: FilesystemCandidate) -> tuple[int, int]:
    return (
        candidate.start_offset,
        candidate.super_offset,
    )


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


def ufs_inode_byte_offset(fs_start: int, fs: dict[str, Any], inode_number: int) -> int:
    inode_block = ufs_itod(fs, inode_number)
    return fs_start + ufs_fsbtobytes(fs, inode_block) + (ufs_itoo(fs, inode_number) * UFS_DINODE_SIZE)


def ufs_data_block_offset(fs_start: int, fs: dict[str, Any], fs_block: int) -> int:
    return fs_start + ufs_fsbtobytes(fs, fs_block)


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


def read_ufs_pointer_block(image: ImageBuffer, filesystem: FilesystemCandidate, fs_block: int) -> list[int]:
    block_offset = ufs_data_block_offset(filesystem.start_offset, filesystem.details, fs_block)
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
    remaining = size
    for fs_block in ufs_inode_data_blocks(image, filesystem, inode):
        block_offset = ufs_data_block_offset(fs_start, fs, fs_block)
        logical_size = min(block_size, remaining)
        data.extend(image[block_offset:block_offset + logical_size])
        remaining -= logical_size
        if len(data) >= size:
            break
    return bytes(data[:size])


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

    cg_bytes[UFS_CG_CGX_OFFSET:UFS_CG_CGX_OFFSET + 4] = cg.to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_NIBLK_OFFSET:UFS_CG_NIBLK_OFFSET + 2] = (
        (int(fs['ipg']) + int(fs['inopb']) - 1) // int(fs['inopb'])
    ).to_bytes(2, 'little', signed=False)
    cg_bytes[UFS_CG_NDBLK_OFFSET:UFS_CG_NDBLK_OFFSET + 4] = cg_ndblk.to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_CS_NDIR_OFFSET:UFS_CG_CS_NDIR_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_CS_NBFREE_OFFSET:UFS_CG_CS_NBFREE_OFFSET + 4] = free_blocks.to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_CS_NIFREE_OFFSET:UFS_CG_CS_NIFREE_OFFSET + 4] = int(fs['ipg']).to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_IROTOR_OFFSET:UFS_CG_IROTOR_OFFSET + 4] = (0).to_bytes(4, 'little', signed=False)
    cg_bytes[UFS_CG_MAGIC_OFFSET:UFS_CG_MAGIC_OFFSET + 4] = UFS_CG_MAGIC.to_bytes(4, 'little', signed=False)

    for frag_index in range(data_start_frag, cg_ndblk):
        set_frag_state(cg_bytes, frag_index, free=True)

    write_cg_block(image, filesystem, cg, cg_bytes)
    return cg_bytes


def read_allocatable_cg_block(image: bytearray, filesystem: FilesystemCandidate, cg: int) -> bytearray:
    cg_bytes = read_cg_block(image, filesystem, cg)
    if u32(cg_bytes, UFS_CG_MAGIC_OFFSET) == UFS_CG_MAGIC:
        return cg_bytes
    if _looks_like_pristine_ufs_cg(cg_bytes):
        return initialize_pristine_ufs_cg(image, filesystem, cg)
    return cg_bytes


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
        cg_bytes = read_allocatable_cg_block(image, filesystem, cg)
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
                block_offset = ufs_data_block_offset(filesystem.start_offset, fs, fs_block)
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
        cg_bytes = read_allocatable_cg_block(image, filesystem, cg)
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
            block_offset = ufs_data_block_offset(filesystem.start_offset, fs, fs_block)
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
    block_offset = ufs_data_block_offset(filesystem.start_offset, filesystem.details, fs_block)
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
