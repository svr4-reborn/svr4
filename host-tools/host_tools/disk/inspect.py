from __future__ import annotations

from pathlib import Path

from .fsprobe import probe_slice_filesystem
from .mbr import parse_mbr_sector
from .structures import AltInfo, DiskImageReport, HDPDLOC, MbrInfo, PdInfo, SECTOR_SIZE, SliceFilesystem, UNIXWARE_PARTITION_TYPE, VtocInfo, VtocPartition
from .svr4 import is_valid_alt_info, is_valid_pdinfo, is_valid_vtoc, parse_alt_info, parse_pdinfo, parse_vtoc, partition_tag_name, remap_guest_visible_sector


def find_active_unix_partition(mbr: MbrInfo):
    for partition in mbr.partitions:
        if partition.bootable and partition.partition_type == UNIXWARE_PARTITION_TYPE:
            return partition
    for partition in mbr.partitions:
        if partition.partition_type == UNIXWARE_PARTITION_TYPE:
            return partition
    return None


def read_sector(image_path: Path, sector_number: int, sector_count: int = 1) -> bytes:
    with image_path.open('rb') as handle:
        handle.seek(sector_number * SECTOR_SIZE)
        return handle.read(sector_count * SECTOR_SIZE)


def read_pdinfo(image_path: Path, partition_start: int) -> PdInfo:
    return parse_pdinfo(read_sector(image_path, partition_start + HDPDLOC))


