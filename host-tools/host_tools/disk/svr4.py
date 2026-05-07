from __future__ import annotations

from .structures import AltInfo, AltTableInfo, HDPDLOC, PdInfo, VTOC_SANE, VALID_PD, VtocInfo, VtocPartition


VTOC_PARTITION_COUNT = 16
PARTITION_STRUCT_OFFSET = 60
PARTITION_STRUCT_SIZE = 12
ALT_SANITY = 0xDEADBEEF
ALT_VERSION = 0x02
V_BACKUP = 0x05
V_OTHER = 0x07

PARTITION_TAG_NAMES = {
    0x01: 'boot',
    0x02: 'root',
    0x03: 'swap',
    0x04: 'usr',
    0x05: 'backup',
    0x06: 'alts',
    0x07: 'other',
    0x08: 'alttrk',
    0x09: 'stand',
    0x0A: 'var',
    0x0B: 'home',
    0x0C: 'dump',
}


def partition_tag_name(tag: int) -> str:
    return PARTITION_TAG_NAMES.get(tag, f'unknown(0x{tag:02x})')


def parse_pdinfo(raw: bytes) -> PdInfo:
    if len(raw) < 98:
        raise ValueError('pdinfo sector is too small')
    return PdInfo(
        drive_id=int.from_bytes(raw[0:4], 'little', signed=False),
        sanity=int.from_bytes(raw[4:8], 'little', signed=False),
        version=int.from_bytes(raw[8:12], 'little', signed=False),
        serial=raw[12:24].split(b'\0', 1)[0].decode('ascii', errors='replace'),
        cylinders=int.from_bytes(raw[24:28], 'little', signed=False),
        tracks=int.from_bytes(raw[28:32], 'little', signed=False),
        sectors=int.from_bytes(raw[32:36], 'little', signed=False),
        bytes_per_sector=int.from_bytes(raw[36:40], 'little', signed=False),
        logical_sector_0=int.from_bytes(raw[40:44], 'little', signed=False),
        vtoc_ptr=int.from_bytes(raw[84:88], 'little', signed=False),
        vtoc_len=int.from_bytes(raw[88:90], 'little', signed=False),
        alt_ptr=int.from_bytes(raw[92:96], 'little', signed=False),
        alt_len=int.from_bytes(raw[96:98], 'little', signed=False),
    )


def parse_vtoc(raw: bytes, offset: int = 0) -> VtocInfo:
    view = raw[offset:]
    if len(view) < PARTITION_STRUCT_OFFSET + (VTOC_PARTITION_COUNT * PARTITION_STRUCT_SIZE):
        raise ValueError('vtoc block is too small')
    partitions: list[VtocPartition] = []
    for index in range(VTOC_PARTITION_COUNT):
        entry_offset = PARTITION_STRUCT_OFFSET + (index * PARTITION_STRUCT_SIZE)
        entry = view[entry_offset:entry_offset + PARTITION_STRUCT_SIZE]
        partitions.append(
            VtocPartition(
                index=index,
                tag=int.from_bytes(entry[0:2], 'little', signed=False),
                flag=int.from_bytes(entry[2:4], 'little', signed=False),
                start_sector=int.from_bytes(entry[4:8], 'little', signed=True),
                sector_count=int.from_bytes(entry[8:12], 'little', signed=True),
            )
        )
    return VtocInfo(
        sanity=int.from_bytes(view[0:4], 'little', signed=False),
        version=int.from_bytes(view[4:8], 'little', signed=False),
        volume=view[8:16].split(b'\0', 1)[0].decode('ascii', errors='replace'),
        partition_count=int.from_bytes(view[16:18], 'little', signed=False),
        partitions=partitions,
    )


def _parse_alt_table(raw: bytes, offset: int, entry_count: int) -> tuple[AltTableInfo, int]:
    end_offset = offset + 8 + (entry_count * 4)
    if len(raw) < end_offset:
        raise ValueError('alternates table is truncated')
    table = AltTableInfo(
        used=int.from_bytes(raw[offset:offset + 2], 'little', signed=False),
        reserved=entry_count,
        base_sector=int.from_bytes(raw[offset + 4:offset + 8], 'little', signed=True),
        bad_entries=[
            int.from_bytes(raw[entry_offset:entry_offset + 4], 'little', signed=True)
            for entry_offset in range(offset + 8, end_offset, 4)
        ],
    )
    return table, end_offset


def parse_alt_info(raw: bytes, offset: int = 0) -> AltInfo:
    view = raw[offset:]
    if len(view) < 16:
        raise ValueError('alternates table is too small')
    sanity = int.from_bytes(view[0:4], 'little', signed=False)
    version = int.from_bytes(view[4:6], 'little', signed=False)
    track_reserved = int.from_bytes(view[10:12], 'little', signed=False)
    track_table, next_offset = _parse_alt_table(view, 8, track_reserved)
    if len(view) < next_offset + 4:
        raise ValueError('alternates table is missing sector metadata')
    sector_reserved = int.from_bytes(view[next_offset + 2:next_offset + 4], 'little', signed=False)
    sector_table, _ = _parse_alt_table(view, next_offset, sector_reserved)
    return AltInfo(
        sanity=sanity,
        version=version,
        track_table=track_table,
        sector_table=sector_table,
    )


def remap_guest_visible_sector(pdinfo: PdInfo, partition: VtocPartition, alt_info: AltInfo | None, absolute_sector: int) -> int:
    if alt_info is None:
        return absolute_sector
    if partition.index == 0 or partition.tag in {V_BACKUP, V_OTHER}:
        return absolute_sector
    if pdinfo.sectors <= 0:
        raise ValueError('pdinfo.sectors must be positive')

    remapped_sector = absolute_sector
    track_number = remapped_sector // pdinfo.sectors
    for index, bad_track in enumerate(alt_info.track_table.bad_entries[:alt_info.track_table.used]):
        if track_number == bad_track:
            remapped_sector = alt_info.track_table.base_sector + (index * pdinfo.sectors) + (remapped_sector % pdinfo.sectors)
            break

    for index, bad_sector in enumerate(alt_info.sector_table.bad_entries[:alt_info.sector_table.used]):
        if remapped_sector == bad_sector:
            remapped_sector = alt_info.sector_table.base_sector + index
            break

    return remapped_sector


def is_valid_pdinfo(pdinfo: PdInfo) -> bool:
    return pdinfo.sanity == VALID_PD


def is_valid_vtoc(vtoc: VtocInfo) -> bool:
    return vtoc.sanity == VTOC_SANE


def is_valid_alt_info(alt_info: AltInfo) -> bool:
    return alt_info.sanity == ALT_SANITY and alt_info.version == ALT_VERSION