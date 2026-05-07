from __future__ import annotations

import unittest
from unittest import mock

from host_tools.fs.common import FilesystemCandidate
from host_tools.fs.ufs import UFS_CG_CS_NDIR_OFFSET
from host_tools.fs.ufs import UFS_CG_CS_NBFREE_OFFSET
from host_tools.fs.ufs import UFS_CG_CS_NFFREE_OFFSET
from host_tools.fs.ufs import UFS_CG_CS_NIFREE_OFFSET
from host_tools.fs.ufs import UFS_CG_FREE_OFFSET
from host_tools.fs.ufs import UFS_CG_IUSED_OFFSET
from host_tools.fs.ufs import UFS_CG_MAGIC
from host_tools.fs.ufs import UFS_CG_MAGIC_OFFSET
from host_tools.fs.ufs import UFS_CG_NDBLK_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NDIR_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NBFREE_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NFFREE_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NIFREE_OFFSET
from host_tools.fs.ufs import UFS_IFDIR
from host_tools.fs.ufs import UFS_IFLNK
from host_tools.fs.ufs import UFS_ROOT_INODE
from host_tools.fs.ufs import apply_ufs_inode_replacement
from host_tools.fs.ufs import build_ufs_directory_block
from host_tools.fs.ufs import create_ufs_file
from host_tools.fs.ufs import initialize_ufs_inode
from host_tools.fs.ufs import is_frag_free
from host_tools.fs.ufs import link_ufs_path
from host_tools.fs.ufs import make_ufs_directory
from host_tools.fs.ufs import read_cg_block
from host_tools.fs.ufs import read_ufs_inode
from host_tools.fs.ufs import read_ufs_path_bytes
from host_tools.fs.ufs import rename_ufs_path
from host_tools.fs.ufs import remove_ufs_directory
from host_tools.fs.ufs import resolve_ufs_path
from host_tools.fs.ufs import symlink_ufs_path
from host_tools.fs.ufs import unlink_ufs_path
import host_tools.fs.ufs as ufs_module
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


