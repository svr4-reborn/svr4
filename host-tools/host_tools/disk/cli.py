from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from host_tools.fs.bfs import format_bfs_filesystem

from .create import RawDiskGeometry, create_raw_image_skeleton
from .inspect import inspect_disk_image, inspect_slice_by_selector, read_slice_bytes
from .structures import DiskImageReport, MbrInfo, PartitionEntry, PdInfo, SliceFilesystem, VtocInfo, VtocPartition
from .svr4 import PARTITION_TAG_NAMES, partition_tag_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Inspect raw SVR4 disk images for host-side tooling.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    inspect_parser = subparsers.add_parser('inspect', help='Inspect a raw disk image.')
    inspect_parser.add_argument('image', help='Path to the disk image to inspect.')
    inspect_parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON.')

    format_bfs_parser = subparsers.add_parser('format-bfs', help='Format a slice as BFS and populate its root directory from host files.')
    format_bfs_parser.add_argument('image', help='Path to the source raw disk image.')
    format_bfs_parser.add_argument('--slice', required=True, help='Slice index or tag name, for example 10 or stand.')
    format_bfs_parser.add_argument('--output', required=True, help='Output raw disk image path. The source image is copied first, then the selected slice is formatted.')
    format_bfs_parser.add_argument('--file', action='append', default=[], help='BFS root file mapping as name=host_path. Repeat for multiple files.')
    format_bfs_parser.add_argument('--dirent-slots', type=int, help='Optional total dirent slot count to reserve, including the root inode slot.')

    create_parser = subparsers.add_parser('create-skeleton', help='Create a raw image with MBR, pdinfo, and VTOC metadata.')
    create_parser.add_argument('--output', required=True, help='Output raw image path.')
    create_parser.add_argument('--cylinders', type=int, required=True)
    create_parser.add_argument('--heads', type=int, required=True)
    create_parser.add_argument('--sectors', type=int, required=True, help='Sectors per track.')
    create_parser.add_argument('--unix-partition-start', type=int, default=1)
    create_parser.add_argument('--unix-partition-size', type=int, help='Size of the UNIX partition in sectors. Defaults to the rest of the disk.')
    create_parser.add_argument('--volume', default='SVR4')
    create_parser.add_argument(
        '--slice',
        action='append',
        default=[],
        help='Slice definition as index:tag:start:size:flag where tag may be numeric or a known name like root, swap, stand, boot, backup, alts.',
    )

    return parser


def parse_tag(value: str) -> int:
    lower = value.lower()
    for tag_number, tag_name in PARTITION_TAG_NAMES.items():
        if tag_name == lower:
            return tag_number
    return int(value, 0)


def parse_slice_definition(value: str) -> VtocPartition:
    parts = value.split(':')
    if len(parts) != 5:
        raise SystemExit(f'error: invalid slice definition {value!r}; expected index:tag:start:size:flag')
    return VtocPartition(
        index=int(parts[0], 0),
        tag=parse_tag(parts[1]),
        start_sector=int(parts[2], 0),
        sector_count=int(parts[3], 0),
        flag=int(parts[4], 0),
    )


def parse_bfs_file_mapping(value: str) -> tuple[str, Path]:
    name, separator, host_path = value.partition('=')
    if separator != '=' or not name or not host_path:
        raise SystemExit(f'error: invalid --file mapping {value!r}; expected name=host_path')
    return name, Path(host_path).resolve()


def format_bfs_path(
    image_path: Path,
    slice_selector: str,
    output_path: Path,
    file_mappings: list[tuple[str, Path]],
    dirent_slots: int | None,
) -> dict[str, int | str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image_path, output_path)
    _, slice_info = inspect_slice_by_selector(output_path, slice_selector)
    image_bytes = bytearray(read_slice_bytes(output_path, slice_info.absolute_start_sector, slice_info.sector_count))
    files = [(name, host_path.read_bytes()) for name, host_path in file_mappings]
    result = format_bfs_filesystem(image_bytes, files, dirent_slots=dirent_slots)
    with output_path.open('r+b') as handle:
        handle.seek(slice_info.absolute_start_sector * 512)
        handle.write(image_bytes)
    return {
        'slice': slice_selector,
        'file_count': result['file_count'],
        'dirent_slots': result['dirent_slots'],
        'image_size': result['image_size'],
    }


def create_skeleton(args: argparse.Namespace) -> None:
    geometry = RawDiskGeometry(cylinders=args.cylinders, heads=args.heads, sectors_per_track=args.sectors)
    unix_partition_size = args.unix_partition_size or (geometry.total_sectors - args.unix_partition_start)
    slices = [parse_slice_definition(value) for value in args.slice]
    create_raw_image_skeleton(
        Path(args.output).resolve(),
        geometry=geometry,
        unix_partition_start=args.unix_partition_start,
        unix_partition_size=unix_partition_size,
        volume=args.volume,
        slices=slices,
    )
    print(f'Created raw disk skeleton at {Path(args.output).resolve()}')


