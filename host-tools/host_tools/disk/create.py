from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .structures import HDPDLOC, SECTOR_SIZE, UNIXWARE_PARTITION_TYPE, VALID_PD, VTOC_SANE, PartitionEntry, VtocPartition


@dataclass(frozen=True)
class RawDiskGeometry:
    cylinders: int
    heads: int
    sectors_per_track: int

    @property
    def total_sectors(self) -> int:
        return self.cylinders * self.heads * self.sectors_per_track


def validate_geometry(geometry: RawDiskGeometry) -> None:
    if geometry.cylinders <= 0 or geometry.heads <= 0 or geometry.sectors_per_track <= 0:
        raise SystemExit('error: disk geometry values must all be positive')


def validate_unix_partition(total_sectors: int, unix_partition_start: int, unix_partition_size: int) -> None:
    if unix_partition_start < 1:
        raise SystemExit('error: UNIX partition must start at or after sector 1')
    if unix_partition_size <= 0:
        raise SystemExit('error: UNIX partition size must be positive')
    if unix_partition_start + unix_partition_size > total_sectors:
        raise SystemExit('error: UNIX partition exceeds the declared disk geometry')


def validate_vtoc_partitions(
    unix_partition_start: int,
    unix_partition_size: int,
    partitions: list[VtocPartition],
) -> None:
    seen_indexes: set[int] = set()
    unix_partition_end = unix_partition_start + unix_partition_size
    for partition in partitions:
        if partition.index < 0 or partition.index >= 16:
            raise SystemExit(f'error: slice index {partition.index} is outside the supported VTOC range 0..15')
        if partition.index in seen_indexes:
            raise SystemExit(f'error: duplicate slice index {partition.index}')
        seen_indexes.add(partition.index)
        if partition.start_sector < 0:
            raise SystemExit(f'error: slice {partition.index} has a negative start sector')
        if partition.sector_count < 0:
            raise SystemExit(f'error: slice {partition.index} has a negative size')
        if partition.start_sector < unix_partition_start:
            raise SystemExit(f'error: slice {partition.index} starts before the UNIX partition')
        if partition.start_sector + partition.sector_count > unix_partition_end:
            raise SystemExit(f'error: slice {partition.index} exceeds the UNIX partition bounds')