def read_vtoc(image_path: Path, partition_start: int, pdinfo: PdInfo) -> VtocInfo:
    vtoc_sector = partition_start + (pdinfo.vtoc_ptr // SECTOR_SIZE)
    vtoc_offset = pdinfo.vtoc_ptr % SECTOR_SIZE
    vtoc_span = max(pdinfo.vtoc_len, SECTOR_SIZE)
    sector_count = max(1, (vtoc_offset + vtoc_span + SECTOR_SIZE - 1) // SECTOR_SIZE)
    block = read_sector(image_path, vtoc_sector, sector_count=sector_count)
    return parse_vtoc(block, offset=vtoc_offset)


def read_alt_info(image_path: Path, partition_start: int, pdinfo: PdInfo) -> AltInfo | None:
    if pdinfo.alt_len <= 0:
        return None
    alt_sector = partition_start + (pdinfo.alt_ptr // SECTOR_SIZE)
    alt_offset = pdinfo.alt_ptr % SECTOR_SIZE
    alt_span = max(pdinfo.alt_len, SECTOR_SIZE)
    sector_count = max(1, (alt_offset + alt_span + SECTOR_SIZE - 1) // SECTOR_SIZE)
    block = read_sector(image_path, alt_sector, sector_count=sector_count)
    alt_info = parse_alt_info(block, offset=alt_offset)
    if not is_valid_alt_info(alt_info):
        return None
    return alt_info


def read_slice_bytes(image_path: Path, absolute_start_sector: int, sector_count: int) -> bytes:
    return read_sector(image_path, absolute_start_sector, sector_count=sector_count)


def absolute_sector_for_slice(pdinfo: PdInfo, slice_start_sector: int) -> int:
    _ = pdinfo
    return slice_start_sector


def inspect_slice_by_selector(image_path: Path, selector: str) -> tuple[DiskImageReport, SliceFilesystem]:
    report, slice_info = inspect_slice_metadata_by_selector(image_path, selector)
    if slice_info.sector_count <= 0:
        return report, slice_info

    # Probe only the selected slice. The full-image inspector intentionally
    # reports root entries for every slice, but selector callers often run on
    # multi-GB images and should not read unrelated slices into memory.
    if partition_tag_name(slice_info.tag) == 'root':
        from host_tools.fs.disk_backed import DiskBackedSlice
        from host_tools.fs.ufs import detect_ufs_at_start, list_ufs_root

        slice_image = DiskBackedSlice(
            image_path,
            slice_info.absolute_start_sector * SECTOR_SIZE,
            slice_info.sector_count * SECTOR_SIZE,
        )
        try:
            filesystem = detect_ufs_at_start(slice_image)
            if filesystem is not None:
                slice_info = SliceFilesystem(
                    slice_index=slice_info.slice_index,
                    tag=slice_info.tag,
                    start_sector=slice_info.start_sector,
                    absolute_start_sector=slice_info.absolute_start_sector,
                    sector_count=slice_info.sector_count,
                    filesystem='ufs',
                    filesystem_offset=filesystem.start_offset,
                    root_entries=list_ufs_root(slice_image, filesystem),
                )
        finally:
            slice_image.close()
        return report, slice_info

    slice_image = read_slice_bytes(image_path, slice_info.absolute_start_sector, slice_info.sector_count)
    return report, probe_slice_filesystem(
        slice_info.slice_index,
        slice_info.tag,
        slice_info.start_sector,
        slice_info.absolute_start_sector,
        slice_info.sector_count,
        slice_image,
    )


def inspect_disk_metadata(image_path: Path) -> DiskImageReport:
    image_path = image_path.resolve()
    file_size = image_path.stat().st_size
    notes: list[str] = []
    mbr = parse_mbr_sector(read_sector(image_path, 0))
    if mbr.signature != 0xAA55:
        notes.append(f'Unexpected MBR signature 0x{mbr.signature:04x}; image may be unpartitioned or use a non-MBR boot sector.')

    active_unix_partition = find_active_unix_partition(mbr)
    pdinfo = None
    vtoc = None
    slice_filesystems: list[SliceFilesystem] = []

    if active_unix_partition is None:
        notes.append('No UNIX partition (type 0x63) was found in the MBR.')
    else:
        pdinfo = read_pdinfo(image_path, active_unix_partition.start_lba)
        if not is_valid_pdinfo(pdinfo):
            notes.append(
                f'Invalid pdinfo sanity 0x{pdinfo.sanity:08x} at sector {active_unix_partition.start_lba + HDPDLOC}; expected 0x{0xCA5E600D:08x}.'
            )
        else:
            vtoc = read_vtoc(image_path, active_unix_partition.start_lba, pdinfo)
            if not is_valid_vtoc(vtoc):
                notes.append(f'Invalid VTOC sanity 0x{vtoc.sanity:08x}; expected 0x{0x600DDEEE:08x}.')
            else:
                for partition in vtoc.partitions:
                    if partition.tag == 0 or partition.sector_count <= 0:
                        continue
                    absolute_start_sector = absolute_sector_for_slice(pdinfo, partition.start_sector)
                    slice_filesystems.append(
                        SliceFilesystem(
                            slice_index=partition.index,
                            tag=partition.tag,
                            start_sector=partition.start_sector,
                            absolute_start_sector=absolute_start_sector,
                            sector_count=partition.sector_count,
                        )
                    )

    return DiskImageReport(
        path=str(image_path),
        file_size=file_size,
        mbr=mbr,
        active_unix_partition=active_unix_partition,
        pdinfo=pdinfo,
        vtoc=vtoc,
        slice_filesystems=slice_filesystems,
        notes=notes,
    )


def inspect_slice_metadata_by_selector(image_path: Path, selector: str) -> tuple[DiskImageReport, SliceFilesystem]:
    report = inspect_disk_metadata(image_path)
    partition = get_vtoc_partition_by_selector(report, selector)
    for slice_info in report.slice_filesystems:
        if slice_info.slice_index == partition.index:
            return report, slice_info
    raise SystemExit(f'error: no slice matching {selector!r} was found')


def get_vtoc_partition_by_selector(report: DiskImageReport, selector: str) -> VtocPartition:
    if report.vtoc is None:
        raise SystemExit('error: image does not contain a valid VTOC')
    normalized = selector.strip().lower()
    for partition in report.vtoc.partitions:
        if str(partition.index) == normalized:
            return partition
    for partition in report.vtoc.partitions:
        if partition_tag_name(partition.tag) == normalized:
            return partition
    raise SystemExit(f'error: no slice matching {selector!r} was found')


def resolve_guest_visible_sector(image_path: Path, selector: str, slice_relative_sector: int) -> tuple[int, int, bytes]:
    report = inspect_disk_image(image_path)
    if report.active_unix_partition is None or report.pdinfo is None:
        raise SystemExit('error: image does not contain a valid active UNIX partition')
    partition = get_vtoc_partition_by_selector(report, selector)
    absolute_sector = partition.start_sector + slice_relative_sector
    alt_info = read_alt_info(image_path, report.active_unix_partition.start_lba, report.pdinfo)
    guest_visible_sector = remap_guest_visible_sector(report.pdinfo, partition, alt_info, absolute_sector)
    return absolute_sector, guest_visible_sector, read_sector(image_path, guest_visible_sector)


def inspect_disk_image(image_path: Path) -> DiskImageReport:
    image_path = image_path.resolve()
    file_size = image_path.stat().st_size
    notes: list[str] = []
    mbr = parse_mbr_sector(read_sector(image_path, 0))
    if mbr.signature != 0xAA55:
        notes.append(f'Unexpected MBR signature 0x{mbr.signature:04x}; image may be unpartitioned or use a non-MBR boot sector.')

    active_unix_partition = find_active_unix_partition(mbr)
    pdinfo = None
    vtoc = None
    slice_filesystems: list[SliceFilesystem] = []

    if active_unix_partition is None:
        notes.append('No UNIX partition (type 0x63) was found in the MBR.')
    else:
        pdinfo = read_pdinfo(image_path, active_unix_partition.start_lba)
        if not is_valid_pdinfo(pdinfo):
            notes.append(
                f'Invalid pdinfo sanity 0x{pdinfo.sanity:08x} at sector {active_unix_partition.start_lba + HDPDLOC}; expected 0x{0xCA5E600D:08x}.'
            )
        else:
            vtoc = read_vtoc(image_path, active_unix_partition.start_lba, pdinfo)
            if not is_valid_vtoc(vtoc):
                notes.append(f'Invalid VTOC sanity 0x{vtoc.sanity:08x}; expected 0x{0x600DDEEE:08x}.')
            else:
                for partition in vtoc.partitions:
                    if partition.tag == 0 or partition.sector_count <= 0:
                        continue
                    absolute_start_sector = absolute_sector_for_slice(
                        pdinfo,
                        partition.start_sector,
                    )
                    slice_image = read_slice_bytes(image_path, absolute_start_sector, partition.sector_count)
                    slice_filesystems.append(
                        probe_slice_filesystem(
                            partition.index,
                            partition.tag,
                            partition.start_sector,
                            absolute_start_sector,
                            partition.sector_count,
                            slice_image,
                        )
                    )

    return DiskImageReport(
        path=str(image_path),
        file_size=file_size,
        mbr=mbr,
        active_unix_partition=active_unix_partition,
        pdinfo=pdinfo,
        vtoc=vtoc,
        slice_filesystems=slice_filesystems,
        notes=notes,
    )
