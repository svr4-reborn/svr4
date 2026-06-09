from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyfuse3
import trio

import host_tools.fs.ufs as ufs_module

from host_tools.disk.cli import format_bfs_path
from host_tools.disk.create import ACTIVE_PARTITION_CHAINLOADER_MBR, DISK_ADDRESSING_CHS, DISK_ADDRESSING_LBA28, RawDiskGeometry, create_raw_image_skeleton
from host_tools.disk.fsprobe import select_slice_filesystem
from host_tools.disk.inspect import inspect_disk_image, inspect_slice_by_selector, read_slice_bytes, resolve_guest_visible_sector
from host_tools.disk.structures import AltInfo, AltTableInfo, PdInfo, VtocPartition
from host_tools.disk.svr4 import ALT_SANITY, ALT_VERSION, is_valid_alt_info, parse_alt_info, remap_guest_visible_sector
from host_tools.fs.bfs import read_bfs_path_bytes
from host_tools.fs.bfs_fuse import BFSOperations, BFSVolume, make_test_context as make_bfs_test_context
from host_tools.fs.common import BFS_MAGIC, UFS_DINODE_SIZE
from host_tools.fs.disk_backed import DiskBackedSlice
from host_tools.fs.ufs import build_ufs_directory_block, format_ufs_filesystem, make_ufs_directory, create_ufs_file, read_ufs_path_bytes
from host_tools.fs.common import UFS_FS_BSIZE_OFFSET, UFS_FS_FPG_OFFSET, UFS_FS_FRAG_OFFSET, UFS_FS_FSIZE_OFFSET, UFS_FS_FSBTODB_OFFSET, UFS_FS_INOPB_OFFSET, UFS_FS_IPG_OFFSET, UFS_FS_MAGIC_OFFSET, UFS_MAGIC, UFS_SB_OFFSET
from host_tools.fs.ufs import UFS_FS_CBLKNO_OFFSET, UFS_FS_CGMASK_OFFSET, UFS_FS_CGOFFSET_OFFSET, UFS_FS_CSMASK_OFFSET, UFS_FS_CSSHIFT_OFFSET, UFS_FS_DBLKNO_OFFSET, UFS_FS_IBLKNO_OFFSET, UFS_FS_NCG_OFFSET, UFS_FS_NINDIR_OFFSET
from host_tools.fs.ufs_fuse import UFSOperations, UFSVolume, make_test_context
from host_tools.fs.ufs_lowlevel import detect_ufs as detect_ufs_lowlevel, read_ufs_file as read_ufs_file_lowlevel, read_ufs_inode as read_ufs_inode_lowlevel, ufs_inode_offset as ufs_inode_offset_lowlevel
from test_ufs_namespace import build_test_filesystem
from tasks.make_image import _build_hdboot_partition_bootstrap, _build_slice_layout, _run_rsync, format_root_slice, format_stand_slice, sync_root_with_rsync, validate_existing_image_for_reuse


