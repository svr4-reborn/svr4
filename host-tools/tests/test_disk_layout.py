from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import pyfuse3
import trio


from host_tools.disk.cli import format_bfs_path
from host_tools.disk.create import RawDiskGeometry, create_raw_image_skeleton
from host_tools.disk.fsprobe import select_slice_filesystem
from host_tools.disk.inspect import inspect_disk_image, inspect_slice_by_selector, read_slice_bytes
from host_tools.disk.structures import VtocPartition
from host_tools.fs.common import BFS_MAGIC
from host_tools.fs.ufs import read_ufs_path_bytes
from host_tools.fs.common import UFS_FS_BSIZE_OFFSET, UFS_FS_FPG_OFFSET, UFS_FS_FRAG_OFFSET, UFS_FS_FSIZE_OFFSET, UFS_FS_FSBTODB_OFFSET, UFS_FS_INOPB_OFFSET, UFS_FS_IPG_OFFSET, UFS_FS_MAGIC_OFFSET, UFS_MAGIC, UFS_SB_OFFSET
from host_tools.fs.ufs_fuse import UFSOperations, UFSVolume, make_test_context
from test_ufs_namespace import build_test_filesystem


class DiskLayoutTests(unittest.TestCase):
    @staticmethod
    def build_detectable_ufs_image() -> bytearray:
        ufs_image, _ = build_test_filesystem()
        super_offset = UFS_SB_OFFSET
        ufs_image[super_offset + UFS_FS_MAGIC_OFFSET:super_offset + UFS_FS_MAGIC_OFFSET + 4] = UFS_MAGIC.to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_BSIZE_OFFSET:super_offset + UFS_FS_BSIZE_OFFSET + 4] = (4096).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_FSIZE_OFFSET:super_offset + UFS_FS_FSIZE_OFFSET + 4] = (512).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_FRAG_OFFSET:super_offset + UFS_FS_FRAG_OFFSET + 4] = (8).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_FSBTODB_OFFSET:super_offset + UFS_FS_FSBTODB_OFFSET + 4] = (3).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_INOPB_OFFSET:super_offset + UFS_FS_INOPB_OFFSET + 4] = (32).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_IPG_OFFSET:super_offset + UFS_FS_IPG_OFFSET + 4] = (16).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_FPG_OFFSET:super_offset + UFS_FS_FPG_OFFSET + 4] = (128).to_bytes(4, 'little')
        return ufs_image

    def create_nonzero_offset_ufs_image(self, image_path: Path) -> bytearray:
        create_raw_image_skeleton(
            image_path,
            geometry=RawDiskGeometry(cylinders=64, heads=4, sectors_per_track=17),
            unix_partition_start=16,
            unix_partition_size=1024,
            volume='SVR4',
            slices=[VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=64, sector_count=256)],
        )

        image = bytearray(image_path.read_bytes())
        ufs_image = self.build_detectable_ufs_image()
        slice_start = (16 + 64) * 512
        image[slice_start:slice_start + len(ufs_image)] = ufs_image
        image_path.write_bytes(image)
        return ufs_image

    def test_inspect_and_format_bfs_use_absolute_slice_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / 'skeleton.raw'
            payload_path = temp_path / 'unix'
            payload_path.write_bytes(b'kernel payload')

            create_raw_image_skeleton(
                image_path,
                geometry=RawDiskGeometry(cylinders=32, heads=4, sectors_per_track=17),
                unix_partition_start=16,
                unix_partition_size=512,
                volume='SVR4',
                slices=[VtocPartition(index=10, tag=0x09, flag=0x200, start_sector=32, sector_count=64)],
            )

            output_path = temp_path / 'formatted.raw'
            format_bfs_path(image_path, 'stand', output_path, [('unix', payload_path)], dirent_slots=None)

            report = inspect_disk_image(output_path)
            _, slice_info = inspect_slice_by_selector(output_path, 'stand')

            self.assertEqual(slice_info.start_sector, 32)
            self.assertEqual(slice_info.absolute_start_sector, 48)
            self.assertEqual(slice_info.filesystem, 'bfs')
            self.assertEqual([entry['name'] for entry in slice_info.root_entries], ['unix'])
            self.assertEqual(report.slice_filesystems[0].absolute_start_sector, 48)

            formatted_slice = read_slice_bytes(output_path, slice_info.absolute_start_sector, slice_info.sector_count)
            untouched_gap = read_slice_bytes(output_path, slice_info.absolute_start_sector - 1, 1)
            self.assertNotEqual(formatted_slice[:4], b'\0\0\0\0')
            self.assertEqual(untouched_gap, b'\0' * 512)

    def test_ufs_volume_uses_absolute_slice_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / 'ufs.raw'

            ufs_image = self.create_nonzero_offset_ufs_image(image_path)

            volume = UFSVolume.open_raw_image(image_path, 'root')
            try:
                self.assertEqual(volume.filesystem.start_offset, 0)
                self.assertEqual(volume.image[:4], ufs_image[:4])
            finally:
                volume.close()

    def test_ufs_operations_persist_mutation_on_nonzero_offset_slice(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                image_path = temp_path / 'ufs-mutate.raw'
                create_raw_image_skeleton(
                    image_path,
                    geometry=RawDiskGeometry(cylinders=64, heads=4, sectors_per_track=17),
                    unix_partition_start=16,
                    unix_partition_size=1024,
                    volume='SVR4',
                    slices=[VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=64, sector_count=256)],
                )
                slice_start_sector = 16 + 64
                slice_offset = slice_start_sector * 512
                slice_image, filesystem = build_test_filesystem()

                image = bytearray(image_path.read_bytes())
                image[slice_offset:slice_offset + len(slice_image)] = slice_image
                image_path.write_bytes(image)

                def flush_callback(data: bytearray) -> None:
                    with image_path.open('r+b') as handle:
                        handle.seek(slice_offset)
                        handle.write(data)

                volume = UFSVolume(
                    image=bytearray(slice_image),
                    filesystem=filesystem,
                    sector_count=256,
                    flush_callback=flush_callback,
                )
                try:
                    operations = UFSOperations(volume)
                    ctx = make_test_context(uid=1000, gid=100, umask=0o022)
                    file_info, created = await operations.create(pyfuse3.ROOT_INODE, b'offset.txt', 0o644, os.O_RDWR, ctx)
                    self.assertEqual(created.st_size, 0)
                    await operations.write(file_info.fh, 0, b'persisted through slice offset')
                    await operations.release(file_info.fh)
                    persisted_slice = read_slice_bytes(image_path, slice_start_sector, 256)
                    _, _, data = read_ufs_path_bytes(persisted_slice, filesystem, '/offset.txt')
                    self.assertEqual(data, b'persisted through slice offset')
                finally:
                    volume.close()

        trio.run(scenario)

    def test_slice_probe_prefers_filesystem_at_slice_start(self) -> None:
        image = self.build_detectable_ufs_image()
        image[512:516] = BFS_MAGIC.to_bytes(4, 'little')

        filesystem, filesystem_offset, _ = select_slice_filesystem(bytes(image))

        self.assertEqual(filesystem, 'ufs')
        self.assertEqual(filesystem_offset, 0)

    def test_create_skeleton_rejects_out_of_range_slice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'invalid.raw'
            with self.assertRaises(SystemExit) as error:
                create_raw_image_skeleton(
                    image_path,
                    geometry=RawDiskGeometry(cylinders=8, heads=4, sectors_per_track=17),
                    unix_partition_start=16,
                    unix_partition_size=64,
                    volume='SVR4',
                    slices=[VtocPartition(index=10, tag=0x09, flag=0x200, start_sector=48, sector_count=32)],
                )
            self.assertIn('exceeds the UNIX partition bounds', str(error.exception))

    def test_create_skeleton_rejects_invalid_slice_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'invalid-index.raw'
            with self.assertRaises(SystemExit) as error:
                create_raw_image_skeleton(
                    image_path,
                    geometry=RawDiskGeometry(cylinders=8, heads=4, sectors_per_track=17),
                    unix_partition_start=16,
                    unix_partition_size=64,
                    volume='SVR4',
                    slices=[VtocPartition(index=16, tag=0x09, flag=0x200, start_sector=16, sector_count=16)],
                )
            self.assertIn('outside the supported VTOC range', str(error.exception))


if __name__ == '__main__':
    unittest.main()