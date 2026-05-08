# pyright: reportMissingImports=false

import argparse
import importlib
import os
import re
import struct
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_TOOLS_ROOT = REPO_ROOT / 'host-tools'
if str(HOST_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(HOST_TOOLS_ROOT))

_disk_create = importlib.import_module('host_tools.disk.create')
_disk_inspect = importlib.import_module('host_tools.disk.inspect')
_disk_structures = importlib.import_module('host_tools.disk.structures')
_fs_bfs = importlib.import_module('host_tools.fs.bfs')
_fs_ufs = importlib.import_module('host_tools.fs.ufs')

RawDiskGeometry = _disk_create.RawDiskGeometry
create_raw_image_skeleton = _disk_create.create_raw_image_skeleton
ACTIVE_PARTITION_CHAINLOADER_MBR = _disk_create.ACTIVE_PARTITION_CHAINLOADER_MBR
MAX_CHS_CYLINDERS = _disk_create.MAX_CHS_CYLINDERS
MAX_KERNEL_CHS_HEADS = _disk_create.MAX_KERNEL_CHS_HEADS
MAX_CHS_SECTORS_PER_TRACK = _disk_create.MAX_CHS_SECTORS_PER_TRACK
inspect_slice_by_selector = _disk_inspect.inspect_slice_by_selector
read_slice_bytes = _disk_inspect.read_slice_bytes
VtocPartition = _disk_structures.VtocPartition
HDPDLOC = _disk_structures.HDPDLOC
format_bfs_filesystem = _fs_bfs.format_bfs_filesystem
create_ufs_file = _fs_ufs.create_ufs_file
create_ufs_special_file = _fs_ufs.create_ufs_special_file
format_ufs_filesystem = _fs_ufs.format_ufs_filesystem
make_ufs_directory = _fs_ufs.make_ufs_directory
symlink_ufs_path = _fs_ufs.symlink_ufs_path
UFS_IFBLK = _fs_ufs.UFS_IFBLK
UFS_IFCHR = _fs_ufs.UFS_IFCHR
recompute_ufs_summary_counts = _fs_ufs.recompute_ufs_summary_counts


EXPECTED_BOOT_FILES = ('unix', 'hdboot')
SECTOR_SIZE = 512
ELF_HEADER_SIZE = 52
ELF_PROGRAM_HEADER_SIZE = 32
PT_LOAD = 1
_DEFAULT_DEVICE_ASSIGNMENTS = {
    '/dev/root': (UFS_IFBLK, 0, 1),
    '/dev/pipe': (UFS_IFBLK, 0, 1),
    '/dev/swap': (UFS_IFBLK, 0, 2),
    '/dev/dump': (UFS_IFBLK, 0, 2),
    '/dev/sysmsg': (UFS_IFCHR, 19, 0),
}

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Build the hard drive image for SVR4')
    parser.add_argument('--image', required=True, help='Path to the output image file')
    parser.add_argument('--size', default=128, help='Size of the image in megabytes (default: 128)')
    parser.add_argument('--sysroot', default=str(REPO_ROOT / 'build/sysroot'), help='Path to the sysroot produced by Jinx')
    parser.add_argument('--stand-size', default=16, help='Size of the BFS /stand slice in megabytes (default: 16)')
    parser.add_argument('--swap-size', default=32, help='Size of the raw swap slice in megabytes (default: 32)')
    parser.add_argument('--heads', default=16, help='Disk geometry heads value (default: 16)')
    parser.add_argument('--sectors', default=63, help='Disk geometry sectors-per-track value (default: 63)')
    parser.add_argument('--stand-start-sector', default=64, help='Absolute disk sector where the stand slice starts (default: 64)')
    parser.add_argument('--root-align-sectors', default=2048, help='Alignment for the root slice start in sectors (default: 2048)')
    parser.add_argument('--allow-missing-boot-files', action='store_true', help='Build the image even if expected /stand boot files are missing')
    parser.add_argument('--reuse-existing', action='store_true', help='Reuse the existing image file if it exists')
    return parser