def encode_chs(lba: int, geometry: RawDiskGeometry) -> bytes:
    if lba <= 0:
        return bytes([0, 0, 0])
    sectors_per_cylinder = geometry.heads * geometry.sectors_per_track
    cylinder = min(lba // sectors_per_cylinder, 1023)
    temp = lba % sectors_per_cylinder
    head = min(temp // geometry.sectors_per_track, 254)
    sector = (temp % geometry.sectors_per_track) + 1
    sector_byte = (sector & 0x3F) | ((cylinder >> 2) & 0xC0)
    return bytes([head & 0xFF, sector_byte & 0xFF, cylinder & 0xFF])


def serialize_partition_entry(partition: PartitionEntry, geometry: RawDiskGeometry) -> bytes:
    boot_indicator = 0x80 if partition.bootable else 0x00
    return b''.join(
        [
            bytes([boot_indicator]),
            encode_chs(partition.start_lba, geometry),
            bytes([partition.partition_type]),
            encode_chs(partition.start_lba + max(partition.sector_count - 1, 0), geometry),
            partition.start_lba.to_bytes(4, 'little', signed=False),
            partition.sector_count.to_bytes(4, 'little', signed=False),
        ]
    )


def build_mbr(geometry: RawDiskGeometry, unix_partition_start: int, unix_partition_size: int) -> bytes:
    sector = bytearray(SECTOR_SIZE)
    sector[446:462] = serialize_partition_entry(
        PartitionEntry(
            index=1,
            bootable=True,
            partition_type=UNIXWARE_PARTITION_TYPE,
            start_lba=unix_partition_start,
            sector_count=unix_partition_size,
            start_chs=(0, 0, 0),
            end_chs=(0, 0, 0),
        ),
        geometry,
    )
    sector[510:512] = (0xAA55).to_bytes(2, 'little', signed=False)
    return bytes(sector)


def build_pdinfo(geometry: RawDiskGeometry, logical_sector_0: int, vtoc_ptr: int, vtoc_len: int, alt_ptr: int, alt_len: int) -> bytes:
    sector = bytearray(SECTOR_SIZE)
    sector[0:4] = (0).to_bytes(4, 'little', signed=False)
    sector[4:8] = VALID_PD.to_bytes(4, 'little', signed=False)
    sector[8:12] = (1).to_bytes(4, 'little', signed=False)
    sector[24:28] = geometry.cylinders.to_bytes(4, 'little', signed=False)
    sector[28:32] = geometry.heads.to_bytes(4, 'little', signed=False)
    sector[32:36] = geometry.sectors_per_track.to_bytes(4, 'little', signed=False)
    sector[36:40] = SECTOR_SIZE.to_bytes(4, 'little', signed=False)
    sector[40:44] = logical_sector_0.to_bytes(4, 'little', signed=False)
    sector[84:88] = vtoc_ptr.to_bytes(4, 'little', signed=False)
    sector[88:90] = vtoc_len.to_bytes(2, 'little', signed=False)
    sector[92:96] = alt_ptr.to_bytes(4, 'little', signed=False)
    sector[96:98] = alt_len.to_bytes(2, 'little', signed=False)
    return bytes(sector)


def build_vtoc(volume: str, partitions: list[VtocPartition]) -> bytes:
    block = bytearray(SECTOR_SIZE)
    block[0:4] = VTOC_SANE.to_bytes(4, 'little', signed=False)
    block[4:8] = (1).to_bytes(4, 'little', signed=False)
    block[8:16] = volume.encode('ascii', errors='replace')[:8].ljust(8, b'\0')
    block[16:18] = len(partitions).to_bytes(2, 'little', signed=False)
    for partition in partitions:
        entry_offset = 60 + (partition.index * 12)
        block[entry_offset:entry_offset + 2] = partition.tag.to_bytes(2, 'little', signed=False)
        block[entry_offset + 2:entry_offset + 4] = partition.flag.to_bytes(2, 'little', signed=False)
        block[entry_offset + 4:entry_offset + 8] = partition.start_sector.to_bytes(4, 'little', signed=True)
        block[entry_offset + 8:entry_offset + 12] = partition.sector_count.to_bytes(4, 'little', signed=True)
    return bytes(block)


def create_raw_image_skeleton(
    output_path: Path,
    geometry: RawDiskGeometry,
    unix_partition_start: int,
    unix_partition_size: int,
    volume: str,
    slices: list[VtocPartition],
) -> None:
    validate_geometry(geometry)
    validate_unix_partition(geometry.total_sectors, unix_partition_start, unix_partition_size)
    validate_vtoc_partitions(unix_partition_start, unix_partition_size, slices)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = bytearray(geometry.total_sectors * SECTOR_SIZE)
    image[0:SECTOR_SIZE] = build_mbr(geometry, unix_partition_start, unix_partition_size)

    vtoc_ptr = (HDPDLOC * SECTOR_SIZE) + 100
    vtoc_len = 316
    alt_ptr = 30 * SECTOR_SIZE
    alt_len = 0

    pdinfo_sector = unix_partition_start + HDPDLOC
    image[pdinfo_sector * SECTOR_SIZE:(pdinfo_sector + 1) * SECTOR_SIZE] = build_pdinfo(
        geometry,
        logical_sector_0=unix_partition_start,
        vtoc_ptr=vtoc_ptr,
        vtoc_len=vtoc_len,
        alt_ptr=alt_ptr,
        alt_len=alt_len,
    )
    vtoc_sector = unix_partition_start + (vtoc_ptr // SECTOR_SIZE)
    vtoc_offset = vtoc_ptr % SECTOR_SIZE
    vtoc_block = build_vtoc(volume, slices)
    image_offset = (vtoc_sector * SECTOR_SIZE) + vtoc_offset
    if image_offset + len(vtoc_block) > len(image):
        raise SystemExit('error: VTOC metadata does not fit inside the declared disk geometry')
    image[image_offset:image_offset + len(vtoc_block)] = vtoc_block
    output_path.write_bytes(image)