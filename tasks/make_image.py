# pyright: reportMissingImports=false

import argparse
from contextlib import contextmanager
import importlib
import json
import os
import re
import signal
import struct
import subprocess
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
_fs_disk_backed = importlib.import_module('host_tools.fs.disk_backed')
_fs_bfs = importlib.import_module('host_tools.fs.bfs')
_fs_ufs = importlib.import_module('host_tools.fs.ufs')
_fs_ufs_fuse = importlib.import_module('host_tools.fs.ufs_fuse')

RawDiskGeometry = _disk_create.RawDiskGeometry
create_raw_image_skeleton = _disk_create.create_raw_image_skeleton
build_mbr = _disk_create.build_mbr
ACTIVE_PARTITION_CHAINLOADER_MBR = _disk_create.ACTIVE_PARTITION_CHAINLOADER_MBR
DISK_ADDRESSING_CHS = _disk_create.DISK_ADDRESSING_CHS
DISK_ADDRESSING_LBA28 = _disk_create.DISK_ADDRESSING_LBA28
MAX_CHS_CYLINDERS = _disk_create.MAX_CHS_CYLINDERS
MAX_KERNEL_CHS_HEADS = _disk_create.MAX_KERNEL_CHS_HEADS
MAX_CHS_SECTORS_PER_TRACK = _disk_create.MAX_CHS_SECTORS_PER_TRACK
read_sector = _disk_inspect.read_sector
read_slice_bytes = _disk_inspect.read_slice_bytes
inspect_disk_metadata = _disk_inspect.inspect_disk_metadata
VtocPartition = _disk_structures.VtocPartition
HDPDLOC = _disk_structures.HDPDLOC
DiskBackedSlice = _fs_disk_backed.DiskBackedSlice
format_bfs_filesystem = _fs_bfs.format_bfs_filesystem
detect_bfs = _fs_bfs.detect_bfs
create_ufs_special_file = _fs_ufs.create_ufs_special_file
format_ufs_filesystem = _fs_ufs.format_ufs_filesystem
detect_ufs_at_start = _fs_ufs.detect_ufs_at_start
link_ufs_path = _fs_ufs.link_ufs_path
make_ufs_directory = _fs_ufs.make_ufs_directory
resolve_ufs_path = _fs_ufs.resolve_ufs_path
write_ufs_inode_mode = _fs_ufs.write_ufs_inode_mode
UFS_IFBLK = _fs_ufs.UFS_IFBLK
UFS_IFCHR = _fs_ufs.UFS_IFCHR
UFS_IFDIR = _fs_ufs.UFS_IFDIR
UFS_IFMT = _fs_ufs.UFS_IFMT
UFS_ROOT_INODE = _fs_ufs.UFS_ROOT_INODE
refresh_ufs_summary_layout = _fs_ufs.refresh_ufs_summary_layout
UFSVolume = _fs_ufs_fuse.UFSVolume


