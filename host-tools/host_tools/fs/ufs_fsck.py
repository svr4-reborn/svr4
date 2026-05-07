from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from host_tools.disk.inspect import inspect_slice_by_selector, read_slice_bytes

from .common import SECTOR_SIZE
from .ufs import UFS_CG_CS_NBFREE_OFFSET
from .ufs import UFS_CG_CS_NDIR_OFFSET
from .ufs import UFS_CG_CS_NFFREE_OFFSET
from .ufs import UFS_CG_CS_NIFREE_OFFSET
from .ufs import UFS_CG_IUSED_OFFSET
from .ufs import UFS_CG_MAGIC
from .ufs import UFS_CG_MAGIC_OFFSET
from .ufs import UFS_CG_NDBLK_OFFSET
from .ufs import UFS_FS_CSTOTAL_NBFREE_OFFSET
from .ufs import UFS_FS_CSTOTAL_NDIR_OFFSET
from .ufs import UFS_FS_CSTOTAL_NFFREE_OFFSET
from .ufs import UFS_FS_CSTOTAL_NIFREE_OFFSET
from .ufs import UFS_IFMT
from .ufs import clear_ufs_inode
from .ufs import delete_ufs_directory_entry
from .ufs import detect_ufs
from .ufs import is_frag_free
from .ufs import is_ufs_inode_used
from .ufs import iter_ufs_inode_directory_records
from .ufs import read_cg_block
from .ufs import read_ufs_inode
from .ufs import read_ufs_pointer_block
from .ufs import recompute_ufs_summary_counts
from .ufs import expected_ufs_cg_header
from .ufs import set_frag_state
from .ufs import set_ufs_inode_state
from .ufs import u32
from .ufs import ufs_allocation_byte_sizes
from .ufs import ufs_cgbase
from .ufs import ufs_cgdmin
from .ufs import ufs_csum_offset
from .ufs import ufs_inode_pointer_blocks
from .ufs import ufs_is_directory
from .ufs import write_cg_block
from .ufs import write_ufs_inode_nlink


@dataclass(slots=True)
class UFSFsckIssue:
    kind: str
    inode: int | None = None
    block: int | None = None
    message: str = ''
    details: dict[str, int | str] = field(default_factory=dict)


@dataclass(slots=True)
class UFSFsckReport:
    image: str
    slice: str
    allocated_inodes: int
    issues: list[UFSFsckIssue]
    superblock_totals: dict[str, int]
    recomputed_totals: dict[str, int]


def issue_is_fixable(issue: UFSFsckIssue) -> bool:
    return issue.kind in {
        'bitmap-mismatch',
        'link-count-mismatch',
        'summary-information-mismatch',
        'summary-mismatch',
        'superblock-summary-mismatch',
    } or (issue.kind == 'partially-allocated-inode' and issue.message == 'inode bitmap says free but inode contains data' and issue.inode is not None)


def _outrange(fs: dict[str, Any], blk: int, cnt: int) -> bool:
    fmax = int(fs['dsize'])
    if blk + cnt > fmax:
        return True
    cg = blk // int(fs['fpg'])
    if blk < ufs_cgdmin(fs, cg):
        return (blk + cnt) > (ufs_cgbase(fs, cg) + int(fs['cblkno']))
    return (blk + cnt) > ufs_cgbase(fs, cg + 1)