def _parse_positive_int(value: str, *, name: str) -> int:
    parsed = int(value, 0)
    if parsed <= 0:
        raise SystemExit(f'error: {name} must be positive')
    return parsed


def _align_up(value: int, alignment: int) -> int:
    if alignment <= 0:
        return value
    return ((value + alignment - 1) // alignment) * alignment


def _build_geometry(size_mb: int, heads: int, sectors_per_track: int) -> RawDiskGeometry:
    total_sectors = _align_up((size_mb * 1024 * 1024) // SECTOR_SIZE, heads * sectors_per_track)
    cylinders = total_sectors // (heads * sectors_per_track)
    if heads > MAX_KERNEL_CHS_HEADS:
        raise SystemExit(f'error: CHS geometry exceeds current kernel head limit ({heads} > {MAX_KERNEL_CHS_HEADS})')
    if sectors_per_track > MAX_CHS_SECTORS_PER_TRACK:
        raise SystemExit(
            f'error: CHS geometry exceeds sector-per-track limit '
            f'({sectors_per_track} > {MAX_CHS_SECTORS_PER_TRACK})'
        )
    if cylinders > MAX_CHS_CYLINDERS:
        raise SystemExit(
            f'error: requested image size needs {cylinders} cylinders, which exceeds '
            f'the CHS limit of {MAX_CHS_CYLINDERS}; reduce --size or change geometry'
        )
    return RawDiskGeometry(cylinders=cylinders, heads=heads, sectors_per_track=sectors_per_track)


def _build_slice_layout(
    geometry: RawDiskGeometry,
    *,
    stand_start_sector: int,
    stand_size_mb: int,
    swap_size_mb: int,
    root_align_sectors: int,
) -> tuple[int, int, list[VtocPartition]]:
    sectors_per_cylinder = geometry.heads * geometry.sectors_per_track
    unix_partition_start = 1
    unix_partition_size = geometry.total_sectors - unix_partition_start
    stand_start_sector = _align_up(stand_start_sector, sectors_per_cylinder)
    stand_sector_count = _align_up((stand_size_mb * 1024 * 1024) // SECTOR_SIZE, sectors_per_cylinder)
    swap_sector_count = _align_up((swap_size_mb * 1024 * 1024) // SECTOR_SIZE, sectors_per_cylinder)
    if stand_sector_count <= 0:
        raise SystemExit('error: stand slice size must be positive')
    if swap_sector_count <= 0:
        raise SystemExit('error: swap slice size must be positive')
    stand_end_sector = stand_start_sector + stand_sector_count
    swap_start_sector = _align_up(_align_up(stand_end_sector, root_align_sectors), sectors_per_cylinder)
    swap_end_sector = swap_start_sector + swap_sector_count
    root_start_sector = _align_up(_align_up(swap_end_sector, root_align_sectors), sectors_per_cylinder)
    if stand_start_sector < unix_partition_start:
        raise SystemExit('error: stand slice starts before the UNIX partition')
    if root_start_sector >= geometry.total_sectors:
        raise SystemExit('error: root slice would start beyond the end of the disk image')

    root_sector_count = ((geometry.total_sectors - root_start_sector) // sectors_per_cylinder) * sectors_per_cylinder
    if root_sector_count <= 0:
        raise SystemExit('error: root slice would be empty')

    slices = [
        VtocPartition(index=0, tag=0x05, flag=0x201, start_sector=unix_partition_start, sector_count=unix_partition_size),
        VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=root_start_sector, sector_count=root_sector_count),
        VtocPartition(index=2, tag=0x03, flag=0x201, start_sector=swap_start_sector, sector_count=swap_sector_count),
        VtocPartition(index=10, tag=0x09, flag=0x200, start_sector=stand_start_sector, sector_count=stand_sector_count),
    ]
    return unix_partition_start, unix_partition_size, slices


def _write_slice_bytes(image_path: Path, start_sector: int, payload: bytes) -> None:
    with image_path.open('r+b') as handle:
        handle.seek(start_sector * SECTOR_SIZE)
        handle.write(payload)


def _build_hdboot_partition_bootstrap(hdboot_path: Path) -> bytes:
    payload = hdboot_path.read_bytes()
    if len(payload) < ELF_HEADER_SIZE or payload[:4] != b'\x7fELF':
        raise SystemExit(f'error: expected {hdboot_path} to be a 32-bit ELF hard-disk bootstrap image')

    ei_class = payload[4]
    ei_data = payload[5]
    if ei_class != 1 or ei_data != 1:
        raise SystemExit(f'error: expected {hdboot_path} to be a 32-bit little-endian ELF image')

    e_phoff = struct.unpack_from('<L', payload, 28)[0]
    e_phentsize = struct.unpack_from('<H', payload, 42)[0]
    e_phnum = struct.unpack_from('<H', payload, 44)[0]
    if e_phnum == 0 or e_phentsize < ELF_PROGRAM_HEADER_SIZE:
        raise SystemExit(f'error: ELF bootstrap {hdboot_path} does not contain usable program headers')

    bootstrap_limit = HDPDLOC * SECTOR_SIZE
    flattened = bytearray(bootstrap_limit)
    max_end = 0
    found_load = False
    for index in range(e_phnum):
        entry_offset = e_phoff + (index * e_phentsize)
        if entry_offset + ELF_PROGRAM_HEADER_SIZE > len(payload):
            raise SystemExit(f'error: ELF bootstrap {hdboot_path} is truncated in the program header table')
        p_type, p_offset, _p_vaddr, p_paddr, p_filesz, _p_memsz, _p_flags, _p_align = struct.unpack_from(
            '<LLLLLLLL',
            payload,
            entry_offset,
        )
        if p_type != PT_LOAD or p_filesz == 0:
            continue
        found_load = True
        end_offset = p_paddr + p_filesz
        if end_offset > bootstrap_limit:
            raise SystemExit(
                f'error: hard-disk bootstrap {hdboot_path} needs {end_offset} bytes, '
                f'but only {bootstrap_limit} bytes are available before pdinfo'
            )
        file_end = p_offset + p_filesz
        if file_end > len(payload):
            raise SystemExit(f'error: ELF bootstrap {hdboot_path} is truncated in a PT_LOAD segment')
        flattened[p_paddr:end_offset] = payload[p_offset:file_end]
        max_end = max(max_end, end_offset)

    if not found_load:
        raise SystemExit(f'error: ELF bootstrap {hdboot_path} does not contain any PT_LOAD segments')

    if bytes(flattened[510:512]) != b'\x55\xaa':
        raise SystemExit(
            f'error: hard-disk bootstrap {hdboot_path} does not place the boot signature at offset 510; '
            'rebuild uts with the corrected WINI bootstrap layout'
        )

    return bytes(flattened[:bootstrap_limit])


def _collect_boot_files(stand_dir: Path) -> tuple[list[tuple[str, bytes]], list[str], list[str]]:
    if not stand_dir.is_dir():
        raise SystemExit(f'error: expected {stand_dir} to exist and be a directory')

    boot_files: list[tuple[str, bytes]] = []
    present_names: list[str] = []
    for child in sorted(stand_dir.iterdir(), key=lambda path: path.name):
        if child.name.startswith('.'):
            continue
        present_names.append(child.name)
        if child.is_dir():
            raise SystemExit(f'error: BFS /stand population only supports flat files; found directory {child}')
        if child.is_symlink():
            raise SystemExit(f'error: BFS /stand population does not support symlinks; found {child}')
        if not child.is_file():
            raise SystemExit(f'error: unsupported /stand entry {child}')
        boot_files.append((child.name, child.read_bytes()))

    missing = [name for name in EXPECTED_BOOT_FILES if name not in present_names]
    return boot_files, present_names, missing


def _ensure_ufs_parent_directories(image: bytearray, filesystem: Any, relative_path: Path) -> None:
    if relative_path == Path('.'):
        return
    current = Path('/')
    for part in relative_path.parts:
        current /= part
        if str(current) == '/':
            continue
        try:
            make_ufs_directory(image, filesystem, current.as_posix(), recompute_summary=False)
        except SystemExit as error:
            if 'already exists inside the ufs filesystem' not in str(error):
                raise


def _populate_root_slice(image: bytearray, filesystem: Any, sysroot: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(sysroot, topdown=True, followlinks=False):
        dir_path = Path(dirpath)
        relative_dir = dir_path.relative_to(sysroot)
        dirnames.sort()
        filenames.sort()

        _ensure_ufs_parent_directories(image, filesystem, relative_dir)
        if relative_dir == Path('stand'):
            dirnames[:] = []
            continue

        for directory_name in dirnames:
            relative_path = relative_dir / directory_name
            if relative_path == Path('stand'):
                make_ufs_directory(image, filesystem, '/stand', recompute_summary=False)
                continue
            host_path = sysroot / relative_path
            mode = host_path.lstat().st_mode & 0o777
            make_ufs_directory(
                image,
                filesystem,
                '/' + relative_path.as_posix(),
                mode=mode or 0o755,
                recompute_summary=False,
            )

        for file_name in filenames:
            relative_path = relative_dir / file_name
            if relative_path.parts and relative_path.parts[0] == 'stand':
                continue
            host_path = sysroot / relative_path
            guest_path = '/' + relative_path.as_posix()
            host_stat = host_path.lstat()
            if os.path.islink(host_path):
                symlink_ufs_path(image, filesystem, os.readlink(host_path), guest_path, recompute_summary=False)
                continue
            if not host_path.is_file():
                raise SystemExit(f'error: unsupported sysroot entry {host_path}')
            create_ufs_file(
                image,
                filesystem,
                guest_path,
                host_path.read_bytes(),
                mode=host_stat.st_mode & 0o777 or 0o644,
                recompute_summary=False,
            )


def _load_kernel_device_assignments() -> dict[str, tuple[int, int, int]]:
    config_path = REPO_ROOT / 'build/builds/uts/build/uts/i386/conf/cf.d/conf.c'
    assignments = dict(_DEFAULT_DEVICE_ASSIGNMENTS)
    if not config_path.is_file():
        return assignments
    pattern = re.compile(r'dev_t\s+(rootdev|pipedev|swapdev|dumpdev)\s*=\s*makedevice\((\d+),\s*(\d+)\);')
    mapping = {
        'rootdev': '/dev/root',
        'pipedev': '/dev/pipe',
        'swapdev': '/dev/swap',
        'dumpdev': '/dev/dump',
    }
    for match in pattern.finditer(config_path.read_text()):
        path = mapping[match.group(1)]
        file_type, _major, _minor = assignments[path]
        assignments[path] = (file_type, int(match.group(2)), int(match.group(3)))

    sysmsg_mdevice_path = REPO_ROOT / 'build/builds/uts/build/uts/i386/conf/mdevice.d/sysmsg'
    if sysmsg_mdevice_path.is_file():
        for line in sysmsg_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'sysmsg':
                break
            assignments['/dev/sysmsg'] = (UFS_IFCHR, int(fields[5], 0), 0)
            break
    return assignments


def _populate_required_device_nodes(image: bytearray, filesystem: Any) -> None:
    try:
        make_ufs_directory(image, filesystem, '/dev', mode=0o755, recompute_summary=False)
    except SystemExit as error:
        if 'already exists inside the ufs filesystem' not in str(error):
            raise
    for path, (file_type, major, minor) in _load_kernel_device_assignments().items():
        try:
            create_ufs_special_file(
                image,
                filesystem,
                path,
                file_type=file_type,
                major=major,
                minor=minor,
                mode=0o600,
                recompute_summary=False,
            )
        except SystemExit as error:
            if 'already exists inside the ufs filesystem' not in str(error):
                raise


def _prepare_base_image(
    image_path: Path,
    *,
    reuse_existing: bool,
    geometry: RawDiskGeometry,
    unix_partition_start: int,
    unix_partition_size: int,
    slices: list[VtocPartition],
) -> None:
    image_path.parent.mkdir(parents=True, exist_ok=True)
    if reuse_existing and image_path.exists():
        return
    create_raw_image_skeleton(
        image_path,
        geometry=geometry,
        unix_partition_start=unix_partition_start,
        unix_partition_size=unix_partition_size,
        volume='SVR4',
        slices=slices,
        mbr_boot_code=ACTIVE_PARTITION_CHAINLOADER_MBR,
    )


def build_image(args: argparse.Namespace) -> None:
    image_path = Path(args.image).resolve()
    sysroot = Path(args.sysroot).resolve()
    stand_dir = sysroot / 'stand'

    size_mb = _parse_positive_int(str(args.size), name='size')
    stand_size_mb = _parse_positive_int(str(args.stand_size), name='stand-size')
    swap_size_mb = _parse_positive_int(str(args.swap_size), name='swap-size')
    heads = _parse_positive_int(str(args.heads), name='heads')
    sectors_per_track = _parse_positive_int(str(args.sectors), name='sectors')
    stand_start_sector = _parse_positive_int(str(args.stand_start_sector), name='stand-start-sector')
    root_align_sectors = _parse_positive_int(str(args.root_align_sectors), name='root-align-sectors')

    if not sysroot.is_dir():
        raise SystemExit(f'error: sysroot {sysroot} does not exist')

    boot_files, present_boot_files, missing_boot_files = _collect_boot_files(stand_dir)
    hdboot_partition_bootstrap = _build_hdboot_partition_bootstrap(stand_dir / 'hdboot')
    if missing_boot_files and not args.allow_missing_boot_files:
        found = ', '.join(present_boot_files) if present_boot_files else '(none)'
        missing = ', '.join(missing_boot_files)
        raise SystemExit(
            'error: /stand is missing expected boot files for a bootable image: '
            f'{missing}. Found: {found}. Add them or rerun with --allow-missing-boot-files.'
        )

    geometry = _build_geometry(size_mb, heads, sectors_per_track)
    unix_partition_start, unix_partition_size, slices = _build_slice_layout(
        geometry,
        stand_start_sector=stand_start_sector,
        stand_size_mb=stand_size_mb,
        swap_size_mb=swap_size_mb,
        root_align_sectors=root_align_sectors,
    )

    with tempfile.TemporaryDirectory(prefix='svr4-image-build-') as temp_dir:
        temp_image_path = Path(temp_dir) / image_path.name
        if args.reuse_existing and image_path.exists():
            shutil.copyfile(image_path, temp_image_path)
        _prepare_base_image(
            temp_image_path,
            reuse_existing=args.reuse_existing,
            geometry=geometry,
            unix_partition_start=unix_partition_start,
            unix_partition_size=unix_partition_size,
            slices=slices,
        )
        _write_slice_bytes(temp_image_path, unix_partition_start, hdboot_partition_bootstrap)

        _, stand_slice = inspect_slice_by_selector(temp_image_path, 'stand')
        stand_slice_bytes = bytearray(read_slice_bytes(temp_image_path, stand_slice.absolute_start_sector, stand_slice.sector_count))
        format_bfs_filesystem(stand_slice_bytes, boot_files)
        _write_slice_bytes(temp_image_path, stand_slice.absolute_start_sector, stand_slice_bytes)

        _, root_slice = inspect_slice_by_selector(temp_image_path, 'root')
        root_slice_bytes = bytearray(read_slice_bytes(temp_image_path, root_slice.absolute_start_sector, root_slice.sector_count))
        filesystem = format_ufs_filesystem(
            root_slice_bytes,
            timestamp=int(time.time()),
            block_size=4096,
            tracks_per_cylinder=geometry.heads,
            sectors_per_track=geometry.sectors_per_track,
        )
        _populate_root_slice(root_slice_bytes, filesystem, sysroot)
        _populate_required_device_nodes(root_slice_bytes, filesystem)
        recompute_ufs_summary_counts(root_slice_bytes, filesystem)
        _write_slice_bytes(temp_image_path, root_slice.absolute_start_sector, root_slice_bytes)

        shutil.copyfile(temp_image_path, image_path)

    missing_note = '' if not missing_boot_files else f' Missing boot files: {", ".join(missing_boot_files)}.'
    print(f'Built SVR4 image at {image_path}.{missing_note}')

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    build_image(args)

if __name__ == '__main__':
    main()