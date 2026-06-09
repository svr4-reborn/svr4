from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .structures import HDPDLOC, SECTOR_SIZE, UNIXWARE_PARTITION_TYPE, VALID_PD, VTOC_SANE, PartitionEntry, VtocPartition


ALT_SANITY = 0xDEADBEEF
ALT_VERSION = 0x02
MAX_ALTENTS = 253


MAX_CHS_CYLINDERS = 1024
MAX_KERNEL_CHS_HEADS = 16
MAX_CHS_SECTORS_PER_TRACK = 63
DISK_ADDRESSING_CHS = 'chs'
DISK_ADDRESSING_LBA28 = 'lba28'
ACTIVE_PARTITION_CHAINLOADER_MBR = bytes.fromhex(
    '31c0fa8ed0bc007c8ec08ed8fb89e6bf0006b90002fcf3a4ea1d060000b004bebe07803c80740c83c610fec875f4beac06eb3289f78b148b4c02bd0500bb007cb80102cd13730c31c0cd134d75efbe9406eb12813efe7d55aa750789feea007c0000be7306ac08c07406b40ecd10ebf5fbebfe496e76616c696420706172746974696f6e20626f6f74207369676e6174757265004572726f722072656164696e6720626f6f747374726170004e6f2061637469766520706172746974696f6e206f6e2068617264206469736b00'
)


@dataclass(frozen=True)
class RawDiskGeometry:
    cylinders: int
    heads: int
    sectors_per_track: int

    @property
    def total_sectors(self) -> int:
        return self.cylinders * self.heads * self.sectors_per_track


def validate_geometry(geometry: RawDiskGeometry, disk_addressing: str = DISK_ADDRESSING_CHS) -> None:
    if geometry.cylinders <= 0 or geometry.heads <= 0 or geometry.sectors_per_track <= 0:
        raise SystemExit('error: disk geometry values must all be positive')
    if disk_addressing not in {DISK_ADDRESSING_CHS, DISK_ADDRESSING_LBA28}:
        raise SystemExit(f'error: unsupported disk addressing mode {disk_addressing!r}')
    if disk_addressing == DISK_ADDRESSING_CHS and geometry.cylinders > MAX_CHS_CYLINDERS:
        raise SystemExit(f'error: disk geometry exceeds CHS cylinder limit ({geometry.cylinders} > {MAX_CHS_CYLINDERS})')
    if geometry.heads > MAX_KERNEL_CHS_HEADS:
        raise SystemExit(f'error: disk geometry exceeds kernel head limit ({geometry.heads} > {MAX_KERNEL_CHS_HEADS})')
    if geometry.sectors_per_track > MAX_CHS_SECTORS_PER_TRACK:
        raise SystemExit(
            f'error: disk geometry exceeds CHS sector-per-track limit '
            f'({geometry.sectors_per_track} > {MAX_CHS_SECTORS_PER_TRACK})'
        )


def max_chs_lba(geometry: RawDiskGeometry) -> int:
    return geometry.total_sectors - 1


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


def encode_chs(lba: int, geometry: RawDiskGeometry, *, saturate: bool = False) -> bytes:
    if lba <= 0:
        return bytes([0, 0, 0])
    if lba > max_chs_lba(geometry):
        if not saturate:
            raise SystemExit(f'error: LBA {lba} is outside the CHS-addressable disk geometry')
        lba = max_chs_lba(geometry)
    if saturate:
        lba = min(lba, (MAX_CHS_CYLINDERS * geometry.heads * geometry.sectors_per_track) - 1)
    sectors_per_cylinder = geometry.heads * geometry.sectors_per_track
    cylinder = lba // sectors_per_cylinder
    temp = lba % sectors_per_cylinder
    head = temp // geometry.sectors_per_track
    sector = (temp % geometry.sectors_per_track) + 1
    sector_byte = (sector & 0x3F) | ((cylinder >> 2) & 0xC0)
    return bytes([head & 0xFF, sector_byte & 0xFF, cylinder & 0xFF])


def serialize_partition_entry(partition: PartitionEntry, geometry: RawDiskGeometry, *, saturate_chs: bool = False) -> bytes:
    boot_indicator = 0x80 if partition.bootable else 0x00
    return b''.join(
        [
            bytes([boot_indicator]),
            encode_chs(partition.start_lba, geometry, saturate=saturate_chs),
            bytes([partition.partition_type]),
            encode_chs(partition.start_lba + max(partition.sector_count - 1, 0), geometry, saturate=saturate_chs),
            partition.start_lba.to_bytes(4, 'little', signed=False),
            partition.sector_count.to_bytes(4, 'little', signed=False),
        ]
    )