def format_partition_type(partition_type: int) -> str:
    return f'0x{partition_type:02x}'


def print_partition_table(mbr: MbrInfo) -> None:
    print(f'MBR signature: 0x{mbr.signature:04x}')
    print('Partitions:')
    for partition in mbr.partitions:
        if partition.partition_type == 0 and partition.start_lba == 0 and partition.sector_count == 0:
            continue
        boot_flag = '*' if partition.bootable else '-'
        print(
            f'  {partition.index}: {boot_flag} type={format_partition_type(partition.partition_type)} '
            f'start={partition.start_lba} sectors={partition.sector_count} '
            f'start_chs={partition.start_chs} end_chs={partition.end_chs}'
        )


def print_active_partition(active_unix_partition: PartitionEntry) -> None:
    print('Active UNIX partition:')
    print(
        f'  index={active_unix_partition.index} start={active_unix_partition.start_lba} '
        f'sectors={active_unix_partition.sector_count} type={format_partition_type(active_unix_partition.partition_type)}'
    )


def print_pdinfo(pdinfo: PdInfo) -> None:
    print('pdinfo:')
    print(f'  sanity: 0x{pdinfo.sanity:08x}')
    print(f'  geometry: {pdinfo.cylinders}/{pdinfo.tracks}/{pdinfo.sectors}')
    print(f'  bytes/sector: {pdinfo.bytes_per_sector}')
    print(f'  logical sector 0: {pdinfo.logical_sector_0}')
    print(f'  vtoc ptr/len: {pdinfo.vtoc_ptr}/{pdinfo.vtoc_len}')
    print(f'  alt ptr/len: {pdinfo.alt_ptr}/{pdinfo.alt_len}')


def print_vtoc(vtoc: VtocInfo) -> None:
    print('VTOC:')
    print(f'  sanity: 0x{vtoc.sanity:08x}')
    print(f'  version: {vtoc.version}')
    print(f'  volume: {vtoc.volume}')
    print(f'  partitions: {vtoc.partition_count}')
    for partition in vtoc.partitions:
        if partition.tag == 0 and partition.start_sector == 0 and partition.sector_count == 0:
            continue
        print(
            f'  slice {partition.index}: tag={partition_tag_name(partition.tag)} '
            f'flag=0x{partition.flag:04x} start={partition.start_sector} size={partition.sector_count}'
        )


def print_slice_filesystems(slice_filesystems: list[SliceFilesystem]) -> None:
    if not slice_filesystems:
        return
    print('Slice filesystems:')
    for slice_info in slice_filesystems:
        filesystem = slice_info.filesystem or 'unknown'
        print(
            f'  slice {slice_info.slice_index}: tag={partition_tag_name(slice_info.tag)} '
            f'fs={filesystem} start={slice_info.start_sector} absolute_start={slice_info.absolute_start_sector} size={slice_info.sector_count}'
        )
        for entry in slice_info.root_entries[:8]:
            size_suffix = f' size={entry["size"]}' if 'size' in entry else ''
            print(f'    {entry["name"]} inode={entry["inode"]}{size_suffix}')


def print_report(report: DiskImageReport) -> None:
    print(f'Image: {report.path}')
    print(f'File size: {report.file_size} bytes')
    print_partition_table(report.mbr)
    if report.active_unix_partition is not None:
        print_active_partition(report.active_unix_partition)
    if report.pdinfo is not None:
        print_pdinfo(report.pdinfo)
    if report.vtoc is not None:
        print_vtoc(report.vtoc)
    print_slice_filesystems(report.slice_filesystems)
    if report.notes:
        print('Notes:')
        for note in report.notes:
            print(f'  - {note}')


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == 'inspect':
        report = inspect_disk_image(Path(args.image))
        if args.json:
            print(f'{json.dumps(report, default=lambda value: value.__dict__, indent=2)}')
        else:
            print_report(report)
        return 0

    if args.command == 'format-bfs':
        result = format_bfs_path(
            Path(args.image).resolve(),
            args.slice,
            Path(args.output).resolve(),
            [parse_bfs_file_mapping(value) for value in args.file],
            args.dirent_slots,
        )
        print(f'{json.dumps(result, indent=2)}')
        return 0

    if args.command == 'create-skeleton':
        create_skeleton(args)
        return 0

    parser.error(f'unsupported command {args.command!r}')
    return 2