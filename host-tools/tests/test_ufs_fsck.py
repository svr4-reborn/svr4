from __future__ import annotations

import unittest

from host_tools.fs.common import FilesystemCandidate
from host_tools.fs.ufs import UFS_CG_BTOT_OFFSET
from host_tools.fs.ufs import UFS_CG_MAGIC
from host_tools.fs.ufs import UFS_CG_MAGIC_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NBFREE_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NDIR_OFFSET
from host_tools.fs.ufs import UFS_FS_CSTOTAL_NIFREE_OFFSET
from host_tools.fs.ufs import apply_ufs_inode_replacement
from host_tools.fs.ufs import build_ufs_directory_block
from host_tools.fs.ufs import cg_block_offset
from host_tools.fs.ufs import create_ufs_file
from host_tools.fs.ufs import initialize_pristine_ufs_cg
from host_tools.fs.ufs import initialize_ufs_inode
from host_tools.fs.ufs import recompute_ufs_summary_counts
from host_tools.fs.ufs import set_frag_state
from host_tools.fs.ufs import u32
from host_tools.fs.ufs import ufs_csum_offset
from host_tools.fs.ufs import UFS_IFDIR
from host_tools.fs.ufs import UFS_ROOT_INODE
from host_tools.fs.ufs import add_ufs_directory_entry
from host_tools.fs.ufs import read_cg_block
from host_tools.fs.ufs import read_ufs_inode
from host_tools.fs.ufs import set_ufs_inode_state
from host_tools.fs.ufs import write_cg_block
from host_tools.fs.ufs import write_ufs_inode_nlink
from host_tools.fs.ufs import write_ufs_inode_blocks
from host_tools.fs.ufs_fsck import analyze_ufs_filesystem
from host_tools.fs.ufs_fsck import repair_ufs_filesystem


def build_multicg_filesystem() -> tuple[bytearray, FilesystemCandidate]:
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
            'nspf': 2,
            'nsect': 32,
            'spc': 64,
            'ncyl': 4,
            'cpg': 2,
            'csaddr': 120,
            'cssize': 32,
        },
    )
    image[UFS_FS_CSTOTAL_NDIR_OFFSET:UFS_FS_CSTOTAL_NDIR_OFFSET + 4] = (1).to_bytes(4, 'little')
    image[UFS_FS_CSTOTAL_NBFREE_OFFSET:UFS_FS_CSTOTAL_NBFREE_OFFSET + 4] = (28).to_bytes(4, 'little')
    image[UFS_FS_CSTOTAL_NIFREE_OFFSET:UFS_FS_CSTOTAL_NIFREE_OFFSET + 4] = (61).to_bytes(4, 'little')

    initialize_pristine_ufs_cg(image, filesystem, 0)
    initialize_pristine_ufs_cg(image, filesystem, 1)

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
    recompute_ufs_summary_counts(image, filesystem)
    return image, filesystem