def build_multicg_test_filesystem_with_pristine_second_group() -> tuple[bytearray, FilesystemCandidate]:
    image = bytearray(256 * 1024)
    filesystem = FilesystemCandidate(
        kind='ufs',
        start_offset=0,
        super_offset=0,
        block_size=4096,
        details={
            'ipg': 32,
            'inopb': 32,
            'fragshift': 2,
            'frag': 4,
            'fsize': 1024,
            'fpg': 64,
            'dsize': 128,
            'ncg': 2,
            'cgoffset': 0,
            'cgmask': 0,
            'cblkno': 1,
            'iblkno': 2,
            'dblkno': 8,
            'fsbtodb': 1,
            'bsize': 4096,
            'nindir': 1024,
        },
    )
    image[UFS_FS_CSTOTAL_NDIR_OFFSET:UFS_FS_CSTOTAL_NDIR_OFFSET + 4] = (1).to_bytes(4, 'little')
    image[UFS_FS_CSTOTAL_NBFREE_OFFSET:UFS_FS_CSTOTAL_NBFREE_OFFSET + 4] = (28).to_bytes(4, 'little')
    image[UFS_FS_CSTOTAL_NIFREE_OFFSET:UFS_FS_CSTOTAL_NIFREE_OFFSET + 4] = (29 + 32).to_bytes(4, 'little')

    cg0_offset = 1024
    image[cg0_offset + UFS_CG_MAGIC_OFFSET:cg0_offset + UFS_CG_MAGIC_OFFSET + 4] = UFS_CG_MAGIC.to_bytes(4, 'little')
    image[cg0_offset + UFS_CG_NDBLK_OFFSET:cg0_offset + UFS_CG_NDBLK_OFFSET + 4] = (64).to_bytes(4, 'little')
    image[cg0_offset + UFS_CG_CS_NDIR_OFFSET:cg0_offset + UFS_CG_CS_NDIR_OFFSET + 4] = (1).to_bytes(4, 'little')
    image[cg0_offset + UFS_CG_CS_NBFREE_OFFSET:cg0_offset + UFS_CG_CS_NBFREE_OFFSET + 4] = (14).to_bytes(4, 'little')
    image[cg0_offset + UFS_CG_CS_NIFREE_OFFSET:cg0_offset + UFS_CG_CS_NIFREE_OFFSET + 4] = (29).to_bytes(4, 'little')
    image[cg0_offset + UFS_CG_IUSED_OFFSET] = 0b00000111
    for frag in range(8, 64):
        image[cg0_offset + UFS_CG_FREE_OFFSET + (frag // 8)] |= 1 << (frag % 8)

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
    def test_create_file_mirrors_legacy_mode_field(self) -> None:
        image, filesystem = build_test_filesystem()

        create_ufs_file(image, filesystem, '/hello.txt', b'hello world')

        inode_number, inode, _ = read_ufs_path_bytes(bytes(image), filesystem, '/hello.txt')
        inode_offset = ufs_module.ufs_inode_offset(filesystem, inode_number)
        legacy_mode = int.from_bytes(image[inode_offset:inode_offset + 2], 'little', signed=False)

        self.assertEqual(legacy_mode, int(inode['mode']) & 0xFFFF)

    def test_create_and_unlink_file(self) -> None:
        image, filesystem = build_test_filesystem()
        create_ufs_file(image, filesystem, '/hello.txt', b'hello world')
        inode_number, _, _ = read_ufs_path_bytes(bytes(image), filesystem, '/hello.txt')
        _, _, data = read_ufs_path_bytes(bytes(image), filesystem, '/hello.txt')
        self.assertEqual(data, b'hello world')
        unlink_ufs_path(image, filesystem, '/hello.txt')
        self.assertIsNone(resolve_ufs_path(bytes(image), filesystem, '/hello.txt'))
        inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, inode_number)
        assert inode is not None
        self.assertEqual(int(inode['mode']), 0)
        self.assertEqual(int(inode['size']), 0)
        self.assertEqual(int(inode['blocks']), 0)
        self.assertFalse(any(int(value) for value in inode['direct_blocks']))
        self.assertFalse(any(int(value) for value in inode['indirect_blocks']))

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

    def test_large_file_spills_into_pristine_second_cylinder_group(self) -> None:
        image, filesystem = build_multicg_test_filesystem_with_pristine_second_group()

        payload = b'A' * (20 * 4096)
        create_ufs_file(image, filesystem, '/big.bin', payload)

        _, inode, data = read_ufs_path_bytes(bytes(image), filesystem, '/big.bin')
        self.assertEqual(data, payload)
        self.assertGreater(len(inode['direct_blocks']), 0)

    def test_indirect_tail_allocates_full_block(self) -> None:
        image, filesystem = build_multicg_test_filesystem_with_pristine_second_group()

        payload = b'A' * ((13 * 4096) + 1)
        create_ufs_file(image, filesystem, '/indirect-tail.bin', payload)

        inode_number, inode, data = read_ufs_path_bytes(bytes(image), filesystem, '/indirect-tail.bin')
        self.assertEqual(data, payload)
        self.assertEqual(int(inode['blocks']), 120)

        last_block = int(inode['indirect_blocks'][0])
        pointer_block = ufs_module.read_ufs_pointer_block(bytes(image), filesystem, last_block)
        final_data_block = max(int(block) for block in pointer_block if int(block) != 0)
        cg = final_data_block // int(filesystem.details['fpg'])
        cg_bytes = read_cg_block(image, filesystem, cg)
        cg_relative_frag = final_data_block - (cg * int(filesystem.details['fpg']))
        self.assertTrue(all(not is_frag_free(cg_bytes, cg_relative_frag + frag_index) for frag_index in range(int(filesystem.details['frag']))))

    def test_small_fragment_write_normalizes_metadata_for_all_cylinder_groups(self) -> None:
        image, filesystem = build_multicg_test_filesystem_with_pristine_second_group()

        cg0_offset = ufs_module.cg_block_offset(filesystem, 0)
        cg1_offset = ufs_module.cg_block_offset(filesystem, 1)
        image[cg1_offset:cg1_offset + int(filesystem.details['bsize'])] = b'\0' * int(filesystem.details['bsize'])
        ufs_module._UFS_METADATA_NORMALIZATION_STATE.discard(
            (id(image), filesystem.start_offset, filesystem.super_offset)
        )
        self.assertEqual(ufs_module.u32(image, cg1_offset + UFS_CG_MAGIC_OFFSET), 0)

        create_ufs_file(image, filesystem, '/tiny.bin', b'x')

        self.assertEqual(ufs_module.u32(image, cg1_offset + UFS_CG_MAGIC_OFFSET), UFS_CG_MAGIC)
        self.assertEqual(ufs_module.u32(image, cg0_offset + UFS_CG_CS_NBFREE_OFFSET), 12)
        self.assertEqual(ufs_module.u32(image, cg0_offset + UFS_CG_CS_NFFREE_OFFSET), 6)
        self.assertEqual(ufs_module.u32(image, cg1_offset + UFS_CG_CS_NBFREE_OFFSET), 14)
        self.assertEqual(ufs_module.u32(image, cg1_offset + UFS_CG_CS_NFFREE_OFFSET), 0)
        self.assertEqual(ufs_module.u32(image, UFS_FS_CSTOTAL_NBFREE_OFFSET), 26)
        self.assertEqual(ufs_module.u32(image, UFS_FS_CSTOTAL_NIFREE_OFFSET), 60)
        self.assertEqual(ufs_module.u32(image, UFS_FS_CSTOTAL_NFFREE_OFFSET), 6)

    def test_sequential_writes_do_not_rescan_from_group_start(self) -> None:
        image, filesystem = build_multicg_test_filesystem_with_pristine_second_group()

        created = create_ufs_file(image, filesystem, '/bench.bin', b'')
        inode_number = int(created['inode'])
        frag_checks = 0
        original_is_frag_free = ufs_module.is_frag_free

        def counting_is_frag_free(cg_bytes: bytes, frag_index: int) -> bool:
            nonlocal frag_checks
            frag_checks += 1
            return original_is_frag_free(cg_bytes, frag_index)

        with mock.patch.object(ufs_module, 'is_frag_free', side_effect=counting_is_frag_free):
            for write_index in range(20):
                inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, inode_number)
                assert inode is not None
                ufs_module.apply_ufs_inode_write(
                    image,
                    filesystem,
                    inode_number,
                    inode,
                    write_index * 4096,
                    b'x' * 4096,
                    target_path='/bench.bin',
                )

        self.assertLess(frag_checks, 200)

    def test_large_append_batches_pointer_block_updates(self) -> None:
        image, filesystem = build_multicg_test_filesystem_with_pristine_second_group()

        created = create_ufs_file(image, filesystem, '/bench.bin', b'')
        inode_number = int(created['inode'])
        inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, inode_number)
        assert inode is not None
        counts = {'read_pointer_block': 0, 'write_pointer_block': 0}
        original_read_pointer_block = ufs_module.read_ufs_pointer_block
        original_write_pointer_block = ufs_module.write_ufs_pointer_block

        def counting_read_pointer_block(*args: object, **kwargs: object) -> list[int]:
            counts['read_pointer_block'] += 1
            return original_read_pointer_block(*args, **kwargs)

        def counting_write_pointer_block(*args: object, **kwargs: object) -> None:
            counts['write_pointer_block'] += 1
            original_write_pointer_block(*args, **kwargs)

        with mock.patch.object(ufs_module, 'read_ufs_pointer_block', side_effect=counting_read_pointer_block), mock.patch.object(ufs_module, 'write_ufs_pointer_block', side_effect=counting_write_pointer_block):
            ufs_module.apply_ufs_inode_write(
                image,
                filesystem,
                inode_number,
                inode,
                0,
                b'x' * (20 * 4096),
                target_path='/bench.bin',
            )

        self.assertLessEqual(counts['read_pointer_block'], 1)
        self.assertLessEqual(counts['write_pointer_block'], 2)

    def test_backend_wrapper(self) -> None:
        image, filesystem = build_test_filesystem()
        backend = UFSBackend(image, filesystem)
        backend.create('/boot.rc', b'boot=yes\n')
        self.assertEqual(backend.read('/boot.rc', 0, 9), b'boot=yes\n')
        backend.mkdir('/etc')
        backend.rename('/boot.rc', '/etc/boot.rc')
        self.assertEqual(backend.read('/etc/boot.rc', 0, 9), b'boot=yes\n')
        backend.symlink('/etc/boot.rc', '/boot.link')
        self.assertEqual(backend.readlink('/boot.link'), '/etc/boot.rc')


if __name__ == '__main__':
    unittest.main()