from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from host_tools.disk.inspect import inspect_slice_by_selector


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _binary_path(root: Path) -> Path:
    return root / 'build' / 'original-ufs-fsck' / 'fsck-original-host'


def _source_paths(root: Path) -> list[Path]:
    port = root / 'host-tools' / 'original-ufs-fsck'
    return [
        port / 'host_main.c',
        port / 'host_setup.c',
        port / 'host_runtime.c',
        port / 'host_cli.c',
        port / 'host_frag.c',
        port / 'host_stubs.c',
        port / 'dir.c',
        port / 'inode.c',
        port / 'pass1.c',
        port / 'pass1b.c',
        port / 'pass2.c',
        port / 'pass3.c',
        port / 'pass4.c',
        port / 'pass5.c',
        port / 'utilities.c',
        root / 'uts' / 'i386' / 'fs' / 'ufs' / 'ufs_tables.c',
    ]


def _needs_rebuild(binary_path: Path, sources: list[Path]) -> bool:
    if not binary_path.exists():
        return True
    binary_mtime = binary_path.stat().st_mtime
    return any(source.stat().st_mtime > binary_mtime for source in sources)


def _build_binary(root: Path) -> Path:
    binary_path = _binary_path(root)
    sources = _source_paths(root)
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    if not _needs_rebuild(binary_path, sources):
        return binary_path

    port = root / 'host-tools' / 'original-ufs-fsck'
    command = [
        'cc',
        '-m32',
        '-std=gnu89',
        '-fcommon',
        '-Wno-implicit-int',
        '-Wno-implicit-function-declaration',
        '-Wno-return-type',
        '-Wno-int-conversion',
        '-I' + str(port / 'compat'),
        '-I' + str(port),
        '-I' + str(root / 'uts' / 'i386'),
        '-include',
        str(port / 'host_compat.h'),
        '-o',
        str(binary_path),
        *[str(source) for source in sources],
    ]
    subprocess.run(command, cwd=root, check=True)
    return binary_path


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the recovered original SVR4 UFS fsck logic against a selected slice in a disk image.')
    parser.add_argument('image', type=Path)
    parser.add_argument('--slice', default='1', help='Slice index or tag name, for example 1 or root.')
    parser.add_argument('--write', action='store_true', help='Allow the original fsck port to write repairs back to the image.')
    parser.add_argument('--yes', action='store_true', help='Answer yes to fixes when write mode is enabled.')
    parser.add_argument('--preen', action='store_true', help='Enable preen mode.')
    parser.add_argument('--debug', action='store_true', help='Enable original fsck debug output.')
    parser.add_argument('--trace-inode', type=int, help='Trace reads associated with a specific inode number.')
    parser.add_argument('--trace-sector', type=int, help='Trace reads of a specific slice-relative disk sector.')
    args = parser.parse_args()

    root = _repo_root()
    binary_path = _build_binary(root)
    _, slice_fs = inspect_slice_by_selector(args.image.resolve(), args.slice)
    command = [
        str(binary_path),
        '--offset-sectors',
        str(slice_fs.absolute_start_sector),
    ]
    if args.write:
        command.append('--write')
    else:
        command.append('--no')
    if args.yes:
        command.append('--yes')
    if args.preen:
        command.append('--preen')
    if args.debug:
        command.append('--debug')
    if args.trace_inode is not None:
        command.extend(['--trace-inode', str(args.trace_inode)])
    if args.trace_sector is not None:
        command.extend(['--trace-sector', str(args.trace_sector)])
    command.append(str(args.image.resolve()))
    completed = subprocess.run(command, cwd=root)
    return int(completed.returncode)


if __name__ == '__main__':
    raise SystemExit(main())