class DiskLayoutTests(unittest.TestCase):
    def test_create_skeleton_uses_sparse_file_for_large_lba_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'large-sparse.raw'
            geometry = RawDiskGeometry(cylinders=4096, heads=16, sectors_per_track=63)
            create_raw_image_skeleton(
                image_path,
                geometry=geometry,
                unix_partition_start=1,
                unix_partition_size=geometry.total_sectors - 1,
                volume='SVR4',
                slices=[VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=2048, sector_count=2048)],
                disk_addressing=DISK_ADDRESSING_LBA28,
            )

            stat_result = image_path.stat()
            self.assertEqual(stat_result.st_size, geometry.total_sectors * 512)
            self.assertLess(stat_result.st_blocks * 512, stat_result.st_size // 16)

    def test_validate_existing_image_for_reuse_accepts_exact_layout_and_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'reuse.raw'
            geometry = RawDiskGeometry(cylinders=512, heads=4, sectors_per_track=17)
            unix_partition_start, unix_partition_size, slices = _build_slice_layout(
                geometry,
                stand_start_sector=64,
                stand_size_mb=1,
                swap_size_mb=1,
                root_align_sectors=68,
            )
            create_raw_image_skeleton(
                image_path,
                geometry=geometry,
                unix_partition_start=unix_partition_start,
                unix_partition_size=unix_partition_size,
                volume='SVR4',
                slices=slices,
                mbr_boot_code=ACTIVE_PARTITION_CHAINLOADER_MBR,
                disk_addressing=DISK_ADDRESSING_CHS,
            )
            format_stand_slice(image_path, slices, [('unix', b'kernel'), ('hdboot', b'boot')])
            format_root_slice(
                image_path,
                slices,
                timestamp=1,
                ufs_bytes_per_inode=8192,
                tracks_per_cylinder=geometry.heads,
                sectors_per_track=geometry.sectors_per_track,
            )

            reusable, reason = validate_existing_image_for_reuse(
                image_path,
                geometry=geometry,
                unix_partition_start=unix_partition_start,
                unix_partition_size=unix_partition_size,
                slices=slices,
                disk_addressing=DISK_ADDRESSING_CHS,
            )
            self.assertTrue(reusable, reason)

            reusable, reason = validate_existing_image_for_reuse(
                image_path,
                geometry=RawDiskGeometry(cylinders=513, heads=4, sectors_per_track=17),
                unix_partition_start=unix_partition_start,
                unix_partition_size=unix_partition_size,
                slices=slices,
                disk_addressing=DISK_ADDRESSING_CHS,
            )
            self.assertFalse(reusable)
            self.assertIn('image size differs', reason)

    def test_root_rsync_excludes_stand_and_deletes_stale_files(self) -> None:
        with patch('tasks.make_image.subprocess.Popen') as popen:
            popen.return_value.wait.return_value = 0
            sync_root_with_rsync(Path('/tmp/sysroot'), Path('/tmp/mount'))

        command = popen.call_args.args[0]
        self.assertIn('--delete', command)
        self.assertIn('--inplace', command)
        self.assertIn('--whole-file', command)
        self.assertIn('--info=progress2,stats2', command)
        self.assertIn('--exclude=/stand/***', command)
        self.assertIn('/tmp/sysroot/', command)
        self.assertIn('/tmp/mount/', command)

    def test_rsync_terminates_child_on_keyboard_interrupt(self) -> None:
        with patch('tasks.make_image.subprocess.Popen') as popen:
            process = popen.return_value
            process.wait.side_effect = [KeyboardInterrupt(), 0]

            with self.assertRaises(KeyboardInterrupt):
                _run_rsync(['rsync', 'source', 'dest'])

        process.terminate.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)

    def test_disk_backed_slice_buffers_writes_until_sync_flush(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'disk-backed.raw'
            image_path.write_bytes(b'\0' * 131072)
            disk_slice = DiskBackedSlice(image_path, 0, 131072)
            try:
                disk_slice[100:104] = b'test'
                self.assertEqual(disk_slice[100:104], b'test')
                self.assertEqual(image_path.read_bytes()[100:104], b'\0\0\0\0')

                ranges = disk_slice.dirty_ranges()
                self.assertEqual(ranges, [(0, 65536)])

                disk_slice.flush(sync=False)
                self.assertEqual(image_path.read_bytes()[100:104], b'\0\0\0\0')

                disk_slice.flush(sync=True)
                self.assertEqual(image_path.read_bytes()[100:104], b'test')
                self.assertEqual(disk_slice.dirty_ranges(), [])
            finally:
                disk_slice.close()

    def test_active_partition_chainloader_mbr_relocates_before_loading_bootstrap(self) -> None:
        self.assertLessEqual(len(ACTIVE_PARTITION_CHAINLOADER_MBR), 446)
        self.assertIn(bytes.fromhex('89e6bf0006b90002fcf3a4ea1d060000'), ACTIVE_PARTITION_CHAINLOADER_MBR)
        self.assertIn(bytes.fromhex('ea007c0000'), ACTIVE_PARTITION_CHAINLOADER_MBR)

    def test_hdboot_partition_bootstrap_requires_signature_at_sector_end(self) -> None:
        elf_header_size = 52
        program_header_size = 32
        segment_offset = 0x100
        segment_size = 768

        payload = bytearray(segment_offset + segment_size)
        payload[0:4] = b'\x7fELF'
        payload[4] = 1
        payload[5] = 1
        payload[28:32] = elf_header_size.to_bytes(4, 'little')
        payload[42:44] = program_header_size.to_bytes(2, 'little')
        payload[44:46] = (1).to_bytes(2, 'little')

        program_header_offset = elf_header_size
        payload[program_header_offset:program_header_offset + 4] = (1).to_bytes(4, 'little')
        payload[program_header_offset + 4:program_header_offset + 8] = segment_offset.to_bytes(4, 'little')
        payload[program_header_offset + 12:program_header_offset + 16] = (0).to_bytes(4, 'little')
        payload[program_header_offset + 16:program_header_offset + 20] = segment_size.to_bytes(4, 'little')

        segment = bytearray(segment_size)
        segment[510:512] = b'\x55\xaa'
        payload[segment_offset:segment_offset + segment_size] = segment

        fake_path = Path('/tmp/hdboot-test')
        with patch.object(Path, 'read_bytes', return_value=bytes(payload)):
            flattened = _build_hdboot_partition_bootstrap(fake_path)

        self.assertEqual(flattened[510:512], b'\x55\xaa')
        self.assertEqual(flattened[506:508], b'\x00\x00')

    def test_parse_alt_info_and_remap_guest_sector(self) -> None:
        raw = bytearray()
        raw.extend(ALT_SANITY.to_bytes(4, 'little'))
        raw.extend(ALT_VERSION.to_bytes(2, 'little'))
        raw.extend((0).to_bytes(2, 'little'))
        raw.extend((1).to_bytes(2, 'little'))
        raw.extend((2).to_bytes(2, 'little'))
        raw.extend((1000).to_bytes(4, 'little', signed=True))
        raw.extend((25).to_bytes(4, 'little', signed=True))
        raw.extend((-1).to_bytes(4, 'little', signed=True))
        raw.extend((1).to_bytes(2, 'little'))
        raw.extend((2).to_bytes(2, 'little'))
        raw.extend((2000).to_bytes(4, 'little', signed=True))
        raw.extend((1003).to_bytes(4, 'little', signed=True))
        raw.extend((-1).to_bytes(4, 'little', signed=True))

        alt_info = parse_alt_info(bytes(raw))

        self.assertTrue(is_valid_alt_info(alt_info))
        self.assertEqual(alt_info.track_table.bad_entries[:alt_info.track_table.used], [25])
        self.assertEqual(alt_info.sector_table.bad_entries[:alt_info.sector_table.used], [1003])

        pdinfo = PdInfo(
            drive_id=0,
            sanity=0,
            version=0,
            serial='',
            cylinders=0,
            tracks=0,
            sectors=17,
            bytes_per_sector=512,
            logical_sector_0=0,
            vtoc_ptr=0,
            vtoc_len=0,
            alt_ptr=0,
            alt_len=0,
        )
        partition = VtocPartition(index=1, tag=0x02, flag=0, start_sector=0, sector_count=0)
        backup_partition = VtocPartition(index=0, tag=0x05, flag=0, start_sector=0, sector_count=0)
        other_partition = VtocPartition(index=2, tag=0x07, flag=0, start_sector=0, sector_count=0)

        self.assertEqual(remap_guest_visible_sector(pdinfo, partition, alt_info, 25 * 17 + 3), 2000)
        self.assertEqual(remap_guest_visible_sector(pdinfo, backup_partition, alt_info, 25 * 17 + 3), 25 * 17 + 3)
        self.assertEqual(remap_guest_visible_sector(pdinfo, other_partition, alt_info, 25 * 17 + 3), 25 * 17 + 3)

    def test_trace_sector_uses_guest_visible_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / 'trace.raw'
            create_raw_image_skeleton(
                image_path,
                geometry=RawDiskGeometry(cylinders=32, heads=4, sectors_per_track=17),
                unix_partition_start=1,
                unix_partition_size=512,
                volume='SVR4',
                slices=[VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=64, sector_count=128)],
            )

            image = bytearray(image_path.read_bytes())
            pdinfo_offset = (1 + 29) * 512
            image[pdinfo_offset + 92:pdinfo_offset + 96] = (15872).to_bytes(4, 'little')
            image[pdinfo_offset + 96:pdinfo_offset + 98] = (32).to_bytes(2, 'little')
            alt_offset = (1 * 512) + 15872
            image[alt_offset:alt_offset + 4] = ALT_SANITY.to_bytes(4, 'little')
            image[alt_offset + 4:alt_offset + 6] = ALT_VERSION.to_bytes(2, 'little')
            image[alt_offset + 8:alt_offset + 10] = (0).to_bytes(2, 'little')
            image[alt_offset + 10:alt_offset + 12] = (0).to_bytes(2, 'little')
            image[alt_offset + 16:alt_offset + 18] = (1).to_bytes(2, 'little')
            image[alt_offset + 18:alt_offset + 20] = (1).to_bytes(2, 'little')
            image[alt_offset + 20:alt_offset + 24] = (300).to_bytes(4, 'little', signed=True)
            image[alt_offset + 24:alt_offset + 28] = (69).to_bytes(4, 'little', signed=True)
            image[300 * 512:(300 * 512) + 32] = b'guest-visible remap works here..'
            image_path.write_bytes(image)

            absolute_sector, guest_visible_sector, data = resolve_guest_visible_sector(image_path, '1', 5)

            self.assertEqual(absolute_sector, 69)
            self.assertEqual(guest_visible_sector, 300)
            self.assertEqual(data[:32], b'guest-visible remap works here..')

    def test_chs_mode_rejects_geometry_above_classic_cylinder_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'too-large.raw'
            with self.assertRaises(SystemExit):
                create_raw_image_skeleton(
                    image_path,
                    geometry=RawDiskGeometry(cylinders=1300, heads=16, sectors_per_track=63),
                    unix_partition_start=1,
                    unix_partition_size=(1300 * 16 * 63) - 1,
                    volume='SVR4',
                    slices=[VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=2048, sector_count=2048)],
                )

    def test_lba28_mode_allows_large_geometry_and_saturates_mbr_chs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'lba.raw'
            create_raw_image_skeleton(
                image_path,
                geometry=RawDiskGeometry(cylinders=1300, heads=16, sectors_per_track=63),
                unix_partition_start=1,
                unix_partition_size=(1300 * 16 * 63) - 1,
                volume='SVR4',
                slices=[VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=2048, sector_count=2048)],
                disk_addressing=DISK_ADDRESSING_LBA28,
            )

            image = image_path.read_bytes()
            partition_entry = image[446:462]

            self.assertEqual(partition_entry[5:8], bytes([15, 0xff, 0xff]))
            self.assertEqual(int.from_bytes(partition_entry[8:12], 'little'), 1)
            self.assertEqual(int.from_bytes(partition_entry[12:16], 'little'), (1300 * 16 * 63) - 1)

    @staticmethod
    def build_detectable_ufs_image(super_offset: int = UFS_SB_OFFSET) -> bytearray:
        ufs_image, _ = build_test_filesystem()
        ufs_image[super_offset + UFS_FS_MAGIC_OFFSET:super_offset + UFS_FS_MAGIC_OFFSET + 4] = UFS_MAGIC.to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_BSIZE_OFFSET:super_offset + UFS_FS_BSIZE_OFFSET + 4] = (4096).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_FSIZE_OFFSET:super_offset + UFS_FS_FSIZE_OFFSET + 4] = (512).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_FRAG_OFFSET:super_offset + UFS_FS_FRAG_OFFSET + 4] = (8).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_FSBTODB_OFFSET:super_offset + UFS_FS_FSBTODB_OFFSET + 4] = (3).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_INOPB_OFFSET:super_offset + UFS_FS_INOPB_OFFSET + 4] = (32).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_IPG_OFFSET:super_offset + UFS_FS_IPG_OFFSET + 4] = (16).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_FPG_OFFSET:super_offset + UFS_FS_FPG_OFFSET + 4] = (128).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_CGOFFSET_OFFSET:super_offset + UFS_FS_CGOFFSET_OFFSET + 4] = (0).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_CGMASK_OFFSET:super_offset + UFS_FS_CGMASK_OFFSET + 4] = (0).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_CBLKNO_OFFSET:super_offset + UFS_FS_CBLKNO_OFFSET + 4] = (1).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_IBLKNO_OFFSET:super_offset + UFS_FS_IBLKNO_OFFSET + 4] = (2).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_DBLKNO_OFFSET:super_offset + UFS_FS_DBLKNO_OFFSET + 4] = (3).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_NCG_OFFSET:super_offset + UFS_FS_NCG_OFFSET + 4] = (1).to_bytes(4, 'little')
        ufs_image[super_offset + UFS_FS_NINDIR_OFFSET:super_offset + UFS_FS_NINDIR_OFFSET + 4] = (1024).to_bytes(4, 'little')
        return ufs_image

    def test_slice_probe_rejects_legacy_ufs_superblock_offset(self) -> None:
        image = self.build_detectable_ufs_image(UFS_SB_OFFSET - 512)

        filesystem, filesystem_offset, _ = select_slice_filesystem(bytes(image))

        self.assertIsNone(filesystem)
        self.assertEqual(filesystem_offset, 0)

    def test_detect_ufs_prefers_canonical_superblock_interpretation(self) -> None:
        candidates = detect_ufs_lowlevel(bytes(self.build_detectable_ufs_image()))

        primary_candidates = [candidate for candidate in candidates if candidate.super_offset == UFS_SB_OFFSET]

        self.assertEqual(len(primary_candidates), 1)
        self.assertEqual(primary_candidates[0].start_offset, 0)
        self.assertNotIn('layout_bias', primary_candidates[0].details)

    def create_nonzero_offset_ufs_image(self, image_path: Path) -> bytearray:
        create_raw_image_skeleton(
            image_path,
            geometry=RawDiskGeometry(cylinders=64, heads=4, sectors_per_track=17),
            unix_partition_start=16,
            unix_partition_size=1024,
            volume='SVR4',
            slices=[VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=80, sector_count=256)],
        )

        image = bytearray(image_path.read_bytes())
        ufs_image = self.build_detectable_ufs_image()
        slice_start = 80 * 512
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
                slices=[VtocPartition(index=10, tag=0x09, flag=0x200, start_sector=48, sector_count=64)],
            )

            output_path = temp_path / 'formatted.raw'
            format_bfs_path(image_path, 'stand', output_path, [('unix', payload_path)], dirent_slots=None)

            report = inspect_disk_image(output_path)
            _, slice_info = inspect_slice_by_selector(output_path, 'stand')

            self.assertEqual(slice_info.start_sector, 48)
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
                    slices=[VtocPartition(index=1, tag=0x02, flag=0x200, start_sector=80, sector_count=256)],
                )
                slice_start_sector = 80
                slice_offset = slice_start_sector * 512
                slice_image, filesystem = build_test_filesystem()

                image = bytearray(image_path.read_bytes())
                image[slice_offset:slice_offset + len(slice_image)] = slice_image
                image_path.write_bytes(image)

                def flush_callback(data: bytearray, dirty_ranges: list[tuple[int, int]], sync: bool) -> None:
                    del sync
                    with image_path.open('r+b') as handle:
                        for start, end in dirty_ranges:
                            handle.seek(slice_offset + start)
                            handle.write(data[start:end])

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

    def test_format_ufs_filesystem_builds_mutable_slice(self) -> None:
        slice_image = bytearray(16 * 1024 * 1024)

        filesystem = format_ufs_filesystem(slice_image)
        make_ufs_directory(slice_image, filesystem, '/etc')
        create_ufs_file(slice_image, filesystem, '/etc/motd', b'svr4\n')

        detected = detect_ufs_lowlevel(bytes(slice_image))

        self.assertEqual(len(detected), 1)
        self.assertEqual(detected[0].super_offset, UFS_SB_OFFSET)
        self.assertEqual(detected[0].start_offset, 0)
        self.assertEqual(read_ufs_path_bytes(bytes(slice_image), filesystem, '/etc/motd')[2], b'svr4\n')

    def test_format_ufs_filesystem_populates_summary_index_fields(self) -> None:
        slice_image = bytearray(16 * 1024 * 1024)

        ufs_module._UFS_METADATA_NORMALIZATION_STATE.clear()
        format_ufs_filesystem(slice_image)

        csmask = int.from_bytes(
            slice_image[UFS_SB_OFFSET + UFS_FS_CSMASK_OFFSET:UFS_SB_OFFSET + UFS_FS_CSMASK_OFFSET + 4],
            'little',
            signed=False,
        )
        csshift = int.from_bytes(
            slice_image[UFS_SB_OFFSET + UFS_FS_CSSHIFT_OFFSET:UFS_SB_OFFSET + UFS_FS_CSSHIFT_OFFSET + 4],
            'little',
            signed=False,
        )

        self.assertEqual(csmask, 0xFFFFFE00)
        self.assertEqual(csshift, 9)

    def test_bfs_volume_uses_absolute_slice_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / 'bfs-skeleton.raw'
            formatted_path = temp_path / 'bfs.raw'
            payload_path = temp_path / 'unix'
            payload_path.write_bytes(b'kernel payload')

            create_raw_image_skeleton(
                image_path,
                geometry=RawDiskGeometry(cylinders=32, heads=4, sectors_per_track=17),
                unix_partition_start=16,
                unix_partition_size=512,
                volume='SVR4',
                slices=[VtocPartition(index=10, tag=0x09, flag=0x200, start_sector=48, sector_count=64)],
            )

            format_bfs_path(image_path, 'stand', formatted_path, [('unix', payload_path)], dirent_slots=None)
            _, slice_info = inspect_slice_by_selector(formatted_path, 'stand')
            bfs_image = read_slice_bytes(formatted_path, slice_info.absolute_start_sector, slice_info.sector_count)

            volume = BFSVolume.open_raw_image(formatted_path, 'stand')
            try:
                self.assertEqual(volume.filesystem.start_offset, 0)
                self.assertEqual(volume.image[:4], bfs_image[:4])
            finally:
                volume.close()

    def test_bfs_operations_persist_mutation_on_nonzero_offset_slice(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                image_path = temp_path / 'bfs-mutate-skeleton.raw'
                formatted_path = temp_path / 'bfs-mutate.raw'
                payload_path = temp_path / 'unix'
                payload_path.write_bytes(b'kernel payload')

                create_raw_image_skeleton(
                    image_path,
                    geometry=RawDiskGeometry(cylinders=32, heads=4, sectors_per_track=17),
                    unix_partition_start=16,
                    unix_partition_size=512,
                    volume='SVR4',
                    slices=[VtocPartition(index=10, tag=0x09, flag=0x200, start_sector=48, sector_count=64)],
                )

                format_bfs_path(image_path, 'stand', formatted_path, [('unix', payload_path)], dirent_slots=None)
                _, slice_info = inspect_slice_by_selector(formatted_path, 'stand')
                volume = BFSVolume.open_raw_image(formatted_path, 'stand')
                try:
                    operations = BFSOperations(volume)
                    ctx = make_bfs_test_context(uid=1000, gid=100, umask=0o022)
                    file_info, created = await operations.create(pyfuse3.ROOT_INODE, b'offset.txt', 0o644, os.O_RDWR, ctx)
                    self.assertEqual(created.st_size, 0)
                    await operations.write(file_info.fh, 0, b'persisted through slice offset')
                    await operations.release(file_info.fh)

                    persisted_slice = read_slice_bytes(formatted_path, slice_info.absolute_start_sector, slice_info.sector_count)
                    _, _, data = read_bfs_path_bytes(persisted_slice, volume.filesystem, '/offset.txt')
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

    def test_slice_probe_rejects_embedded_filesystem_away_from_slice_start(self) -> None:
        image = bytearray(512 * 1024)
        embedded_offset = 193024
        ufs_image = self.build_detectable_ufs_image()
        image[embedded_offset:embedded_offset + len(ufs_image)] = ufs_image

        filesystem, filesystem_offset, root_entries = select_slice_filesystem(bytes(image))

        self.assertIsNone(filesystem)
        self.assertEqual(filesystem_offset, 0)
        self.assertEqual(root_entries, [])

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
                    slices=[VtocPartition(index=10, tag=0x09, flag=0x200, start_sector=64, sector_count=32)],
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
                    slices=[VtocPartition(index=16, tag=0x09, flag=0x200, start_sector=32, sector_count=16)],
                )
            self.assertIn('outside the supported VTOC range', str(error.exception))


if __name__ == '__main__':
    unittest.main()