def build_mbr(
    geometry: RawDiskGeometry,
    unix_partition_start: int,
    unix_partition_size: int,
    *,
    boot_code: bytes | None = None,
    disk_addressing: str = DISK_ADDRESSING_CHS,
) -> bytes:
    sector = bytearray(SECTOR_SIZE)
    if boot_code is not None:
        if len(boot_code) > 446:
            raise SystemExit(f'error: MBR boot code is too large ({len(boot_code)} > 446 bytes)')
        sector[:len(boot_code)] = boot_code
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
        saturate_chs=(disk_addressing == DISK_ADDRESSING_LBA28),
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
    partition_count = (max((partition.index for partition in partitions), default=-1) + 1)
    block[16:18] = partition_count.to_bytes(2, 'little', signed=False)
    for partition in partitions:
        entry_offset = 60 + (partition.index * 12)
        block[entry_offset:entry_offset + 2] = partition.tag.to_bytes(2, 'little', signed=False)
        block[entry_offset + 2:entry_offset + 4] = partition.flag.to_bytes(2, 'little', signed=False)
        block[entry_offset + 4:entry_offset + 8] = partition.start_sector.to_bytes(4, 'little', signed=True)
        block[entry_offset + 8:entry_offset + 12] = partition.sector_count.to_bytes(4, 'little', signed=True)
    return bytes(block)


def build_empty_alt_info() -> bytes:
    block = bytearray(2048)
    block[0:4] = ALT_SANITY.to_bytes(4, 'little', signed=False)
    block[4:6] = ALT_VERSION.to_bytes(2, 'little', signed=False)
    block[6:8] = (0).to_bytes(2, 'little', signed=False)

    track_table_offset = 8
    sector_table_offset = track_table_offset + 8 + (MAX_ALTENTS * 4)

    block[track_table_offset:track_table_offset + 2] = (0).to_bytes(2, 'little', signed=False)
    block[track_table_offset + 2:track_table_offset + 4] = (0).to_bytes(2, 'little', signed=False)
    block[track_table_offset + 4:track_table_offset + 8] = (0).to_bytes(4, 'little', signed=True)

    block[sector_table_offset:sector_table_offset + 2] = (0).to_bytes(2, 'little', signed=False)
    block[sector_table_offset + 2:sector_table_offset + 4] = (0).to_bytes(2, 'little', signed=False)
    block[sector_table_offset + 4:sector_table_offset + 8] = (0).to_bytes(4, 'little', signed=True)
    return bytes(block)


def create_raw_image_skeleton(
    output_path: Path,
    geometry: RawDiskGeometry,
    unix_partition_start: int,
    unix_partition_size: int,
    volume: str,
    slices: list[VtocPartition],
    mbr_boot_code: bytes | None = None,
    disk_addressing: str = DISK_ADDRESSING_CHS,
) -> None:
    validate_geometry(geometry, disk_addressing=disk_addressing)
    validate_unix_partition(geometry.total_sectors, unix_partition_start, unix_partition_size)
    validate_vtoc_partitions(unix_partition_start, unix_partition_size, slices)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b'')
    with output_path.open('r+b') as handle:
        handle.truncate(geometry.total_sectors * SECTOR_SIZE)
        handle.seek(0)
        handle.write(
            build_mbr(
                geometry,
                unix_partition_start,
                unix_partition_size,
                boot_code=mbr_boot_code,
                disk_addressing=disk_addressing,
            )
        )

        vtoc_ptr = (HDPDLOC * SECTOR_SIZE) + 100
        vtoc_len = 316
        alt_ptr = 30 * SECTOR_SIZE
        alt_info = build_empty_alt_info()
        alt_len = len(alt_info)

        pdinfo_sector = unix_partition_start + HDPDLOC
        handle.seek(pdinfo_sector * SECTOR_SIZE)
        handle.write(
            build_pdinfo(
                geometry,
                logical_sector_0=unix_partition_start,
                vtoc_ptr=vtoc_ptr,
                vtoc_len=vtoc_len,
                alt_ptr=alt_ptr,
                alt_len=alt_len,
            )
        )
        vtoc_sector = unix_partition_start + (vtoc_ptr // SECTOR_SIZE)
        vtoc_offset = vtoc_ptr % SECTOR_SIZE
        vtoc_block = build_vtoc(volume, slices)
        image_offset = (vtoc_sector * SECTOR_SIZE) + vtoc_offset
        if image_offset + len(vtoc_block) > geometry.total_sectors * SECTOR_SIZE:
            raise SystemExit('error: VTOC metadata does not fit inside the declared disk geometry')
        handle.seek(image_offset)
        handle.write(vtoc_block)

        alt_sector = unix_partition_start + (alt_ptr // SECTOR_SIZE)
        alt_offset = alt_ptr % SECTOR_SIZE
        alt_image_offset = (alt_sector * SECTOR_SIZE) + alt_offset
        if alt_image_offset + len(alt_info) > geometry.total_sectors * SECTOR_SIZE:
            raise SystemExit('error: alternates metadata does not fit inside the declared disk geometry')
        handle.seek(alt_image_offset)
        handle.write(alt_info)
