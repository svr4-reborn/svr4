from __future__ import annotations

from dataclasses import dataclass

from .bfs import bfs_filesystem_stats
from .bfs import bfs_root_inode
from .bfs import create_bfs_file
from .bfs import detach_bfs_path
from .bfs import finalize_bfs_unlinked_inode
from .bfs import iter_bfs_directory_entries
from .bfs import read_bfs_dirent
from .bfs import read_bfs_file
from .bfs import read_bfs_path_bytes
from .bfs import remove_bfs_path
from .bfs import rename_bfs_path
from .bfs import replace_bfs_inode_data
from .bfs import resolve_bfs_path
from .bfs import write_bfs_inode_fields
from .bfs import apply_bfs_replacement
from .common import BFS_ROOT_INODE, FilesystemCandidate


@dataclass
class BFSBackend:
    image: bytearray
    filesystem: FilesystemCandidate

    def lookup(self, path: str) -> tuple[int, dict[str, int]]:
        resolved = resolve_bfs_path(self.image, self.filesystem, path)
        if resolved is None:
            raise SystemExit(f'error: could not resolve {path} inside the bfs filesystem')
        return resolved

    def getattr(self, path: str) -> dict[str, int]:
        inode_number, inode = self.lookup(path)
        return {'inode': inode_number, **inode}

    def getattr_inode(self, inode_number: int) -> dict[str, int]:
        inode = read_bfs_dirent(self.image, self.filesystem.start_offset, inode_number)
        if inode is None or int(inode['d_ino']) == 0:
            raise SystemExit(f'error: bfs inode {inode_number} does not exist')
        return inode

    def readdir(self, path: str) -> list[dict[str, int | str]]:
        if path != '/':
            raise SystemExit(f'error: {path} is not a BFS directory')
        return iter_bfs_directory_entries(self.image, self.filesystem)

    def read(self, path: str) -> bytes:
        return read_bfs_path_bytes(self.image, self.filesystem, path)[2]

    def read_inode(self, inode_number: int) -> bytes:
        if inode_number == BFS_ROOT_INODE:
            return read_bfs_file(self.image, self.filesystem, bfs_root_inode(self.image, self.filesystem))
        inode = self.getattr_inode(inode_number)
        return read_bfs_file(self.image, self.filesystem, inode)

    def write(self, path: str, data: bytes) -> dict[str, int | str]:
        return apply_bfs_replacement(self.image, self.filesystem, path, data)

    def write_inode(self, inode_number: int, data: bytes) -> dict[str, int | str]:
        return replace_bfs_inode_data(self.image, self.filesystem, inode_number, data)

    def create(self, path: str, data: bytes, *, mode: int = 0o644, uid: int = 0, gid: int = 0, timestamp: int | None = None) -> dict[str, int | str]:
        return create_bfs_file(self.image, self.filesystem, path, data, mode=mode, uid=uid, gid=gid, timestamp=timestamp)

    def unlink(self, path: str) -> dict[str, int | str]:
        return remove_bfs_path(self.image, self.filesystem, path)

    def detach(self, path: str) -> dict[str, int | str]:
        return detach_bfs_path(self.image, self.filesystem, path)

    def finalize_unlinked_inode(self, inode_number: int) -> dict[str, int]:
        return finalize_bfs_unlinked_inode(self.image, self.filesystem, inode_number)

    def rename(self, source_path: str, target_path: str, *, detach_target: bool = False) -> dict[str, int | str]:
        return rename_bfs_path(self.image, self.filesystem, source_path, target_path, detach_target=detach_target)

    def setattr_inode(
        self,
        inode_number: int,
        *,
        mode: int | None = None,
        uid: int | None = None,
        gid: int | None = None,
        nlink: int | None = None,
        atime: int | None = None,
        mtime: int | None = None,
        ctime: int | None = None,
    ) -> dict[str, int]:
        return write_bfs_inode_fields(
            self.image,
            self.filesystem,
            inode_number,
            mode=mode,
            uid=uid,
            gid=gid,
            nlink=nlink,
            atime=atime,
            mtime=mtime,
            ctime=ctime,
        )

    def statfs(self) -> dict[str, int]:
        return bfs_filesystem_stats(self.image, self.filesystem)