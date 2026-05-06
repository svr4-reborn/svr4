from __future__ import annotations

from dataclasses import dataclass, field


SECTOR_SIZE = 512
BFS_MAGIC = 0x1BADFACE
UFS_MAGIC = 0x00011954

BFS_ROOT_INODE = 2
BFS_SUPER_SIZE = 512
BFS_DIRENT_SIZE = 56
BFS_LDIR_SIZE = 16

UFS_ROOT_INODE = 2
UFS_SB_OFFSET = 8192
UFS_SB_SIZE = 8192
UFS_DIRBLKSIZ = 512
UFS_DINODE_SIZE = 128
UFS_NDADDR = 12
UFS_FS_MAGIC_OFFSET = 1372
UFS_FS_BSIZE_OFFSET = 48
UFS_FS_FSIZE_OFFSET = 52
UFS_FS_FRAG_OFFSET = 56
UFS_FS_FSBTODB_OFFSET = 100
UFS_FS_INOPB_OFFSET = 120
UFS_FS_CGOFFSET_OFFSET = 24
UFS_FS_CGMASK_OFFSET = 28
UFS_FS_IBLKNO_OFFSET = 16
UFS_FS_IPG_OFFSET = 184
UFS_FS_FPG_OFFSET = 188
UFS_DI_MODE_OFFSET = 112
UFS_DI_SIZE_OFFSET = 8
UFS_DI_DB_OFFSET = 40
UFS_DI_IB_OFFSET = 88


def i32(buffer: bytes, offset: int) -> int:
    return int.from_bytes(buffer[offset:offset + 4], 'little', signed=True)


def u16(buffer: bytes, offset: int) -> int:
    return int.from_bytes(buffer[offset:offset + 2], 'little', signed=False)


def u32(buffer: bytes, offset: int) -> int:
    return int.from_bytes(buffer[offset:offset + 4], 'little', signed=False)


@dataclass(frozen=True)
class FilesystemCandidate:
    kind: str
    start_offset: int
    super_offset: int
    block_size: int | None = None
    details: dict[str, int | str] = field(default_factory=dict)
    root_entries: list[dict[str, int | str]] = field(default_factory=list)