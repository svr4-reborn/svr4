from __future__ import annotations

import errno
import os
import stat
import unittest
from unittest import mock

import pyfuse3
import trio

from host_tools.fs.bfs import build_bfs_filesystem_image, detect_bfs, read_bfs_path_bytes
from host_tools.fs.bfs_fuse import BFSOperations, BFSVolume, make_test_context


def build_test_filesystem() -> tuple[bytearray, object]:
    image = bytearray(
        build_bfs_filesystem_image(
            128 * 512,
            [
                ('unix', b'kernel payload'),
                ('fdboot', b'boot blocks'),
            ],
            dirent_slots=16,
        )
    )
    filesystem = detect_bfs(bytes(image))[0]
    return image, filesystem


class BFSFuseFrontendTests(unittest.TestCase):
    def build_operations(self) -> tuple[BFSOperations, list[bytes]]:
        image, filesystem = build_test_filesystem()
        flushes: list[bytes] = []
        volume = BFSVolume(
            image=image,
            filesystem=filesystem,
            sector_count=len(image) // 512,
            flush_callback=lambda data: flushes.append(bytes(data)),
        )
        return BFSOperations(volume), flushes

    def test_create_write_lookup_and_setattr(self) -> None:
        async def scenario() -> None:
            operations, flushes = self.build_operations()
            ctx = make_test_context(uid=1000, gid=100, umask=0o022)

            file_info, created = await operations.create(pyfuse3.ROOT_INODE, b'hello.txt', 0o666, os.O_RDWR, ctx)
            self.assertEqual(created.st_size, 0)
            self.assertGreaterEqual(len(flushes), 1)

            bytes_written = await operations.write(file_info.fh, 0, b'hello world')
            self.assertEqual(bytes_written, 11)
            self.assertGreaterEqual(len(flushes), 2)

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
                return len(first_batch) < 5

            with mock.patch('pyfuse3.readdir_reply', side_effect=first_reply):
                await operations.readdir(fh, 0, object())

            self.assertGreaterEqual(len(first_batch), 5)
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

            with self.assertRaises(pyfuse3.FUSEError) as mkdir_error:
                await operations.mkdir(pyfuse3.ROOT_INODE, b'dir', 0o755, ctx)
            self.assertEqual(mkdir_error.exception.errno, errno.ENOSYS)

            with self.assertRaises(pyfuse3.FUSEError) as rmdir_error:
                await operations.rmdir(pyfuse3.ROOT_INODE, b'dir', ctx)
            self.assertEqual(rmdir_error.exception.errno, errno.ENOSYS)

            with self.assertRaises(pyfuse3.FUSEError) as link_error:
                await operations.link(pyfuse3.ROOT_INODE, pyfuse3.ROOT_INODE, b'alias', ctx)
            self.assertEqual(link_error.exception.errno, errno.ENOSYS)

            with self.assertRaises(pyfuse3.FUSEError) as symlink_error:
                await operations.symlink(pyfuse3.ROOT_INODE, b'boot.current', b'/unix', ctx)
            self.assertEqual(symlink_error.exception.errno, errno.ENOSYS)

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

    def test_rename_can_replace_open_target(self) -> None:
        async def scenario() -> None:
            operations, _ = self.build_operations()
            ctx = make_test_context(uid=0, gid=0, umask=0o022)

            source_info, source_entry = await operations.create(pyfuse3.ROOT_INODE, b'source', 0o644, os.O_RDWR, ctx)
            await operations.write(source_info.fh, 0, b'new payload')
            await operations.release(source_info.fh)

            target_info, target_entry = await operations.create(pyfuse3.ROOT_INODE, b'target', 0o644, os.O_RDWR, ctx)
            await operations.write(target_info.fh, 0, b'old payload')
            target_inode = pyfuse3.InodeT(target_entry.st_ino)
            await operations.lookup(pyfuse3.ROOT_INODE, b'target', ctx)

            await operations.rename(pyfuse3.ROOT_INODE, b'source', pyfuse3.ROOT_INODE, b'target', 0, ctx)

            renamed = await operations.lookup(pyfuse3.ROOT_INODE, b'target', ctx)
            self.assertEqual(renamed.st_ino, source_entry.st_ino)
            old_data = await operations.read(target_info.fh, 0, 32)
            self.assertEqual(old_data, b'old payload')

            await operations.release(target_info.fh)
            await operations.forget([(target_inode, 2)])

            with self.assertRaises(pyfuse3.FUSEError) as getattr_error:
                await operations.getattr(target_inode)
            self.assertEqual(getattr_error.exception.errno, errno.ENOENT)

        trio.run(scenario)


if __name__ == '__main__':
    unittest.main()