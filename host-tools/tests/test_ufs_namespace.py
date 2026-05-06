from __future__ import annotations

import unittest

from host_tools.fs.common import FilesystemCandidate
from host_tools.fs.ufs import UFS_CG_CS_NDIR_OFFSET
from host_tools.fs.ufs import UFS_CG_CS_NBFREE_OFFSET
from host_tools.fs.ufs import UFS_CG_CS_NIFREE_OFFSET
from host_tools.fs.ufs import UFS_CG_IUSED_OFFSET
from host_tools.fs.ufs import UFS_CG_MAGIC
from host_tools.fs.ufs import UFS_CG_MAGIC_OFFSET
from host_tools.fs.ufs import UFS_CG_NDBLK_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NDIR_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NBFREE_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NIFREE_OFFSET
from host_tools.fs.ufs import UFS_IFDIR
from host_tools.fs.ufs import UFS_IFLNK
from host_tools.fs.ufs import UFS_ROOT_INODE
from host_tools.fs.ufs import apply_ufs_inode_replacement
from host_tools.fs.ufs import build_ufs_directory_block
from host_tools.fs.ufs import create_ufs_file
from host_tools.fs.ufs import initialize_ufs_inode
from host_tools.fs.ufs import link_ufs_path
from host_tools.fs.ufs import make_ufs_directory
from host_tools.fs.ufs import read_ufs_inode
from host_tools.fs.ufs import read_ufs_path_bytes
from host_tools.fs.ufs import rename_ufs_path
from host_tools.fs.ufs import remove_ufs_directory
from host_tools.fs.ufs import resolve_ufs_path
from host_tools.fs.ufs import symlink_ufs_path
from host_tools.fs.ufs import unlink_ufs_path
from host_tools.fs.ufs_backend import UFSBackend


def build_test_filesystem() -> tuple[bytearray, FilesystemCandidate]:
    image = bytearray(1024 * 1024)
    filesystem = FilesystemCandidate(
        kind='ufs',
        start_offset=0,
        super_offset=0,
        block_size=4096,
        details={
            'ipg': 16,
            'inopb': 32,
            'fragshift': 3,
            'frag': 8,
            'fsize': 512,
            'fpg': 128,
            'ncg': 1,
            'cgoffset': 0,
            'cgmask': 0,
            'cblkno': 1,
            'iblkno': 2,
            'dblkno': 3,
            'fsbtodb': 3,
            'bsize': 4096,
            'nindir': 1024,
        },
    )
    image[UFS_FS_CSTOTAL_NDIR_OFFSET:UFS_FS_CSTOTAL_NDIR_OFFSET + 4] = (1).to_bytes(4, 'little')
    image[UFS_FS_CSTOTAL_NBFREE_OFFSET:UFS_FS_CSTOTAL_NBFREE_OFFSET + 4] = (64).to_bytes(4, 'little')
    image[UFS_FS_CSTOTAL_NIFREE_OFFSET:UFS_FS_CSTOTAL_NIFREE_OFFSET + 4] = (13).to_bytes(4, 'little')

    cg_offset = 4096
    image[cg_offset + UFS_CG_MAGIC_OFFSET:cg_offset + UFS_CG_MAGIC_OFFSET + 4] = UFS_CG_MAGIC.to_bytes(4, 'little')
    image[cg_offset + UFS_CG_NDBLK_OFFSET:cg_offset + UFS_CG_NDBLK_OFFSET + 4] = (64).to_bytes(4, 'little')
    image[cg_offset + UFS_CG_CS_NDIR_OFFSET:cg_offset + UFS_CG_CS_NDIR_OFFSET + 4] = (1).to_bytes(4, 'little')
    image[cg_offset + UFS_CG_CS_NBFREE_OFFSET:cg_offset + UFS_CG_CS_NBFREE_OFFSET + 4] = (64).to_bytes(4, 'little')
    image[cg_offset + UFS_CG_CS_NIFREE_OFFSET:cg_offset + UFS_CG_CS_NIFREE_OFFSET + 4] = (13).to_bytes(4, 'little')
    image[cg_offset + UFS_CG_IUSED_OFFSET] = 0b00000111
    for index in range(8):
        image[cg_offset + UFS_CG_MAGIC_OFFSET + 4 + index] = 0xFF

    initialize_ufs_inode(image, filesystem, UFS_ROOT_INODE, UFS_IFDIR | 0o755, nlink=2)
    root_inode = read_ufs_inode(bytes(image), filesystem.start_offset, filesystem.details, UFS_ROOT_INODE)
    assert root_inode is not None
    apply_ufs_inode_replacement(
        image,
        filesystem,
        UFS_ROOT_INODE,
        root_inode,
        build_ufs_directory_block(UFS_ROOT_INODE, UFS_ROOT_INODE),
        target_path='/',
    )
    return image, filesystem


