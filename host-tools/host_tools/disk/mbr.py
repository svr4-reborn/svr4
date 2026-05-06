from __future__ import annotations

from .structures import MbrInfo, PartitionEntry, SECTOR_SIZE


def decode_chs(raw: bytes) -> tuple[int, int, int]:
    head = raw[0]
    sector = raw[1] & 0x3F
    cylinder = ((raw[1] & 0xC0) << 2) | raw[2]
    return cylinder, head, sector


def parse_partition_entry(index: int, raw: bytes) -> PartitionEntry:
    if len(raw) != 16:
        raise ValueError(f'partition entry {index} must be 16 bytes')
    return PartitionEntry(
        index=index,
        bootable=(raw[0] == 0x80),
        start_chs=decode_chs(raw[1:4]),
        partition_type=raw[4],
        end_chs=decode_chs(raw[5:8]),
        start_lba=int.from_bytes(raw[8:12], 'little', signed=False),
        sector_count=int.from_bytes(raw[12:16], 'little', signed=False),
    )


def parse_mbr_sector(sector: bytes) -> MbrInfo:
    if len(sector) != SECTOR_SIZE:
        raise ValueError(f'MBR sector must be exactly {SECTOR_SIZE} bytes')
    partitions = [
        parse_partition_entry(index + 1, sector[446 + (index * 16):462 + (index * 16)])
        for index in range(4)
    ]
    signature = int.from_bytes(sector[510:512], 'little', signed=False)
    return MbrInfo(signature=signature, partitions=partitions)