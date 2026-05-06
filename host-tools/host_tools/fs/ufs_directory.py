from __future__ import annotations

from dataclasses import dataclass

from .common import u16, u32


UFS_DIRBLKSIZ = 512


@dataclass(frozen=True)
class UFSDirectoryEntry:
    inode: int
    record_length: int
    name_length: int
    name: str
    offset: int


@dataclass(frozen=True)
class UFSDirectoryInsertSlot:
    block_offset: int
    entry_offset: int
    record_length: int
    previous_entry_offset: int | None
    previous_entry_new_length: int | None


def ufs_dirsiz(name: str) -> int:
    name_length = len(name.encode('ascii'))
    return 8 + ((name_length + 1 + 3) & ~3)


def decode_ufs_directory_entry(directory_bytes: bytes, offset: int, max_length: int) -> UFSDirectoryEntry | None:
    if offset < 0 or offset + 8 > max_length:
        return None
    inode_number = u32(directory_bytes, offset)
    record_length = u16(directory_bytes, offset + 4)
    name_length = u16(directory_bytes, offset + 6)
    if record_length == 0 or offset + record_length > max_length:
        return None
    if name_length > 255 or offset + 8 + name_length > max_length:
        return None
    name = directory_bytes[offset + 8:offset + 8 + name_length].decode('ascii', errors='replace')
    return UFSDirectoryEntry(
        inode=inode_number,
        record_length=record_length,
        name_length=name_length,
        name=name,
        offset=offset,
    )


def encode_ufs_directory_entry(inode_number: int, name: str, record_length: int | None = None) -> bytes:
    encoded_name = name.encode('ascii')
    entry_length = ufs_dirsiz(name)
    actual_record_length = entry_length if record_length is None else record_length
    if actual_record_length < entry_length:
        raise ValueError('record length is too small for UFS directory entry payload')
    raw = bytearray(actual_record_length)
    raw[0:4] = inode_number.to_bytes(4, 'little', signed=False)
    raw[4:6] = actual_record_length.to_bytes(2, 'little', signed=False)
    raw[6:8] = len(encoded_name).to_bytes(2, 'little', signed=False)
    raw[8:8 + len(encoded_name)] = encoded_name
    return bytes(raw)


def iter_ufs_directory_records(directory_bytes: bytes, size: int) -> list[UFSDirectoryEntry]:
    records: list[UFSDirectoryEntry] = []
    offset = 0
    max_length = min(len(directory_bytes), size)
    while offset + 8 <= max_length:
        entry = decode_ufs_directory_entry(directory_bytes, offset, max_length)
        if entry is None:
            break
        records.append(entry)
        offset += entry.record_length
    return records