class UFSNamespaceTests(unittest.TestCase):
    def test_create_and_unlink_file(self) -> None:
        image, filesystem = build_test_filesystem()
        create_ufs_file(image, filesystem, '/hello.txt', b'hello world')
        _, _, data = read_ufs_path_bytes(bytes(image), filesystem, '/hello.txt')
        self.assertEqual(data, b'hello world')
        unlink_ufs_path(image, filesystem, '/hello.txt')
        self.assertIsNone(resolve_ufs_path(bytes(image), filesystem, '/hello.txt'))

    def test_mkdir_and_rmdir(self) -> None:
        image, filesystem = build_test_filesystem()
        make_ufs_directory(image, filesystem, '/etc')
        self.assertIsNotNone(resolve_ufs_path(bytes(image), filesystem, '/etc'))
        remove_ufs_directory(image, filesystem, '/etc')
        self.assertIsNone(resolve_ufs_path(bytes(image), filesystem, '/etc'))

    def test_nested_create_inside_new_directory(self) -> None:
        image, filesystem = build_test_filesystem()
        make_ufs_directory(image, filesystem, '/etc')
        create_ufs_file(image, filesystem, '/etc/rc.local', b'exit 0\n')
        _, _, data = read_ufs_path_bytes(bytes(image), filesystem, '/etc/rc.local')
        self.assertEqual(data, b'exit 0\n')

    def test_link_rename_and_symlink(self) -> None:
        image, filesystem = build_test_filesystem()
        create_ufs_file(image, filesystem, '/hello.txt', b'hello world')
        hello_inode_number, hello_inode, hello_data = read_ufs_path_bytes(bytes(image), filesystem, '/hello.txt')
        self.assertEqual(hello_data, b'hello world')
        self.assertEqual(int(hello_inode['blocks']), 1)
        link_ufs_path(image, filesystem, '/hello.txt', '/hello.link')
        linked_inode_number, _, linked_data = read_ufs_path_bytes(bytes(image), filesystem, '/hello.link')
        self.assertEqual(linked_inode_number, hello_inode_number)
        self.assertEqual(linked_data, b'hello world')
        rename_ufs_path(image, filesystem, '/hello.link', '/renamed.txt')
        self.assertIsNone(resolve_ufs_path(bytes(image), filesystem, '/hello.link'))
        self.assertEqual(read_ufs_path_bytes(bytes(image), filesystem, '/renamed.txt')[2], b'hello world')
        symlink_ufs_path(image, filesystem, '/renamed.txt', '/hello.symlink')
        _, symlink_inode, symlink_data = read_ufs_path_bytes(bytes(image), filesystem, '/hello.symlink')
        self.assertEqual(symlink_data, b'/renamed.txt')
        self.assertEqual(int(symlink_inode['mode']) & 0o170000, UFS_IFLNK)

    def test_backend_wrapper(self) -> None:
        image, filesystem = build_test_filesystem()
        backend = UFSBackend(image, filesystem)
        backend.create('/boot.rc', b'boot=yes\n')
        self.assertEqual(backend.read('/boot.rc'), b'boot=yes\n')
        backend.mkdir('/etc')
        backend.rename('/boot.rc', '/etc/boot.rc')
        self.assertEqual(backend.read('/etc/boot.rc'), b'boot=yes\n')
        backend.symlink('/etc/boot.rc', '/boot.link')
        self.assertEqual(backend.readlink('/boot.link'), '/etc/boot.rc')


if __name__ == '__main__':
    unittest.main()