class UFSFsckTests(unittest.TestCase):
    def test_reports_clean_for_normalized_filesystem(self) -> None:
        image, filesystem = build_multicg_filesystem()
        create_ufs_file(image, filesystem, '/tiny.bin', b'hello world')

        report = analyze_ufs_filesystem(image, filesystem)

        self.assertEqual(len(report.issues), 0)

    def test_detects_incorrect_block_count(self) -> None:
        image, filesystem = build_multicg_filesystem()
        created = create_ufs_file(image, filesystem, '/tiny.bin', b'hello world')
        inode_number = int(created['inode'])
        write_ufs_inode_blocks(image, filesystem, inode_number, 1)

        report = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(any(issue.kind == 'incorrect-block-count' and issue.inode == inode_number for issue in report.issues))

    def test_detects_bad_cylinder_group_magic(self) -> None:
        image, filesystem = build_multicg_filesystem()
        second_cg_offset = cg_block_offset(filesystem, 1)
        image[second_cg_offset + UFS_CG_MAGIC_OFFSET:second_cg_offset + UFS_CG_MAGIC_OFFSET + 4] = (0).to_bytes(4, 'little')
        self.assertNotEqual(u32(image, second_cg_offset + UFS_CG_MAGIC_OFFSET), UFS_CG_MAGIC)

        report = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(any(issue.kind == 'bad-cylinder-group' and issue.details.get('cg') == 1 for issue in report.issues))

    def test_detects_link_count_mismatch(self) -> None:
        image, filesystem = build_multicg_filesystem()
        initialize_ufs_inode(image, filesystem, 7, 0o100644, nlink=5)
        cg_bytes = read_cg_block(image, filesystem, 0)
        set_ufs_inode_state(cg_bytes, UFS_ROOT_INODE, used=True)
        set_ufs_inode_state(cg_bytes, 7, used=True)
        write_cg_block(image, filesystem, 0, cg_bytes)
        root_inode = read_ufs_inode(bytes(image), filesystem.start_offset, filesystem.details, UFS_ROOT_INODE)
        assert root_inode is not None
        add_ufs_directory_entry(image, filesystem, UFS_ROOT_INODE, root_inode, 'linked', 7)

        report = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(
            any(
                issue.kind == 'link-count-mismatch'
                and issue.inode == 7
                and issue.details.get('expected') == 1
                and issue.details.get('actual') == 5
                for issue in report.issues
            )
        )

    def test_detects_bitmap_mismatch(self) -> None:
        image, filesystem = build_multicg_filesystem()
        created = create_ufs_file(image, filesystem, '/tiny.bin', b'hello world')
        inode_number = int(created['inode'])
        inode = read_ufs_inode(bytes(image), filesystem.start_offset, filesystem.details, inode_number)
        assert inode is not None
        first_frag = int(inode['direct_blocks'][0])
        cg_bytes = read_cg_block(image, filesystem, 0)
        set_frag_state(cg_bytes, first_frag, free=True)
        write_cg_block(image, filesystem, 0, cg_bytes)

        report = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(any(issue.kind == 'bitmap-mismatch' and issue.details.get('cg') == 0 for issue in report.issues))

    def test_detects_summary_information_mismatch(self) -> None:
        image, filesystem = build_multicg_filesystem()
        create_ufs_file(image, filesystem, '/tiny.bin', b'hello world')
        cg_bytes = read_cg_block(image, filesystem, 0)
        cg_bytes[UFS_CG_BTOT_OFFSET + 4:UFS_CG_BTOT_OFFSET + 8] = (7).to_bytes(4, 'little')
        write_cg_block(image, filesystem, 0, cg_bytes)

        report = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(any(issue.kind == 'summary-information-mismatch' and issue.details.get('cg') == 0 for issue in report.issues))

    def test_repair_fixes_summary_information_mismatch(self) -> None:
        image, filesystem = build_multicg_filesystem()
        create_ufs_file(image, filesystem, '/tiny.bin', b'hello world')
        cg_bytes = read_cg_block(image, filesystem, 0)
        cg_bytes[UFS_CG_BTOT_OFFSET + 4:UFS_CG_BTOT_OFFSET + 8] = (7).to_bytes(4, 'little')
        write_cg_block(image, filesystem, 0, cg_bytes)

        report = analyze_ufs_filesystem(image, filesystem)
        _, modified = repair_ufs_filesystem(image, filesystem, report)
        repaired = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(modified)
        self.assertFalse(any(issue.kind == 'summary-information-mismatch' for issue in repaired.issues))

    def test_repair_fixes_superblock_summary_cache_mismatch(self) -> None:
        image, filesystem = build_multicg_filesystem()
        create_ufs_file(image, filesystem, '/tiny.bin', b'hello world')
        csum_offset = ufs_csum_offset(filesystem, filesystem.details, 0)
        assert csum_offset is not None
        image[csum_offset + 4:csum_offset + 8] = (99).to_bytes(4, 'little')

        report = analyze_ufs_filesystem(image, filesystem)
        self.assertTrue(any(issue.kind == 'superblock-summary-mismatch' and issue.details.get('cg') == 0 for issue in report.issues))

        _, modified = repair_ufs_filesystem(image, filesystem, report)
        repaired = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(modified)
        self.assertFalse(any(issue.kind == 'superblock-summary-mismatch' for issue in repaired.issues))

    def test_repair_clears_partially_allocated_free_inode(self) -> None:
        image, filesystem = build_multicg_filesystem()
        inode_offset = 8192
        image[inode_offset:inode_offset + 16] = b'corrupt-inode!!!'

        report = analyze_ufs_filesystem(image, filesystem)
        self.assertTrue(any(issue.kind == 'partially-allocated-inode' for issue in report.issues))

        cleared, modified = repair_ufs_filesystem(image, filesystem, report)
        repaired = analyze_ufs_filesystem(image, filesystem)

        self.assertEqual(len(cleared), 1)
        self.assertTrue(modified)
        self.assertEqual(len(repaired.issues), 0)

    def test_detects_directory_entry_to_free_inode(self) -> None:
        image, filesystem = build_multicg_filesystem()
        cg_bytes = read_cg_block(image, filesystem, 0)
        set_ufs_inode_state(cg_bytes, UFS_ROOT_INODE, used=True)
        write_cg_block(image, filesystem, 0, cg_bytes)
        root_inode = read_ufs_inode(bytes(image), filesystem.start_offset, filesystem.details, UFS_ROOT_INODE)
        assert root_inode is not None

        add_ufs_directory_entry(image, filesystem, UFS_ROOT_INODE, root_inode, 'ghost', 7)

        report = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(
            any(
                issue.kind == 'directory-entry-to-free-inode'
                and issue.details.get('entry_name') == 'ghost'
                and issue.details.get('entry_inode') == 7
                for issue in report.issues
            )
        )

    def test_repair_removes_directory_entry_to_free_inode(self) -> None:
        image, filesystem = build_multicg_filesystem()
        cg_bytes = read_cg_block(image, filesystem, 0)
        set_ufs_inode_state(cg_bytes, UFS_ROOT_INODE, used=True)
        write_cg_block(image, filesystem, 0, cg_bytes)
        root_inode = read_ufs_inode(bytes(image), filesystem.start_offset, filesystem.details, UFS_ROOT_INODE)
        assert root_inode is not None

        add_ufs_directory_entry(image, filesystem, UFS_ROOT_INODE, root_inode, 'ghost', 7)

        report = analyze_ufs_filesystem(image, filesystem)
        _, modified = repair_ufs_filesystem(image, filesystem, report)
        repaired = analyze_ufs_filesystem(image, filesystem)

        self.assertTrue(modified)
        self.assertFalse(any(issue.kind == 'directory-entry-to-free-inode' for issue in repaired.issues))


if __name__ == '__main__':
    unittest.main()