def find_ufs_directory_insert_slot(directory_bytes: bytes, size: int, name: str) -> UFSDirectoryInsertSlot | None:
    needed_length = ufs_dirsiz(name)
    max_length = min(len(directory_bytes), size)
    rounded_length = ((max_length + UFS_DIRBLKSIZ - 1) // UFS_DIRBLKSIZ) * UFS_DIRBLKSIZ
    if rounded_length == 0:
        rounded_length = UFS_DIRBLKSIZ
    for block_offset in range(0, rounded_length, UFS_DIRBLKSIZ):
        block_limit = min(block_offset + UFS_DIRBLKSIZ, max_length)
        block_span = block_limit - block_offset
        if block_span <= 0:
            if needed_length <= UFS_DIRBLKSIZ:
                return UFSDirectoryInsertSlot(
                    block_offset=block_offset,
                    entry_offset=block_offset,
                    record_length=UFS_DIRBLKSIZ,
                    previous_entry_offset=None,
                    previous_entry_new_length=None,
                )
            continue

        cursor = block_offset
        found_record = False
        while cursor + 8 <= block_limit:
            entry = decode_ufs_directory_entry(directory_bytes, cursor, block_limit)
            if entry is None:
                break
            found_record = True
            if entry.inode == 0 and entry.record_length >= needed_length:
                return UFSDirectoryInsertSlot(
                    block_offset=block_offset,
                    entry_offset=entry.offset,
                    record_length=entry.record_length,
                    previous_entry_offset=None,
                    previous_entry_new_length=None,
                )
            minimal_length = ufs_dirsiz(entry.name)
            available_length = entry.record_length - minimal_length
            if entry.inode != 0 and available_length >= needed_length:
                return UFSDirectoryInsertSlot(
                    block_offset=block_offset,
                    entry_offset=entry.offset + minimal_length,
                    record_length=available_length,
                    previous_entry_offset=entry.offset,
                    previous_entry_new_length=minimal_length,
                )
            cursor += entry.record_length

        if not found_record and needed_length <= UFS_DIRBLKSIZ:
            return UFSDirectoryInsertSlot(
                block_offset=block_offset,
                entry_offset=block_offset,
                record_length=UFS_DIRBLKSIZ,
                previous_entry_offset=None,
                previous_entry_new_length=None,
            )
    return None


def insert_ufs_directory_entry(directory_bytes: bytes, size: int, inode_number: int, name: str) -> bytes:
    slot = find_ufs_directory_insert_slot(directory_bytes, size, name)
    if slot is None:
        raise ValueError(f'no directory slot available for {name!r}')

    needed_length = ufs_dirsiz(name)
    target_length = max(needed_length, slot.record_length)
    new_size = max(len(directory_bytes), slot.block_offset + UFS_DIRBLKSIZ, slot.entry_offset + target_length)
    updated = bytearray(new_size)
    updated[:len(directory_bytes)] = directory_bytes

    if slot.previous_entry_offset is not None and slot.previous_entry_new_length is not None:
        updated[slot.previous_entry_offset + 4:slot.previous_entry_offset + 6] = slot.previous_entry_new_length.to_bytes(2, 'little', signed=False)
        target_length = slot.record_length
    else:
        remaining_length = slot.record_length - needed_length
        if remaining_length >= 8:
            updated[slot.entry_offset + needed_length:slot.entry_offset + slot.record_length] = encode_ufs_directory_entry(0, '', remaining_length)
            target_length = needed_length

    updated[slot.entry_offset:slot.entry_offset + target_length] = encode_ufs_directory_entry(inode_number, name, target_length)
    return bytes(updated)


def remove_ufs_directory_entry(directory_bytes: bytes, size: int, name: str) -> bytes:
    records = iter_ufs_directory_records(directory_bytes, size)
    updated = bytearray(directory_bytes)
    previous_record: UFSDirectoryEntry | None = None
    for record in records:
        if record.name != name or record.inode == 0:
            if (record.offset % UFS_DIRBLKSIZ) == 0:
                previous_record = None
            else:
                previous_record = record
            continue

        if previous_record is not None and (previous_record.offset // UFS_DIRBLKSIZ) == (record.offset // UFS_DIRBLKSIZ):
            merged_length = previous_record.record_length + record.record_length
            updated[previous_record.offset + 4:previous_record.offset + 6] = merged_length.to_bytes(2, 'little', signed=False)
        else:
            updated[record.offset:record.offset + record.record_length] = encode_ufs_directory_entry(0, '', record.record_length)
        return bytes(updated)
    raise ValueError(f'could not find directory entry {name!r} to remove')


def rewrite_ufs_directory_entry_inode(directory_bytes: bytes, size: int, name: str, inode_number: int) -> bytes:
    updated = bytearray(directory_bytes)
    for record in iter_ufs_directory_records(directory_bytes, size):
        if record.inode != 0 and record.name == name:
            updated[record.offset:record.offset + 4] = inode_number.to_bytes(4, 'little', signed=False)
            return bytes(updated)
    raise ValueError(f'could not find directory entry {name!r} to rewrite')