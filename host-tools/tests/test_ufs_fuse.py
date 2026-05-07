from __future__ import annotations

import errno
import os
import stat
import unittest
from unittest import mock

import pyfuse3
import trio

from host_tools.fs.common import UFS_NDADDR
from host_tools.fs.ufs import read_ufs_inode
from host_tools.fs.ufs import read_ufs_pointer_block
from host_tools.fs.ufs import resolve_ufs_path
from host_tools.fs.ufs import ufs_allocation_byte_sizes
from host_tools.fs.ufs import ufs_cgbase
from host_tools.fs.ufs import ufs_cgdmin
from host_tools.fs.ufs import ufs_inode_data_blocks
from host_tools.fs.ufs_fuse import UFSOperations, UFSVolume, make_test_context
from test_ufs_namespace import build_multicg_test_filesystem_with_pristine_second_group, build_test_filesystem


def _assert_matches_original_fsck_inode_rules(
    testcase: unittest.TestCase,
    image: bytes | bytearray,
    filesystem: object,
    inode_number: int,
) -> None:
    inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, inode_number)
    testcase.assertIsNotNone(inode)
    assert inode is not None

    fs = filesystem.details
    block_size = int(fs['bsize'])
    fragment_size = int(fs['fsize'])
    fragments_per_block = int(fs['frag'])
    indirect_count = int(fs['nindir'])
    needed_blocks = 0 if int(inode['size']) == 0 else (int(inode['size']) + block_size - 1) // block_size
    data_blocks = ufs_inode_data_blocks(image, filesystem, inode)
    allocation_sizes = ufs_allocation_byte_sizes(fs, int(inode['size']))
    direct_blocks = [int(block) for block in inode['direct_blocks']]
    indirect_roots = [int(block) for block in inode['indirect_blocks']]
    fs_size = int(fs.get('size', fs.get('dsize', int(fs['fpg']) * int(fs['ncg']))))

    def dtog(block_number: int) -> int:
        return block_number // int(fs['fpg'])

    def outrange(block_number: int, fragment_count: int) -> bool:
        if block_number + fragment_count > fs_size:
            return True
        cylinder_group = dtog(block_number)
        if block_number < ufs_cgdmin(fs, cylinder_group):
            return (block_number + fragment_count) > ufs_cgbase(fs, cylinder_group)
        return (block_number + fragment_count) > ufs_cgbase(fs, cylinder_group + 1)

    for index, block_number in enumerate(data_blocks):
        testcase.assertFalse(
            outrange(block_number, allocation_sizes[index] // fragment_size),
            msg=f'data block {block_number} is out of range for inode {inode_number}',
        )

    for index in range(min(needed_blocks, UFS_NDADDR), UFS_NDADDR):
        testcase.assertEqual(direct_blocks[index], 0, msg=f'unexpected direct pointer {index} in inode {inode_number}')

    remaining_blocks = needed_blocks - UFS_NDADDR
    roots_needed = 0
    while remaining_blocks > 0:
        roots_needed += 1
        remaining_blocks //= indirect_count
    for index in range(roots_needed, len(indirect_roots)):
        testcase.assertEqual(indirect_roots[index], 0, msg=f'unexpected indirect root {index} in inode {inode_number}')

    flattened_indirect_data: list[int] = []

    def validate_indirect(root_block: int, level: int, size_remaining: int, label: str) -> None:
        testcase.assertFalse(
            outrange(root_block, fragments_per_block),
            msg=f'indirect block {root_block} ({label}) is out of range for inode {inode_number}',
        )
        pointers = read_ufs_pointer_block(image, filesystem, root_block)
        size_per_pointer = block_size
        for _ in range(level - 1):
            size_per_pointer *= indirect_count
        pointers_needed = min(indirect_count, max(0, (size_remaining // size_per_pointer) + 1))
        for pointer in pointers[pointers_needed:]:
            testcase.assertEqual(pointer, 0, msg=f'nonzero trailing indirect pointer in {label} for inode {inode_number}')
        for index, pointer in enumerate(pointers[:pointers_needed], start=1):
            if pointer == 0:
                continue
            if level > 1:
                validate_indirect(int(pointer), level - 1, size_remaining - (index * size_per_pointer), f'{label}.{index}')
            else:
                flattened_indirect_data.append(int(pointer))

    indirect_size_remaining = int(inode['size']) - (UFS_NDADDR * block_size)
    for level, root_block in enumerate(indirect_roots, start=1):
        if root_block == 0:
            continue
        validate_indirect(root_block, level, indirect_size_remaining, f'ib{level}')

    testcase.assertEqual(flattened_indirect_data, data_blocks[UFS_NDADDR:])


class UFSFuseFrontendTests(unittest.TestCase):
    def build_operations(self) -> tuple[UFSOperations, list[tuple[list[tuple[int, int]], bool]]]:
        return self.build_operations_with_fixture(build_test_filesystem)

    def build_operations_with_fixture(self, builder: object) -> tuple[UFSOperations, list[tuple[list[tuple[int, int]], bool]]]:
        image, filesystem = builder()
        flushes: list[tuple[list[tuple[int, int]], bool]] = []
        volume = UFSVolume(
            image=image,
            filesystem=filesystem,
            sector_count=len(image) // 512,
            flush_callback=lambda data, ranges, sync: flushes.append((list(ranges), sync)),
        )
        return UFSOperations(volume), flushes

    def test_create_write_lookup_and_setattr(self) -> None:
        async def scenario() -> None:
            operations, flushes = self.build_operations()
            ctx = make_test_context(uid=1000, gid=100, umask=0o022)

            file_info, created = await operations.create(pyfuse3.ROOT_INODE, b'hello.txt', 0o666, os.O_RDWR, ctx)
            self.assertEqual(created.st_size, 0)
            self.assertGreaterEqual(len(flushes), 1)

            bytes_written = await operations.write(file_info.fh, 0, b'hello world')
            self.assertEqual(bytes_written, 11)
            self.assertEqual(len(flushes), 1)

            data = await operations.read(file_info.fh, 0, 32)
            self.assertEqual(data, b'hello world')

            looked_up = await operations.lookup(pyfuse3.ROOT_INODE, b'hello.txt', ctx)
            self.assertEqual(looked_up.st_size, 11)
            self.assertEqual(looked_up.st_uid, 1000)
            self.assertEqual(looked_up.st_gid, 100)

            updated = pyfuse3.EntryAttributes()
            updated.st_size = 5
            updated.st_mode = looked_up.st_mode
            updated.st_uid = looked_up.st_uid
            updated.st_gid = looked_up.st_gid
            updated.st_atime_ns = looked_up.st_atime_ns
            updated.st_mtime_ns = looked_up.st_mtime_ns
            updated.st_ctime_ns = looked_up.st_ctime_ns
            fields = type(
                'Fields',
                (),
                {
                    'update_size': True,
                    'update_mode': False,
                    'update_uid': False,
                    'update_gid': False,
                    'update_atime': False,
                    'update_mtime': False,
                    'update_ctime': False,
                },
            )()
            shrunk = await operations.setattr(pyfuse3.InodeT(looked_up.st_ino), updated, fields, None, ctx)
            self.assertEqual(shrunk.st_size, 5)

            truncated = await operations.read(file_info.fh, 0, 32)
            self.assertEqual(truncated, b'hello')
            await operations.release(file_info.fh)
            self.assertGreaterEqual(len(flushes), 2)

        trio.run(scenario)

    def test_multiple_writes_flush_on_release_not_each_write(self) -> None:
        async def scenario() -> None:
            operations, flushes = self.build_operations()
            ctx = make_test_context(uid=1000, gid=100, umask=0o022)

            file_info, _ = await operations.create(pyfuse3.ROOT_INODE, b'batched.bin', 0o666, os.O_RDWR, ctx)
            baseline_flushes = len(flushes)

            self.assertEqual(await operations.write(file_info.fh, 0, b'A' * 4096), 4096)
            self.assertEqual(await operations.write(file_info.fh, 4096, b'B' * 4096), 4096)
            self.assertEqual(len(flushes), baseline_flushes)

            await operations.release(file_info.fh)
            self.assertEqual(len(flushes), baseline_flushes + 1)
            self.assertTrue(flushes[-1][1])

        trio.run(scenario)

    def test_flush_writes_dirty_ranges_not_whole_slice(self) -> None:
        async def scenario() -> None:
            operations, flushes = self.build_operations()
            ctx = make_test_context(uid=1000, gid=100, umask=0o022)

            file_info, _ = await operations.create(pyfuse3.ROOT_INODE, b'ranged.bin', 0o666, os.O_RDWR, ctx)
            await operations.write(file_info.fh, 0, b'payload')
            await operations.release(file_info.fh)

            ranges, sync = flushes[-1]
            self.assertTrue(sync)
            self.assertTrue(ranges)
            total_dirty = sum(end - start for start, end in ranges)
            self.assertLess(total_dirty, len(operations._volume.image))

        trio.run(scenario)

    def test_block_aligned_append_avoids_full_replacement(self) -> None:
        async def scenario() -> None:
            operations, _ = self.build_operations()
            ctx = make_test_context(uid=1000, gid=100, umask=0o022)

            file_info, created = await operations.create(pyfuse3.ROOT_INODE, b'append.bin', 0o666, os.O_RDWR, ctx)
            first_block = b'A' * 4096
            second_block = b'B' * 4096

            with mock.patch('host_tools.fs.ufs_fuse.apply_ufs_inode_replacement', side_effect=AssertionError('unexpected full replacement')):
                self.assertEqual(await operations.write(file_info.fh, 0, first_block), len(first_block))
                self.assertEqual(await operations.write(file_info.fh, len(first_block), second_block), len(second_block))

            inode = pyfuse3.InodeT(created.st_ino)
            looked_up = await operations.getattr(inode)
            self.assertEqual(looked_up.st_size, 8192)
            self.assertEqual(await operations.read(file_info.fh, 0, 8192), first_block + second_block)
            await operations.release(file_info.fh)

        trio.run(scenario)

    def test_fragment_growth_and_truncate_avoid_full_file_reads(self) -> None:
        async def scenario() -> None:
            operations, _ = self.build_operations()
            ctx = make_test_context(uid=1000, gid=100, umask=0o022)

            file_info, created = await operations.create(pyfuse3.ROOT_INODE, b'fragment.bin', 0o666, os.O_RDWR, ctx)
            initial_payload = b'C' * 3000
            grown_payload = b'D' * 2000

            self.assertEqual(await operations.write(file_info.fh, 0, initial_payload), len(initial_payload))

            with mock.patch('host_tools.fs.ufs.read_ufs_file', side_effect=AssertionError('unexpected whole-file read')):
                self.assertEqual(await operations.write(file_info.fh, len(initial_payload), grown_payload), len(grown_payload))

                attrs = pyfuse3.EntryAttributes()
                attrs.st_size = 2048
                attrs.st_mode = 0
                attrs.st_uid = 0
                attrs.st_gid = 0
                attrs.st_atime_ns = 0
                attrs.st_mtime_ns = 0
                attrs.st_ctime_ns = 0
                fields = type(
                    'Fields',
                    (),
                    {
                        'update_size': True,
                        'update_mode': False,
                        'update_uid': False,
                        'update_gid': False,
                        'update_atime': False,
                        'update_mtime': False,
                        'update_ctime': False,
                    },
                )()
                shrunk = await operations.setattr(pyfuse3.InodeT(created.st_ino), attrs, fields, None, ctx)

            self.assertEqual(shrunk.st_size, 2048)
            self.assertEqual(await operations.read(file_info.fh, 0, 4096), initial_payload[:2048])
            await operations.release(file_info.fh)

        trio.run(scenario)

    def test_large_indirect_file_matches_original_fsck_rules(self) -> None:
        async def scenario() -> None:
            operations, _ = self.build_operations_with_fixture(build_multicg_test_filesystem_with_pristine_second_group)
            ctx = make_test_context(uid=1000, gid=100, umask=0o022)

            file_info, _ = await operations.create(pyfuse3.ROOT_INODE, b'fsck-large.bin', 0o666, os.O_RDWR, ctx)
            payload = (b'0123456789ABCDEF' * 3328) + (b'XYZ' * 512)

            self.assertEqual(await operations.write(file_info.fh, 0, payload), len(payload))
            await operations.release(file_info.fh)

            resolved = resolve_ufs_path(bytes(operations._volume.image), operations._volume.filesystem, '/fsck-large.bin')
            self.assertIsNotNone(resolved)
            assert resolved is not None
            inode_number, _ = resolved
            _assert_matches_original_fsck_inode_rules(self, operations._volume.image, operations._volume.filesystem, inode_number)

        trio.run(scenario)

    def test_regular_file_read_avoids_full_file_materialization(self) -> None:
        async def scenario() -> None:
            operations, _ = self.build_operations()
            ctx = make_test_context(uid=1000, gid=100, umask=0o022)

            file_info, _ = await operations.create(pyfuse3.ROOT_INODE, b'read.bin', 0o666, os.O_RDWR, ctx)
            payload = (b'0123456789ABCDEF' * 512)
            self.assertEqual(await operations.write(file_info.fh, 0, payload), len(payload))

            with mock.patch('host_tools.fs.ufs.read_ufs_file', side_effect=AssertionError('unexpected whole-file read')):
                chunk = await operations.read(file_info.fh, 128, 64)

            self.assertEqual(chunk, payload[128:192])
            await operations.release(file_info.fh)

        trio.run(scenario)

    def test_directory_rename_link_and_symlink(self) -> None:
        async def scenario() -> None:
            operations, flushes = self.build_operations()
            ctx = make_test_context(uid=0, gid=0, umask=0o022)

            etc_entry = await operations.mkdir(pyfuse3.ROOT_INODE, b'etc', 0o755, ctx)
            self.assertTrue(etc_entry.st_mode & 0o040000)
            file_info, created = await operations.create(pyfuse3.InodeT(etc_entry.st_ino), b'boot.rc', 0o644, os.O_RDWR, ctx)
            await operations.write(file_info.fh, 0, b'boot=yes\n')
            await operations.release(file_info.fh)

            await operations.link(pyfuse3.InodeT(created.st_ino), pyfuse3.ROOT_INODE, b'boot.link', ctx)
            await operations.rename(pyfuse3.ROOT_INODE, b'boot.link', pyfuse3.ROOT_INODE, b'boot.saved', 0, ctx)
            symlink_entry = await operations.symlink(pyfuse3.ROOT_INODE, b'boot.current', b'/boot.saved', ctx)
            target = await operations.readlink(pyfuse3.InodeT(symlink_entry.st_ino), ctx)

            self.assertEqual(target, b'/boot.saved')
            self.assertGreaterEqual(len(flushes), 5)

        trio.run(scenario)

    def test_readdir_pagination_does_not_repeat_names(self) -> None:
        async def scenario() -> None:
            operations, _ = self.build_operations()
            ctx = make_test_context(uid=0, gid=0, umask=0o022)

            for name in [b'alpha', b'beta', b'gamma', b'delta', b'epsilon', b'zeta']:
                file_info, _ = await operations.create(pyfuse3.ROOT_INODE, name, 0o644, os.O_RDWR, ctx)
                await operations.release(file_info.fh)

            fh = await operations.opendir(pyfuse3.ROOT_INODE, ctx)
            first_batch: list[tuple[bytes, int]] = []
            second_batch: list[tuple[bytes, int]] = []

            def first_reply(token: object, name: bytes, attr: pyfuse3.EntryAttributes, next_id: int) -> bool:
                del token, attr
                first_batch.append((name, next_id))
                return len(first_batch) < 4

            with mock.patch('pyfuse3.readdir_reply', side_effect=first_reply):
                await operations.readdir(fh, 0, object())

            self.assertGreaterEqual(len(first_batch), 4)
            resume_from = first_batch[-1][1]

            def second_reply(token: object, name: bytes, attr: pyfuse3.EntryAttributes, next_id: int) -> bool:
                del token, attr
                second_batch.append((name, next_id))
                return True

            with mock.patch('pyfuse3.readdir_reply', side_effect=second_reply):
                await operations.readdir(fh, resume_from, object())

            await operations.releasedir(fh)

            first_names = [name.decode('ascii') for name, _ in first_batch]
            second_names = [name.decode('ascii') for name, _ in second_batch]

            self.assertEqual(len(first_names), len(set(first_names)))
            self.assertEqual(len(second_names), len(set(second_names)))
            self.assertTrue(set(first_names).isdisjoint(second_names))
            self.assertIn('alpha', first_names + second_names)
            self.assertIn('zeta', first_names + second_names)

        trio.run(scenario)

    def test_unlink_is_deferred_until_release_and_forget(self) -> None:
        async def scenario() -> None:
            operations, _ = self.build_operations()
            ctx = make_test_context(uid=0, gid=0, umask=0o022)

            file_info, created = await operations.create(pyfuse3.ROOT_INODE, b'gone.txt', 0o644, os.O_RDWR, ctx)
            await operations.write(file_info.fh, 0, b'still here')
            inode = pyfuse3.InodeT(created.st_ino)

            await operations.unlink(pyfuse3.ROOT_INODE, b'gone.txt', ctx)

            with self.assertRaises(pyfuse3.FUSEError) as lookup_error:
                await operations.lookup(pyfuse3.ROOT_INODE, b'gone.txt', ctx)
            self.assertEqual(lookup_error.exception.errno, errno.ENOENT)

            attrs = await operations.getattr(inode)
            self.assertEqual(attrs.st_nlink, 0)
            data = await operations.read(file_info.fh, 0, 32)
            self.assertEqual(data, b'still here')

            await operations.release(file_info.fh)
            await operations.forget([(inode, 1)])

            with self.assertRaises(pyfuse3.FUSEError) as getattr_error:
                await operations.getattr(inode)
            self.assertEqual(getattr_error.exception.errno, errno.ENOENT)

        trio.run(scenario)

    def test_unsupported_features_return_enosys(self) -> None:
        async def scenario() -> None:
            operations, _ = self.build_operations()
            ctx = make_test_context(uid=0, gid=0, umask=0o022)

            with self.assertRaises(pyfuse3.FUSEError) as getxattr_error:
                await operations.getxattr(pyfuse3.ROOT_INODE, b'user.test', ctx)
            self.assertEqual(getxattr_error.exception.errno, errno.ENOSYS)

            with self.assertRaises(pyfuse3.FUSEError) as listxattr_error:
                await operations.listxattr(pyfuse3.ROOT_INODE, ctx)
            self.assertEqual(listxattr_error.exception.errno, errno.ENOSYS)

            with self.assertRaises(pyfuse3.FUSEError) as setxattr_error:
                await operations.setxattr(pyfuse3.ROOT_INODE, b'user.test', b'value', ctx)
            self.assertEqual(setxattr_error.exception.errno, errno.ENOSYS)

            with self.assertRaises(pyfuse3.FUSEError) as removexattr_error:
                await operations.removexattr(pyfuse3.ROOT_INODE, b'user.test', ctx)
            self.assertEqual(removexattr_error.exception.errno, errno.ENOSYS)

            with self.assertRaises(pyfuse3.FUSEError) as mknod_error:
                await operations.mknod(pyfuse3.ROOT_INODE, b'node', stat.S_IFCHR | 0o600, 0, ctx)
            self.assertEqual(mknod_error.exception.errno, errno.ENOSYS)

            with self.assertRaises(pyfuse3.FUSEError) as rename_error:
                await operations.rename(
                    pyfuse3.ROOT_INODE,
                    b'a',
                    pyfuse3.ROOT_INODE,
                    b'b',
                    pyfuse3.RENAME_EXCHANGE,
                    ctx,
                )
            self.assertEqual(rename_error.exception.errno, errno.ENOSYS)

        trio.run(scenario)


if __name__ == '__main__':
    unittest.main()