from __future__ import annotations

from dataclasses import dataclass

from .common import FilesystemCandidate
from .ufs import apply_ufs_replacement
from .ufs import create_ufs_file
from .ufs import iter_ufs_directory_entries
from .ufs import link_ufs_path
from .ufs import make_ufs_directory
from .ufs import read_ufs_path_range
from .ufs import remove_ufs_directory
from .ufs import rename_ufs_path
from .ufs import resolve_ufs_path
from .ufs import symlink_ufs_path
from .ufs import ufs_is_symlink
from .ufs import unlink_ufs_path


@dataclass
class UFSBackend:
    image: bytearray
    filesystem: FilesystemCandidate

    def lookup(self, path: str) -> tuple[int, dict[str, int | list[int]]]:
        resolved = resolve_ufs_path(self.image, self.filesystem, path)
        if resolved is None:
            raise SystemExit(f'error: could not resolve {path} inside the ufs filesystem')
        return resolved

    def getattr(self, path: str) -> dict[str, int]:
        inode_number, inode = self.lookup(path)
        return {
            'inode': inode_number,
            'mode': int(inode['mode']),
            'nlink': int(inode['nlink']),
            'uid': int(inode['uid']),
            'gid': int(inode['gid']),
            'size': int(inode['size']),
            'blocks': int(inode['blocks']),
        }

    def readdir(self, path: str) -> list[dict[str, int | str]]:
        _, inode = self.lookup(path)
        return iter_ufs_directory_entries(self.image, self.filesystem, inode)

    def read(self, path: str, offset: int = 0, size: int | None = None) -> bytes:
        return read_ufs_path_range(self.image, self.filesystem, path, offset=offset, size=size)[2]

    def write(self, path: str, data: bytes) -> dict[str, int | str]:
        return apply_ufs_replacement(self.image, self.filesystem, path, data)

    def create(self, path: str, data: bytes, mode: int = 0o644) -> dict[str, int | str]:
        return create_ufs_file(self.image, self.filesystem, path, data, mode=mode)

    def mkdir(self, path: str, mode: int = 0o755) -> dict[str, int | str]:
        return make_ufs_directory(self.image, self.filesystem, path, mode=mode)

    def unlink(self, path: str) -> dict[str, int | str]:
        return unlink_ufs_path(self.image, self.filesystem, path)

    def rmdir(self, path: str) -> dict[str, int | str]:
        return remove_ufs_directory(self.image, self.filesystem, path)

    def link(self, source_path: str, target_path: str) -> dict[str, int | str]:
        return link_ufs_path(self.image, self.filesystem, source_path, target_path)

    def rename(self, source_path: str, target_path: str) -> dict[str, int | str]:
        return rename_ufs_path(self.image, self.filesystem, source_path, target_path)

    def symlink(self, target: str, link_path: str) -> dict[str, int | str]:
        return symlink_ufs_path(self.image, self.filesystem, target, link_path)

    def readlink(self, path: str) -> str:
        _, inode, data = read_ufs_path_range(self.image, self.filesystem, path)
        if not ufs_is_symlink(inode):
            raise SystemExit(f'error: {path} is not a UFS symbolic link')
        return data.decode('ascii')