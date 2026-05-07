from __future__ import annotations

from dataclasses import dataclass, field


SECTOR_SIZE = 512
UNIXWARE_PARTITION_TYPE = 0x63
HDPDLOC = 29
VALID_PD = 0xCA5E600D
VTOC_SANE = 0x600DDEEE


@dataclass(frozen=True)
class PartitionEntry:
    index: int
    bootable: bool
    partition_type: int
    start_lba: int
    sector_count: int
    start_chs: tuple[int, int, int]
    end_chs: tuple[int, int, int]


@dataclass(frozen=True)
class MbrInfo:
    signature: int
    partitions: list[PartitionEntry]


@dataclass(frozen=True)
class PdInfo:
    drive_id: int
    sanity: int
    version: int
    serial: str
    cylinders: int
    tracks: int
    sectors: int
    bytes_per_sector: int
    logical_sector_0: int
    vtoc_ptr: int
    vtoc_len: int
    alt_ptr: int
    alt_len: int


@dataclass(frozen=True)
class AltTableInfo:
    used: int
    reserved: int
    base_sector: int
    bad_entries: list[int]


@dataclass(frozen=True)
class AltInfo:
    sanity: int
    version: int
    track_table: AltTableInfo
    sector_table: AltTableInfo


@dataclass(frozen=True)
class VtocPartition:
    index: int
    tag: int
    flag: int
    start_sector: int
    sector_count: int


@dataclass(frozen=True)
class VtocInfo:
    sanity: int
    version: int
    volume: str
    partition_count: int
    partitions: list[VtocPartition]


@dataclass(frozen=True)
class SliceFilesystem:
    slice_index: int
    tag: int
    start_sector: int
    absolute_start_sector: int
    sector_count: int
    filesystem: str | None = None
    filesystem_offset: int = 0
    root_entries: list[dict[str, int | str]] = field(default_factory=list)


@dataclass(frozen=True)
class DiskImageReport:
    path: str
    file_size: int
    mbr: MbrInfo
    active_unix_partition: PartitionEntry | None = None
    pdinfo: PdInfo | None = None
    vtoc: VtocInfo | None = None
    slice_filesystems: list[SliceFilesystem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)