EXPECTED_BOOT_FILES = ('unix', 'hdboot')
SECTOR_SIZE = 512
ELF_HEADER_SIZE = 52
ELF_PROGRAM_HEADER_SIZE = 32
PT_LOAD = 1
_DEFAULT_DEVICE_ASSIGNMENTS = {
    '/dev/console': (UFS_IFCHR, 30, 0),
    '/dev/syscon': (UFS_IFCHR, 30, 0),
    '/dev/tty': (UFS_IFCHR, 16, 0),
    '/dev/vt00': (UFS_IFCHR, 5, 0),
    '/dev/vtmon': (UFS_IFCHR, 30, 15),
    '/dev/video': (UFS_IFCHR, 29, 0),
    '/dev/vidadm': (UFS_IFCHR, 29, 1),
    '/dev/kd/kd00': (UFS_IFCHR, 30, 0),
    '/dev/kd/kdvm00': (UFS_IFCHR, 20, 0),
    '/dev/sad/admin': (UFS_IFCHR, 25, 1),
    '/dev/sad/user': (UFS_IFCHR, 25, 0),
    '/dev/root': (UFS_IFBLK, 0, 1),
    '/dev/pipe': (UFS_IFBLK, 0, 1),
    '/dev/swap': (UFS_IFBLK, 0, 2),
    '/dev/dump': (UFS_IFBLK, 0, 2),
    '/dev/null': (UFS_IFCHR, 2, 2),
    '/dev/sysmsg': (UFS_IFCHR, 19, 0),
    '/dev/zero': (UFS_IFCHR, 2, 4),
    '/dev/urandom': (UFS_IFCHR, 2, 5),
}
_NETWORK_NODE_MODULES = (
    'arp',
    'icmp',
    'ip',
    'llcloop',
    'rawip',
    'tcp',
    'ticlts',
    'ticots',
    'ticotsor',
    'udp',
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Build the hard drive image for SVR4')
    parser.add_argument('--image', required=True, help='Path to the output image file')
    parser.add_argument('--size', default=324, help='Size of the image in megabytes (default: 160)')
    parser.add_argument('--sysroot', default=str(REPO_ROOT / 'build/sysroot'), help='Path to the sysroot produced by Jinx')
    parser.add_argument('--stand-size', default=16, help='Size of the BFS /stand slice in megabytes (default: 16)')
    parser.add_argument('--swap-size', default=64, help='Size of the raw swap slice in megabytes (default: 64)')
    parser.add_argument('--ufs-bytes-per-inode', default=8192, help='Target UFS inode density in bytes per inode (default: 8192)')
    parser.add_argument('--kernel-conf', help='Path to the generated uts/i386/conf directory (default: infer from --sysroot)')
    parser.add_argument('--heads', default=16, help='Disk geometry heads value (default: 16)')
    parser.add_argument('--sectors', default=63, help='Disk geometry sectors-per-track value (default: 63)')
    parser.add_argument(
        '--disk-addressing',
        choices=[DISK_ADDRESSING_CHS, DISK_ADDRESSING_LBA28],
        default=DISK_ADDRESSING_CHS,
        help='Disk addressing mode for validation and MBR CHS fields (default: chs)',
    )
    parser.add_argument('--stand-start-sector', default=64, help='Absolute disk sector where the stand slice starts (default: 64)')
    parser.add_argument('--root-align-sectors', default=2048, help='Alignment for the root slice start in sectors (default: 2048)')
    parser.add_argument('--allow-missing-boot-files', action='store_true', help='Build the image even if expected /stand boot files are missing')
    parser.add_argument('--force-reformat', action='store_true', help='Always recreate and reformat the image instead of reusing a valid existing image')
    parser.add_argument('--no-reuse-existing', action='store_true', help='Alias for --force-reformat')
    parser.add_argument('--reuse-existing', action='store_true', help=argparse.SUPPRESS)
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


def _build_geometry(size_mb: int, heads: int, sectors_per_track: int, disk_addressing: str) -> RawDiskGeometry:
    total_sectors = _align_up((size_mb * 1024 * 1024) // SECTOR_SIZE, heads * sectors_per_track)
    cylinders = total_sectors // (heads * sectors_per_track)
    if heads > MAX_KERNEL_CHS_HEADS:
        raise SystemExit(f'error: CHS geometry exceeds current kernel head limit ({heads} > {MAX_KERNEL_CHS_HEADS})')
    if sectors_per_track > MAX_CHS_SECTORS_PER_TRACK:
        raise SystemExit(
            f'error: CHS geometry exceeds sector-per-track limit '
            f'({sectors_per_track} > {MAX_CHS_SECTORS_PER_TRACK})'
        )
    if disk_addressing == DISK_ADDRESSING_CHS and cylinders > MAX_CHS_CYLINDERS:
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


def _get_layout_slice(slices: list[VtocPartition], selector: str) -> VtocPartition:
    normalized = selector.strip().lower()
    wanted_index = {
        '1': 1,
        'root': 1,
        '2': 2,
        'swap': 2,
        '10': 10,
        'stand': 10,
    }.get(normalized)
    if wanted_index is None:
        raise SystemExit(f'error: no slice matching {selector!r} was found')

    for partition in slices:
        if partition.index == wanted_index:
            return partition

    raise SystemExit(f'error: no slice matching {selector!r} was found')


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


def _kernel_conf_roots(*, sysroot: Path, explicit_kernel_conf: Path | None) -> list[Path]:
    candidates = []
    if explicit_kernel_conf is not None:
        candidates.append(explicit_kernel_conf)
    candidates.extend([
        sysroot.parent / 'builds/uts/build/uts/i386/conf',
        REPO_ROOT / 'build/builds/uts/build/uts/i386/conf',
        REPO_ROOT / 'build/uts/i386/conf',
    ])

    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def _find_kernel_conf_file(conf_roots: list[Path], relative_path: str) -> Path | None:
    for conf_root in conf_roots:
        candidate = conf_root / relative_path
        if candidate.is_file():
            return candidate
    return None


def _find_kernel_conf_directory(conf_roots: list[Path], relative_path: str) -> Path | None:
    for conf_root in conf_roots:
        candidate = conf_root / relative_path
        if candidate.is_dir():
            return candidate
    return None


def _iter_kernel_metadata_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith('*') or stripped.startswith('#'):
            continue
        lines.append(stripped)
    return lines


def _parse_kernel_number(token: str) -> int:
    try:
        return int(token, 0)
    except ValueError:
        return int(token, 16)


def _parse_node_minor(token: str, character_majors: dict[str, int]) -> int:
    if token in character_majors:
        return character_majors[token]
    if re.fullmatch(r'0[0-7]+', token):
        return int(token, 8)
    return _parse_kernel_number(token)


def _load_kernel_character_majors(conf_roots: list[Path]) -> dict[str, int]:
    manifest_path = _find_kernel_conf_file(conf_roots, 'cf.d/simple-idconfig.json')
    if manifest_path is None:
        return {}
    manifest = json.loads(manifest_path.read_text())
    character_majors: dict[str, int] = {}
    for raw_device in manifest.get('devices', []):
        if not raw_device.get('configured'):
            continue
        if 'c' not in str(raw_device.get('type_flags', '')):
            continue
        character_major = raw_device.get('char_major_start')
        if character_major is None:
            continue
        character_majors[str(raw_device['name'])] = int(character_major)
    return character_majors


def _load_network_device_assignments(conf_roots: list[Path]) -> dict[str, tuple[int, int, int]]:
    character_majors = _load_kernel_character_majors(conf_roots)
    node_dir = _find_kernel_conf_directory(conf_roots, 'node.d')
    assignments: dict[str, tuple[int, int, int]] = {}
    if not character_majors or node_dir is None:
        return assignments

    for module_name in _NETWORK_NODE_MODULES:
        node_path = node_dir / module_name
        if not node_path.is_file():
            continue
        for line in _iter_kernel_metadata_lines(node_path):
            fields = line.split()
            if len(fields) < 4:
                continue
            device_name, relative_path, node_type, minor_token = fields[:4]
            if not node_type.startswith('c'):
                continue
            major = character_majors.get(device_name)
            if major is None:
                continue
            try:
                minor = _parse_node_minor(minor_token, character_majors)
            except ValueError:
                continue
            assignments[f'/dev/{relative_path}'] = (UFS_IFCHR, major, minor)
    return assignments


def _load_kernel_device_assignments(conf_roots: list[Path]) -> dict[str, tuple[int, int, int]]:
    config_path = _find_kernel_conf_file(conf_roots, 'cf.d/conf.c')
    assignments = dict(_DEFAULT_DEVICE_ASSIGNMENTS)
    if config_path is None:
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

    sysmsg_mdevice_path = _find_kernel_conf_file(conf_roots, 'mdevice.d/sysmsg')
    if sysmsg_mdevice_path is not None:
        for line in sysmsg_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'sysmsg':
                break
            assignments['/dev/sysmsg'] = (UFS_IFCHR, int(fields[5], 0), 0)
            break

    mem_mdevice_path = _find_kernel_conf_file(conf_roots, 'mdevice.d/mem')
    if mem_mdevice_path is not None:
        for line in mem_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'mem':
                break
            mem_major = int(fields[5], 0)
            assignments['/dev/null'] = (UFS_IFCHR, mem_major, 2)
            assignments['/dev/zero'] = (UFS_IFCHR, mem_major, 4)
            assignments['/dev/urandom'] = (UFS_IFCHR, mem_major, 5)
            break

    cmux_mdevice_path = _find_kernel_conf_file(conf_roots, 'mdevice.d/cmux')
    if cmux_mdevice_path is not None:
        for line in cmux_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'cmux':
                break
            assignments['/dev/vt00'] = (UFS_IFCHR, int(fields[5], 0), 0)
            break

    kd_mdevice_path = _find_kernel_conf_file(conf_roots, 'mdevice.d/kd')
    if kd_mdevice_path is not None:
        for line in kd_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'kd':
                break
            assignments['/dev/console'] = (UFS_IFCHR, int(fields[5], 0), 0)
            assignments['/dev/syscon'] = assignments['/dev/console']
            assignments['/dev/vtmon'] = (UFS_IFCHR, int(fields[5], 0), 15)
            assignments['/dev/kd/kd00'] = (UFS_IFCHR, int(fields[5], 0), 0)
            assignments['/dev/kd/kd01'] = (UFS_IFCHR, int(fields[5], 0), 1)
            break

    kdvm_mdevice_path = _find_kernel_conf_file(conf_roots, 'mdevice.d/kdvm')
    if kdvm_mdevice_path is not None:
        for line in kdvm_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'kdvm':
                break
            assignments['/dev/kd/kdvm00'] = (UFS_IFCHR, int(fields[5], 0), 0)
            assignments['/dev/kd/kdvm01'] = (UFS_IFCHR, int(fields[5], 0), 1)
            break

    gvid_mdevice_path = _find_kernel_conf_file(conf_roots, 'mdevice.d/gvid')
    if gvid_mdevice_path is not None:
        for line in gvid_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'gvid':
                break
            assignments['/dev/video'] = (UFS_IFCHR, int(fields[5], 0), 0)
            assignments['/dev/vidadm'] = (UFS_IFCHR, int(fields[5], 0), 1)
            break

    m320_mdevice_path = _find_kernel_conf_file(conf_roots, 'mdevice.d/m320')
    if m320_mdevice_path is not None:
        for line in m320_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'm320':
                break
            assignments['/dev/mouse'] = (UFS_IFCHR, int(fields[5], 0), 0)
            break

    sad_mdevice_path = _find_kernel_conf_file(conf_roots, 'mdevice.d/sad')
    if sad_mdevice_path is not None:
        for line in sad_mdevice_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*') or stripped.startswith('#'):
                continue
            fields = stripped.split()
            if len(fields) < 6 or fields[0] != 'sad':
                break
            sad_major = int(fields[5], 0)
            assignments['/dev/sad/user'] = (UFS_IFCHR, sad_major, 0)
            assignments['/dev/sad/admin'] = (UFS_IFCHR, sad_major, 1)
            break
    assignments.update(_load_network_device_assignments(conf_roots))

    # Add pseudo-terminal devices
    character_majors = _load_kernel_character_majors(conf_roots)
    clone_major = character_majors.get('clone', 4)
    ptm_major = character_majors.get('ptm', 11)
    pts_major = character_majors.get('pts', 35)

    assignments['/dev/ptmx'] = (UFS_IFCHR, clone_major, ptm_major)
    for i in range(32):
        assignments[f'/dev/pts/{i}'] = (UFS_IFCHR, pts_major, i)

    return assignments


def _ensure_ufs_directory(image: bytearray, filesystem: Any, path: str, *, mode: int = 0o755) -> None:
    try:
        make_ufs_directory(image, filesystem, path, mode=mode, recompute_summary=False)
    except SystemExit as error:
        if 'already exists inside the ufs filesystem' not in str(error):
            raise
        resolved = resolve_ufs_path(image, filesystem, path)
        if resolved is None:
            raise
        inode_number, inode = resolved
        if int(inode['mode']) & UFS_IFMT != UFS_IFDIR:
            raise SystemExit(f'error: required path {path} exists but is not a directory')
        write_ufs_inode_mode(image, filesystem, inode_number, UFS_IFDIR | mode)


def _populate_required_runtime_directories(image: bytearray, filesystem: Any) -> None:
    required_directories = {
        '/root': 0o755,
        '/tmp': 0o1777,
        '/tmp/.X11-unix': 0o1777,
        '/var': 0o755,
        '/var/lib': 0o755,
        '/var/lib/xkb': 0o755,
        '/var/log': 0o755,
    }
    for path, mode in required_directories.items():
        _ensure_ufs_directory(image, filesystem, path, mode=mode)


def _required_device_directories(assignments: dict[str, tuple[int, int, int]]) -> list[str]:
    directories = {'/dev', '/dev/kd', '/dev/sad'}
    for path in assignments:
        parent = Path(path).parent
        while parent != Path('/'):
            directories.add(parent.as_posix())
            parent = parent.parent
    return sorted(directories, key=lambda directory: (directory.count('/'), directory))


def _populate_required_device_nodes(image: bytearray, filesystem: Any, conf_roots: list[Path]) -> None:
    assignments = _load_kernel_device_assignments(conf_roots)
    for directory in _required_device_directories(assignments):
        _ensure_ufs_directory(image, filesystem, directory)
    for path, (file_type, major, minor) in assignments.items():
        try:
            create_ufs_special_file(
                image,
                filesystem,
                path,
                file_type=file_type,
                major=major,
                minor=minor,
                mode=0o600,
                parent_inode_number=UFS_ROOT_INODE if path.count('/') == 1 else None,
                recompute_summary=False,
            )
        except SystemExit as error:
            if 'already exists inside the ufs filesystem' not in str(error):
                raise
    try:
        link_ufs_path(image, filesystem, '/dev/syscon', '/dev/systty')
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
    disk_addressing: str,
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
        disk_addressing=disk_addressing,
    )


def _same_vtoc_partition(left: Any, right: VtocPartition) -> bool:
    return (
        int(left.index) == right.index
        and int(left.tag) == right.tag
        and int(left.flag) == right.flag
        and int(left.start_sector) == right.start_sector
        and int(left.sector_count) == right.sector_count
    )


def validate_existing_image_for_reuse(
    image_path: Path,
    *,
    geometry: RawDiskGeometry,
    unix_partition_start: int,
    unix_partition_size: int,
    slices: list[VtocPartition],
    disk_addressing: str,
) -> tuple[bool, str]:
    if not image_path.exists():
        return False, 'image does not exist'
    expected_size = geometry.total_sectors * SECTOR_SIZE
    if image_path.stat().st_size != expected_size:
        return False, f'image size differs ({image_path.stat().st_size} != {expected_size})'
    expected_mbr = build_mbr(
        geometry,
        unix_partition_start,
        unix_partition_size,
        boot_code=ACTIVE_PARTITION_CHAINLOADER_MBR,
        disk_addressing=disk_addressing,
    )
    if read_sector(image_path, 0) != expected_mbr:
        return False, 'MBR differs from requested layout'
    try:
        report = inspect_disk_metadata(image_path)
    except BaseException as error:
        return False, f'could not inspect existing image: {error}'
    if report.notes:
        return False, '; '.join(report.notes)
    if report.active_unix_partition is None:
        return False, 'missing active UNIX partition'
    if report.active_unix_partition.start_lba != unix_partition_start:
        return False, 'UNIX partition start differs'
    if report.active_unix_partition.sector_count != unix_partition_size:
        return False, 'UNIX partition size differs'
    if report.pdinfo is None:
        return False, 'missing pdinfo'
    if report.pdinfo.cylinders != geometry.cylinders or report.pdinfo.tracks != geometry.heads or report.pdinfo.sectors != geometry.sectors_per_track:
        return False, 'pdinfo geometry differs'
    if report.pdinfo.logical_sector_0 != unix_partition_start:
        return False, 'pdinfo logical sector zero differs'
    if report.vtoc is None:
        return False, 'missing VTOC'

    existing_by_index = {partition.index: partition for partition in report.vtoc.partitions}
    for expected in slices:
        existing = existing_by_index.get(expected.index)
        if existing is None:
            return False, f'missing expected slice {expected.index}'
        if not _same_vtoc_partition(existing, expected):
            return False, f'slice {expected.index} layout differs'

    stand_slice = _get_layout_slice(slices, 'stand')
    stand_bytes = read_slice_bytes(image_path, stand_slice.start_sector, stand_slice.sector_count)
    if not any(candidate.start_offset == 0 for candidate in detect_bfs(stand_bytes)):
        return False, 'stand slice is not BFS'

    root_slice = _get_layout_slice(slices, 'root')
    root_image = DiskBackedSlice(image_path, root_slice.start_sector * SECTOR_SIZE, root_slice.sector_count * SECTOR_SIZE)
    try:
        if detect_ufs_at_start(root_image) is None:
            return False, 'root slice is not UFS'
    finally:
        root_image.close()

    return True, 'existing image layout and filesystems match'


def create_or_recreate_image_layout(
    image_path: Path,
    *,
    geometry: RawDiskGeometry,
    unix_partition_start: int,
    unix_partition_size: int,
    slices: list[VtocPartition],
    disk_addressing: str,
    hdboot_partition_bootstrap: bytes,
) -> None:
    _prepare_base_image(
        image_path,
        reuse_existing=False,
        geometry=geometry,
        unix_partition_start=unix_partition_start,
        unix_partition_size=unix_partition_size,
        slices=slices,
        disk_addressing=disk_addressing,
    )
    _write_slice_bytes(image_path, unix_partition_start, hdboot_partition_bootstrap)


def format_stand_slice(image_path: Path, slices: list[VtocPartition], boot_files: list[tuple[str, bytes]]) -> None:
    stand_slice = _get_layout_slice(slices, 'stand')
    stand_slice_bytes = bytearray(read_slice_bytes(image_path, stand_slice.start_sector, stand_slice.sector_count))
    format_bfs_filesystem(stand_slice_bytes, boot_files)
    _write_slice_bytes(image_path, stand_slice.start_sector, stand_slice_bytes)


def format_root_slice(
    image_path: Path,
    slices: list[VtocPartition],
    *,
    timestamp: int,
    ufs_bytes_per_inode: int,
    tracks_per_cylinder: int,
    sectors_per_track: int,
) -> None:
    root_slice = _get_layout_slice(slices, 'root')
    root_image = DiskBackedSlice(image_path, root_slice.start_sector * SECTOR_SIZE, root_slice.sector_count * SECTOR_SIZE)
    try:
        format_ufs_filesystem(
            root_image,
            timestamp=timestamp,
            block_size=4096,
            bytes_per_inode=ufs_bytes_per_inode,
            tracks_per_cylinder=tracks_per_cylinder,
            sectors_per_track=sectors_per_track,
        )
    finally:
        root_image.close()


@contextmanager
def mount_slice(image_path: Path, slice_selector: str, filesystem: str, *, bulk_populate: bool = False):
    with tempfile.TemporaryDirectory(prefix=f'svr4-{filesystem}-{slice_selector}-', ignore_cleanup_errors=True) as mount_dir:
        mount_path = Path(mount_dir)
        script_name = 'ufs_mount.py' if filesystem == 'ufs' else 'bfs_mount.py'
        command = [
            sys.executable,
            str(HOST_TOOLS_ROOT / script_name),
            str(image_path),
            str(mount_path),
            '--slice',
            slice_selector,
            '--cache-timeout',
            '0',
            '--no-default-permissions',
        ]
        # UFS population writes thousands of files; deferring fsync to unmount
        # avoids a per-file disk barrier. The final close still fsyncs, so the
        # image is durable once the build completes. (bfs_mount has no such
        # flag; the /stand slice is tiny.)
        if bulk_populate and filesystem == 'ufs':
            command.append('--bulk-populate')
        process = subprocess.Popen(command, start_new_session=True)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SystemExit(f'error: failed to mount {filesystem} slice {slice_selector}')
            if _is_mounted(mount_path):
                break
            time.sleep(0.05)
        else:
            process.terminate()
            raise SystemExit(f'error: timed out mounting {filesystem} slice {slice_selector}')
        try:
            yield mount_path
        finally:
            for unmount_command in (
                ['fusermount3', '-u', str(mount_path)],
                ['fusermount', '-u', str(mount_path)],
                ['fusermount3', '-uz', str(mount_path)],
                ['fusermount', '-uz', str(mount_path)],
            ):
                try:
                    subprocess.run(unmount_command, check=False)
                except FileNotFoundError:
                    pass
                if process.poll() is not None or not _is_mounted(mount_path):
                    break
            try:
                _wait_ignoring_sigint(process, timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    _wait_ignoring_sigint(process, timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _wait_ignoring_sigint(process, timeout=5)


def _is_mounted(path: Path) -> bool:
    if os.path.ismount(path):
        return True
    try:
        result = subprocess.run(
            ['findmnt', '--mountpoint', str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _run_rsync(command: list[str]) -> None:
    try:
        process = subprocess.Popen(command)
        try:
            returncode = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                _wait_ignoring_sigint(process, timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                _wait_ignoring_sigint(process, timeout=5)
            raise
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command)
    except FileNotFoundError as error:
        raise SystemExit('error: rsync is required for HDD image population') from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(f'error: rsync failed with exit status {error.returncode}') from error


def _rsync_common_args() -> list[str]:
    return [
        'rsync',
        '-aH',
        '--numeric-ids',
        '--delete',
        '--inplace',
        '--whole-file',
        '--human-readable',
        '--info=progress2,stats2',
    ]


def _wait_ignoring_sigint(process: subprocess.Popen[Any], *, timeout: float) -> int:
    previous_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        return process.wait(timeout=timeout)
    finally:
        signal.signal(signal.SIGINT, previous_handler)


def sync_stand_with_rsync(sysroot: Path, mount_path: Path) -> None:
    _run_rsync([*_rsync_common_args(), f'{sysroot / "stand"}/', f'{mount_path}/'])


def sync_root_with_rsync(sysroot: Path, mount_path: Path) -> None:
    _run_rsync([*_rsync_common_args(), '--exclude=/stand/***', f'{sysroot}/', f'{mount_path}/'])


def ensure_runtime_dirs_and_device_nodes(image_path: Path, kernel_conf_roots: list[Path]) -> None:
    volume = UFSVolume.open_raw_image(image_path, 'root')
    try:
        _populate_required_runtime_directories(volume.image, volume.filesystem)
        _populate_required_device_nodes(volume.image, volume.filesystem, kernel_conf_roots)
        refresh_ufs_summary_layout(volume.image, volume.filesystem)
    finally:
        volume.close()


def build_image(args: argparse.Namespace) -> None:
    image_path = Path(args.image).resolve()
    sysroot = Path(args.sysroot).resolve()
    explicit_kernel_conf = Path(args.kernel_conf).resolve() if args.kernel_conf else None
    kernel_conf_roots = _kernel_conf_roots(sysroot=sysroot, explicit_kernel_conf=explicit_kernel_conf)
    stand_dir = sysroot / 'stand'

    size_mb = _parse_positive_int(str(args.size), name='size')
    stand_size_mb = _parse_positive_int(str(args.stand_size), name='stand-size')
    swap_size_mb = _parse_positive_int(str(args.swap_size), name='swap-size')
    ufs_bytes_per_inode = _parse_positive_int(str(args.ufs_bytes_per_inode), name='--ufs-bytes-per-inode')
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

    geometry = _build_geometry(size_mb, heads, sectors_per_track, args.disk_addressing)
    unix_partition_start, unix_partition_size, slices = _build_slice_layout(
        geometry,
        stand_start_sector=stand_start_sector,
        stand_size_mb=stand_size_mb,
        swap_size_mb=swap_size_mb,
        root_align_sectors=root_align_sectors,
    )

    force_reformat = args.force_reformat or args.no_reuse_existing
    reused, reuse_reason = (False, 'forced reformat')
    if not force_reformat:
        reused, reuse_reason = validate_existing_image_for_reuse(
            image_path,
            geometry=geometry,
            unix_partition_start=unix_partition_start,
            unix_partition_size=unix_partition_size,
            slices=slices,
            disk_addressing=args.disk_addressing,
        )

    if reused:
        _write_slice_bytes(image_path, unix_partition_start, hdboot_partition_bootstrap)
        print(f'Reusing existing SVR4 image at {image_path}: {reuse_reason}')
    else:
        print(f'Recreating SVR4 image at {image_path}: {reuse_reason}')
        create_or_recreate_image_layout(
            image_path,
            geometry=geometry,
            unix_partition_start=unix_partition_start,
            unix_partition_size=unix_partition_size,
            slices=slices,
            disk_addressing=args.disk_addressing,
            hdboot_partition_bootstrap=hdboot_partition_bootstrap,
        )
        format_stand_slice(image_path, slices, boot_files)
        format_root_slice(
            image_path,
            slices,
            timestamp=int(time.time()),
            ufs_bytes_per_inode=ufs_bytes_per_inode,
            tracks_per_cylinder=geometry.heads,
            sectors_per_track=geometry.sectors_per_track,
        )

    with mount_slice(image_path, 'stand', 'bfs') as stand_mount:
        sync_stand_with_rsync(sysroot, stand_mount)
    with mount_slice(image_path, 'root', 'ufs', bulk_populate=True) as root_mount:
        sync_root_with_rsync(sysroot, root_mount)
    ensure_runtime_dirs_and_device_nodes(image_path, kernel_conf_roots)

    missing_note = '' if not missing_boot_files else f' Missing boot files: {", ".join(missing_boot_files)}.'
    path_note = 'reused existing image via rsync' if reused else 'recreated image and populated via rsync'
    print(f'Built SVR4 image at {image_path} ({path_note}).{missing_note}')

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    build_image(args)

if __name__ == '__main__':
    main()