def _iter_pointer_issues(
    image: bytes | bytearray,
    filesystem: Any,
    fs: dict[str, Any],
    blkno: int,
    ilevel: int,
    isize: int,
    inode_number: int,
    seen_blocks: set[int],
    issues: list[UFSFsckIssue],
) -> int:
    frag = int(fs['frag'])
    nindir = int(fs['nindir'])
    bsize = int(fs['bsize'])
    counted_fragments = frag
    if _outrange(fs, blkno, frag):
        issues.append(
            UFSFsckIssue(
                kind='bad-block',
                inode=inode_number,
                block=blkno,
                message='indirect block is out of range',
            )
        )
        return counted_fragments
    for fragment in range(blkno, blkno + frag):
        if fragment in seen_blocks:
            issues.append(
                UFSFsckIssue(
                    kind='duplicate-block',
                    inode=inode_number,
                    block=fragment,
                    message='indirect block fragment is duplicated',
                )
            )
        else:
            seen_blocks.add(fragment)

    pointers = read_ufs_pointer_block(image, filesystem, blkno)
    next_level = ilevel - 1
    size_per_block = bsize
    for _ in range(next_level):
        size_per_block *= nindir
    needed_indirects = (isize // size_per_block) + 1
    if needed_indirects > nindir:
        needed_indirects = nindir
    for index, pointer in enumerate(pointers[:needed_indirects], start=1):
        if not pointer:
            continue
        if next_level > 0:
            counted_fragments += _iter_pointer_issues(
                image,
                filesystem,
                fs,
                int(pointer),
                next_level,
                isize - (index * size_per_block),
                inode_number,
                seen_blocks,
                issues,
            )
            continue
        counted_fragments += frag
        if _outrange(fs, int(pointer), frag):
            issues.append(
                UFSFsckIssue(
                    kind='bad-block',
                    inode=inode_number,
                    block=int(pointer),
                    message='data block is out of range',
                )
            )
            continue
        for fragment in range(int(pointer), int(pointer) + frag):
            if fragment in seen_blocks:
                issues.append(
                    UFSFsckIssue(
                        kind='duplicate-block',
                        inode=inode_number,
                        block=fragment,
                        message='data block fragment is duplicated',
                    )
                )
            else:
                seen_blocks.add(fragment)

    return counted_fragments


def _scan_inode_blocks(
    image: bytes | bytearray,
    filesystem: Any,
    fs: dict[str, Any],
    inode_number: int,
    inode: dict[str, int | list[int]],
    seen_blocks: set[int],
    issues: list[UFSFsckIssue],
) -> int:
    bsize = int(fs['bsize'])
    fsize = int(fs['fsize'])
    frag = int(fs['frag'])
    counted_fragments = 0
    ndb = (int(inode['size']) + bsize - 1) // bsize
    for direct_block in inode['direct_blocks']:
        ndb -= 1
        if ndb == 0 and (int(inode['size']) % bsize) != 0:
            numfrags = ((int(inode['size']) % bsize) + fsize - 1) // fsize
        else:
            numfrags = frag
        block = int(direct_block)
        if block == 0:
            continue
        counted_fragments += numfrags
        if _outrange(fs, block, numfrags):
            issues.append(
                UFSFsckIssue(
                    kind='bad-block',
                    inode=inode_number,
                    block=block,
                    message='direct block is out of range',
                )
            )
            continue
        for fragment in range(block, block + numfrags):
            if fragment in seen_blocks:
                issues.append(
                    UFSFsckIssue(
                        kind='duplicate-block',
                        inode=inode_number,
                        block=fragment,
                        message='direct block fragment is duplicated',
                    )
                )
            else:
                seen_blocks.add(fragment)
    for level, indirect_block in enumerate(inode['indirect_blocks'], start=1):
        block = int(indirect_block)
        if not block:
            continue
        counted_fragments += _iter_pointer_issues(
            image,
            filesystem,
            fs,
            block,
            level,
            int(inode['size']) - (bsize * 12),
            inode_number,
            seen_blocks,
            issues,
        )
    return counted_fragments


def analyze_ufs_filesystem(
    image: bytes | bytearray,
    filesystem: Any,
    *,
    image_label: str = '<memory>',
    slice_label: str = '0',
) -> UFSFsckReport:
    fs = filesystem.details
    ipg = int(fs['ipg'])
    ncg = int(fs['ncg'])
    frag = int(fs['frag'])
    block_size = int(fs['bsize'])
    imax = ipg * ncg
    seen_blocks: set[int] = set()
    issues: list[UFSFsckIssue] = []
    inode_states: dict[int, tuple[bool, dict[str, int | list[int]]]] = {}
    reference_counts: dict[int, int] = {}

    for cg in range(ncg):
        reserved_start = ufs_cgbase(fs, cg)
        reserved_end = ufs_cgdmin(fs, cg)
        seen_blocks.update(range(reserved_start, reserved_end))

    allocated_inodes = 0
    recomputed_totals = {'ndir': 0, 'nbfree': 0, 'nifree': 0, 'nffree': 0}
    for cg in range(ncg):
        cg_bytes = read_cg_block(image, filesystem, cg)
        magic = u32(cg_bytes, UFS_CG_MAGIC_OFFSET)
        if magic != UFS_CG_MAGIC:
            issues.append(
                UFSFsckIssue(
                    kind='bad-cylinder-group',
                    message='cylinder group has invalid magic',
                    details={'cg': cg, 'magic': magic},
                )
            )
            continue

        cg_ndblk = u32(cg_bytes, UFS_CG_NDBLK_OFFSET)
        actual_ndir = 0
        actual_nifree = ipg
        for inode_index in range(ipg):
            inode_number = (cg * ipg) + inode_index
            if inode_number < 2:
                continue
            inode = read_ufs_inode(image, filesystem.start_offset, fs, inode_number)
            if inode is None:
                continue
            used = is_ufs_inode_used(cg_bytes, inode_index)
            inode_states[inode_number] = (used, inode)
            allocated = int(inode['mode']) != 0
            if not used:
                if allocated or int(inode['size']) != 0 or any(int(value) != 0 for value in inode['direct_blocks']) or any(int(value) != 0 for value in inode['indirect_blocks']):
                    issues.append(
                        UFSFsckIssue(
                            kind='partially-allocated-inode',
                            inode=inode_number,
                            message='inode bitmap says free but inode contains data',
                        )
                    )
                continue
            actual_nifree -= 1
            allocated_inodes += 1
            if not allocated:
                issues.append(
                    UFSFsckIssue(
                        kind='partially-allocated-inode',
                        inode=inode_number,
                        message='inode bitmap says used but inode mode is zero',
                    )
                )
                continue
            if ufs_is_directory(inode):
                actual_ndir += 1
            elif (int(inode['mode']) & UFS_IFMT) == UFS_IFMT:
                issues.append(
                    UFSFsckIssue(
                        kind='unknown-file-type',
                        inode=inode_number,
                        message='inode has invalid file type bits',
                        details={'mode': int(inode['mode'])},
                    )
                )
            counted_fragments = _scan_inode_blocks(image, filesystem, fs, inode_number, inode, seen_blocks, issues)
            expected_sectors = counted_fragments * (int(fs['fsize']) // SECTOR_SIZE)
            if expected_sectors != int(inode['blocks']):
                issues.append(
                    UFSFsckIssue(
                        kind='incorrect-block-count',
                        inode=inode_number,
                        message='inode di_blocks does not match allocations',
                        details={'actual': int(inode['blocks']), 'expected': expected_sectors, 'size': int(inode['size'])},
                    )
                )

        actual_nbfree = 0
        if cg == 0:
            actual_nifree -= 2
        actual_nffree = 0
        for frag_base in range(0, cg_ndblk - frag + 1, frag):
            free_fragments = sum(1 for frag_offset in range(frag) if is_frag_free(cg_bytes, frag_base + frag_offset))
            if free_fragments == frag:
                actual_nbfree += 1
            elif 0 < free_fragments < frag:
                actual_nffree += free_fragments
        trailing_start = (cg_ndblk // frag) * frag
        for frag_index in range(trailing_start, cg_ndblk):
            if is_frag_free(cg_bytes, frag_index):
                actual_nffree += 1

        ondisk_summary = {
            'ndir': u32(cg_bytes, UFS_CG_CS_NDIR_OFFSET),
            'nbfree': u32(cg_bytes, UFS_CG_CS_NBFREE_OFFSET),
            'nifree': u32(cg_bytes, UFS_CG_CS_NIFREE_OFFSET),
            'nffree': u32(cg_bytes, UFS_CG_CS_NFFREE_OFFSET),
        }
        actual_summary = {
            'ndir': actual_ndir,
            'nbfree': actual_nbfree,
            'nifree': actual_nifree,
            'nffree': actual_nffree,
        }
        for key in recomputed_totals:
            recomputed_totals[key] += actual_summary[key]
        if ondisk_summary != actual_summary:
            issues.append(
                UFSFsckIssue(
                    kind='summary-mismatch',
                    message='cylinder group summary does not match bitmap/inode contents',
                    details={
                        'cg': cg,
                        'ondisk_ndir': ondisk_summary['ndir'],
                        'ondisk_nbfree': ondisk_summary['nbfree'],
                        'ondisk_nifree': ondisk_summary['nifree'],
                        'ondisk_nffree': ondisk_summary['nffree'],
                        'actual_ndir': actual_summary['ndir'],
                        'actual_nbfree': actual_summary['nbfree'],
                        'actual_nifree': actual_summary['nifree'],
                        'actual_nffree': actual_summary['nffree'],
                    },
                )
            )
        csum_offset = ufs_csum_offset(filesystem, fs, cg)
        if csum_offset is not None:
            cached_summary = {
                'ndir': u32(image, csum_offset),
                'nbfree': u32(image, csum_offset + 4),
                'nifree': u32(image, csum_offset + 8),
                'nffree': u32(image, csum_offset + 12),
            }
            if cached_summary != actual_summary:
                issues.append(
                    UFSFsckIssue(
                        kind='superblock-summary-mismatch',
                        message='superblock cylinder-group summary cache does not match reconstructed totals',
                        details={
                            'cg': cg,
                            'ondisk_ndir': cached_summary['ndir'],
                            'ondisk_nbfree': cached_summary['nbfree'],
                            'ondisk_nifree': cached_summary['nifree'],
                            'ondisk_nffree': cached_summary['nffree'],
                            'actual_ndir': actual_summary['ndir'],
                            'actual_nbfree': actual_summary['nbfree'],
                            'actual_nifree': actual_summary['nifree'],
                            'actual_nffree': actual_summary['nffree'],
                        },
                    )
                )
        expected_header, _ = expected_ufs_cg_header(image, filesystem, cg, cg_bytes)
        if cg_bytes[:UFS_CG_IUSED_OFFSET] != expected_header[:UFS_CG_IUSED_OFFSET]:
            diffs = [
                index
                for index, (actual, expected) in enumerate(
                    zip(cg_bytes[:UFS_CG_IUSED_OFFSET], expected_header[:UFS_CG_IUSED_OFFSET])
                )
                if actual != expected
            ]
            issues.append(
                UFSFsckIssue(
                    kind='summary-information-mismatch',
                    message='cylinder group summary tables do not match bitmap layout',
                    details={
                        'cg': cg,
                        'diff_count': len(diffs),
                        'first_offset': diffs[0] if diffs else -1,
                    },
                )
            )

    for inode_number, (used, inode) in inode_states.items():
        if not used or int(inode['mode']) == 0 or not ufs_is_directory(inode):
            continue
        for record in iter_ufs_inode_directory_records(image, filesystem, inode):
            if record.inode == 0:
                continue
            child_inode_number = int(record.inode)
            if 0 <= child_inode_number < imax:
                reference_counts[child_inode_number] = reference_counts.get(child_inode_number, 0) + 1
            if record.name in {'.', '..'}:
                continue
            if child_inode_number < 2 or child_inode_number >= imax:
                issues.append(
                    UFSFsckIssue(
                        kind='directory-entry-to-invalid-inode',
                        inode=inode_number,
                        message='directory entry points outside the valid inode range',
                        details={'entry_inode': child_inode_number, 'entry_name': record.name},
                    )
                )
                continue
            child_state = inode_states.get(child_inode_number)
            if child_state is None:
                issues.append(
                    UFSFsckIssue(
                        kind='directory-entry-to-invalid-inode',
                        inode=inode_number,
                        message='directory entry points to an unreadable inode',
                        details={'entry_inode': child_inode_number, 'entry_name': record.name},
                    )
                )
                continue
            child_used, child_inode = child_state
            if not child_used or int(child_inode['mode']) == 0:
                issues.append(
                    UFSFsckIssue(
                        kind='directory-entry-to-free-inode',
                        inode=inode_number,
                        message='directory entry points to a free or zeroed inode',
                        details={'entry_inode': child_inode_number, 'entry_name': record.name},
                    )
                )

    for inode_number, (used, inode) in inode_states.items():
        if not used or int(inode['mode']) == 0:
            continue
        if inode_number not in reference_counts:
            continue
        expected_nlink = reference_counts.get(inode_number, 0)
        actual_nlink = int(inode['nlink'])
        if expected_nlink != actual_nlink:
            issues.append(
                UFSFsckIssue(
                    kind='link-count-mismatch',
                    inode=inode_number,
                    message='inode link count does not match directory references',
                    details={'actual': actual_nlink, 'expected': expected_nlink},
                )
            )

    for cg in range(ncg):
        cg_bytes = read_cg_block(image, filesystem, cg)
        cg_ndblk = u32(cg_bytes, UFS_CG_NDBLK_OFFSET)
        inode_mismatch_count = 0
        free_mismatch_count = 0
        sample_inode: int | None = None
        sample_inode_expected = 0
        sample_inode_actual = 0
        sample_frag: int | None = None
        sample_frag_expected = 0
        sample_frag_actual = 0
        for inode_index in range(ipg):
            inode_number = (cg * ipg) + inode_index
            expected_used = inode_number < 2 if cg == 0 else False
            inode_state = inode_states.get(inode_number)
            if inode_state is not None and int(inode_state[1]['mode']) != 0:
                expected_used = True
            actual_used = is_ufs_inode_used(cg_bytes, inode_index)
            if expected_used != actual_used:
                inode_mismatch_count += 1
                if sample_inode is None:
                    sample_inode = inode_number
                    sample_inode_expected = int(expected_used)
                    sample_inode_actual = int(actual_used)
        dbase = ufs_cgbase(fs, cg)
        data_frag_start = ufs_cgdmin(fs, cg) - dbase
        for frag_index in range(data_frag_start, cg_ndblk):
            expected_free = (dbase + frag_index) not in seen_blocks
            actual_free = is_frag_free(cg_bytes, frag_index)
            if not expected_free and actual_free:
                free_mismatch_count += 1
                if sample_frag is None:
                    sample_frag = dbase + frag_index
                    sample_frag_expected = int(expected_free)
                    sample_frag_actual = int(actual_free)
        if inode_mismatch_count or free_mismatch_count:
            details: dict[str, int | str] = {
                'cg': cg,
                'inode_mismatch_count': inode_mismatch_count,
                'free_mismatch_count': free_mismatch_count,
            }
            if sample_inode is not None:
                details['sample_inode'] = sample_inode
                details['sample_inode_expected_used'] = sample_inode_expected
                details['sample_inode_actual_used'] = sample_inode_actual
            if sample_frag is not None:
                details['sample_fragment'] = sample_frag
                details['sample_fragment_expected_free'] = sample_frag_expected
                details['sample_fragment_actual_free'] = sample_frag_actual
            issues.append(
                UFSFsckIssue(
                    kind='bitmap-mismatch',
                    message='cylinder group bitmaps do not match reconstructed filesystem state',
                    details=details,
                )
            )

    super_offset = filesystem.super_offset
    superblock_totals = {
        'ndir': u32(image, super_offset + UFS_FS_CSTOTAL_NDIR_OFFSET),
        'nbfree': u32(image, super_offset + UFS_FS_CSTOTAL_NBFREE_OFFSET),
        'nifree': u32(image, super_offset + UFS_FS_CSTOTAL_NIFREE_OFFSET),
        'nffree': u32(image, super_offset + UFS_FS_CSTOTAL_NFFREE_OFFSET),
    }
    if superblock_totals != recomputed_totals:
        issues.append(
            UFSFsckIssue(
                kind='superblock-summary-mismatch',
                message='superblock summary totals do not match cylinder groups',
                details={
                    'ondisk_ndir': superblock_totals['ndir'],
                    'ondisk_nbfree': superblock_totals['nbfree'],
                    'ondisk_nifree': superblock_totals['nifree'],
                    'ondisk_nffree': superblock_totals['nffree'],
                    'actual_ndir': recomputed_totals['ndir'],
                    'actual_nbfree': recomputed_totals['nbfree'],
                    'actual_nifree': recomputed_totals['nifree'],
                    'actual_nffree': recomputed_totals['nffree'],
                },
            )
        )

    return UFSFsckReport(
        image=image_label,
        slice=slice_label,
        allocated_inodes=allocated_inodes,
        issues=issues,
        superblock_totals=superblock_totals,
        recomputed_totals=recomputed_totals,
    )


def analyze_ufs_image(image_path: Path, slice_selector: str) -> UFSFsckReport:
    _, slice_fs = inspect_slice_by_selector(image_path, slice_selector)
    slice_image = read_slice_bytes(image_path, slice_fs.absolute_start_sector, slice_fs.sector_count)
    filesystem = detect_ufs(slice_image)[0]
    return analyze_ufs_filesystem(
        slice_image,
        filesystem,
        image_label=str(image_path),
        slice_label=slice_selector,
    )


def repair_ufs_filesystem(image: bytearray, filesystem: Any, report: UFSFsckReport | None = None) -> tuple[list[int], bool]:
    current_report = analyze_ufs_filesystem(image, filesystem) if report is None else report
    cleared_inodes: list[int] = []
    seen_inodes: set[int] = set()
    removed_directory_entries: set[tuple[int, str]] = set()
    repaired_links: set[int] = set()
    rebuilt_bitmaps = False
    rebuilt_summaries = False
    modified = False
    for issue in current_report.issues:
        if not issue_is_fixable(issue):
            if issue.kind != 'directory-entry-to-free-inode' or issue.inode is None:
                continue
            entry_name = issue.details.get('entry_name')
            if not isinstance(entry_name, str):
                continue
            parent_inode_number = int(issue.inode)
            key = (parent_inode_number, entry_name)
            if key in removed_directory_entries:
                continue
            parent_inode = read_ufs_inode(image, filesystem.start_offset, filesystem.details, parent_inode_number)
            if parent_inode is None or int(parent_inode['mode']) == 0 or not ufs_is_directory(parent_inode):
                continue
            delete_ufs_directory_entry(image, filesystem, parent_inode_number, parent_inode, entry_name)
            removed_directory_entries.add(key)
            modified = True
            continue
        if issue.kind == 'link-count-mismatch' and issue.inode is not None:
            inode_number = int(issue.inode)
            if inode_number in repaired_links:
                continue
            expected_nlink = issue.details.get('expected')
            if not isinstance(expected_nlink, int):
                continue
            write_ufs_inode_nlink(image, filesystem, inode_number, expected_nlink)
            repaired_links.add(inode_number)
            modified = True
            continue
        if issue.kind == 'bitmap-mismatch':
            rebuilt_bitmaps = True
            rebuilt_summaries = True
            modified = True
            continue
        if issue.kind in {'summary-information-mismatch', 'summary-mismatch', 'superblock-summary-mismatch'}:
            rebuilt_summaries = True
            modified = True
            continue
        inode_number = int(issue.inode)
        if inode_number in seen_inodes:
            continue
        clear_ufs_inode(image, filesystem, inode_number)
        seen_inodes.add(inode_number)
        cleared_inodes.append(inode_number)
        modified = True
    if rebuilt_bitmaps:
        fs = filesystem.details
        ipg = int(fs['ipg'])
        ncg = int(fs['ncg'])
        seen_blocks: set[int] = set()
        inode_in_use: set[int] = {0, 1}
        for cg in range(ncg):
            seen_blocks.update(range(ufs_cgbase(fs, cg), ufs_cgdmin(fs, cg)))
        for cg in range(ncg):
            for inode_index in range(ipg):
                inode_number = (cg * ipg) + inode_index
                if inode_number < 2:
                    continue
                inode = read_ufs_inode(image, filesystem.start_offset, fs, inode_number)
                if inode is None or int(inode['mode']) == 0:
                    continue
                inode_in_use.add(inode_number)
                _scan_inode_blocks(image, filesystem, fs, inode_number, inode, seen_blocks, [])
        for cg in range(ncg):
            cg_bytes = read_cg_block(image, filesystem, cg)
            dbase = ufs_cgbase(fs, cg)
            cg_ndblk = u32(cg_bytes, UFS_CG_NDBLK_OFFSET)
            data_frag_start = ufs_cgdmin(fs, cg) - dbase
            for inode_index in range(ipg):
                inode_number = (cg * ipg) + inode_index
                should_be_used = inode_number in inode_in_use
                set_ufs_inode_state(cg_bytes, inode_index, used=should_be_used)
            for frag_index in range(data_frag_start, cg_ndblk):
                set_frag_state(cg_bytes, frag_index, free=(dbase + frag_index) not in seen_blocks)
            write_cg_block(image, filesystem, cg, cg_bytes)
    if cleared_inodes or repaired_links or rebuilt_summaries:
        recompute_ufs_summary_counts(image, filesystem)
    return cleared_inodes, modified


def repair_ufs_image(image_path: Path, slice_selector: str) -> tuple[list[int], UFSFsckReport]:
    _, slice_fs = inspect_slice_by_selector(image_path, slice_selector)
    slice_image = bytearray(read_slice_bytes(image_path, slice_fs.absolute_start_sector, slice_fs.sector_count))
    filesystem = detect_ufs(slice_image)[0]
    initial_report = analyze_ufs_filesystem(
        slice_image,
        filesystem,
        image_label=str(image_path),
        slice_label=slice_selector,
    )
    cleared_inodes, modified = repair_ufs_filesystem(slice_image, filesystem, initial_report)
    if modified:
        with image_path.open('r+b') as image_file:
            image_file.seek(slice_fs.absolute_start_sector * SECTOR_SIZE)
            image_file.write(slice_image)
    final_report = analyze_ufs_filesystem(
        slice_image,
        filesystem,
        image_label=str(image_path),
        slice_label=slice_selector,
    )
    return cleared_inodes, final_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run host-side SVR4 UFS fsck-style consistency checks.')
    parser.add_argument('image', type=Path, help='Path to the raw disk image.')
    parser.add_argument('--slice', default='1', help='Slice index or tag name, for example 1 or root.')
    parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON.')
    parser.add_argument('--fix', action='store_true', help='Clear fixable partially allocated free inodes and rewrite the image.')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cleared_inodes: list[int] = []
    if args.fix:
        cleared_inodes, report = repair_ufs_image(args.image.resolve(), args.slice)
    else:
        report = analyze_ufs_image(args.image.resolve(), args.slice)
    payload = {
        'image': report.image,
        'slice': report.slice,
        'allocated_inodes': report.allocated_inodes,
        'issue_count': len(report.issues),
        'cleared_inodes': cleared_inodes,
        'superblock_totals': report.superblock_totals,
        'recomputed_totals': report.recomputed_totals,
        'issues': [asdict(issue) for issue in report.issues],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f'image: {report.image}')
        print(f'slice: {report.slice}')
        print(f'allocated inodes: {report.allocated_inodes}')
        if cleared_inodes:
            print(f'cleared free dirty inodes: {len(cleared_inodes)}')
        print(f'issues: {len(report.issues)}')
        for issue in report.issues[:50]:
            inode = '' if issue.inode is None else f' inode={issue.inode}'
            block = '' if issue.block is None else f' block={issue.block}'
            details = '' if not issue.details else f' details={issue.details}'
            print(f'- {issue.kind}{inode}{block}: {issue.message}{details}')
        if len(report.issues) > 50:
            print(f'... {len(report.issues) - 50} more issues omitted')
    return 1 if report.issues else 0


if __name__ == '__main__':
    raise SystemExit(main())