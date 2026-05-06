from __future__ import annotations

from host_tools.fs.bfs import detect_bfs, list_bfs_root
from host_tools.fs.ufs import detect_ufs, list_ufs_root

from .structures import SliceFilesystem


def select_slice_filesystem(image: bytes) -> tuple[str, int, list[dict[str, int | str]]]:
    ufs_candidates = detect_ufs(image)
    bfs_candidates = detect_bfs(image)

    for candidate in ufs_candidates:
        if candidate.start_offset == 0:
            return 'ufs', candidate.start_offset, list_ufs_root(image, candidate)
    for candidate in bfs_candidates:
        if candidate.start_offset == 0:
            return 'bfs', candidate.start_offset, list_bfs_root(image, candidate)
    if ufs_candidates:
        candidate = ufs_candidates[0]
        return 'ufs', candidate.start_offset, list_ufs_root(image, candidate)
    if bfs_candidates:
        candidate = bfs_candidates[0]
        return 'bfs', candidate.start_offset, list_bfs_root(image, candidate)
    return None, 0, []


def probe_slice_filesystem(
    slice_index: int,
    tag: int,
    start_sector: int,
    absolute_start_sector: int,
    sector_count: int,
    image: bytes,
) -> SliceFilesystem:
    filesystem, filesystem_offset, root_entries = select_slice_filesystem(image)

    return SliceFilesystem(
        slice_index=slice_index,
        tag=tag,
        start_sector=start_sector,
        absolute_start_sector=absolute_start_sector,
        sector_count=sector_count,
        filesystem=filesystem,
        filesystem_offset=filesystem_offset,
        root_entries=root_entries,
    )