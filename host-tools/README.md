# Host Tools

This directory contains generic host-side utilities for working with raw SVR4
boot and disk images.

The initial focus is raw disk image inspection so later BFS/UFS tools can
operate directly on the installed SVR4 disk layout.

Image interaction is now expected to happen through the FUSE layer. The CLI is
kept only for offline inspection and image construction tasks that are still
useful before mounting or bootstrapping an image.

Install for packaging or builder integration:

```sh
python3 -m pip install .
python3 -m pip install '.[fuse]'
python3 -m build
```

Once installed, the package exposes console entry points that are stable enough
for a host-tool pipeline to call directly:

```sh
svr4-disk-image inspect build/boot-media/att_unix_reference_install.raw
svr4-bfs-mount build/boot-media/att_unix_reference_install.raw /tmp/svr4-stand --slice stand
svr4-ufs-mount build/boot-media/att_unix_reference_install.raw /tmp/svr4-root --slice root
```

This is intended to be usable from builder systems such as Jinx or xbstrap,
where the host tool can be installed into the build environment and invoked as a
normal command instead of through repo-local script paths.

Repository-local usage:

```sh
python3 host-tools/disk_image.py inspect build/boot-media/att_unix_reference_install.raw
python3 host-tools/disk_image.py format-bfs build/boot-media/test-skeleton.raw \
	--slice stand \
	--file unix=build/boot-media/unix \
	--file hdboot=build/boot-media/hdboot \
	--output build/boot-media/test-stand.raw
python3 host-tools/disk_image.py create-skeleton \
	--output build/boot-media/test-skeleton.raw \
	--cylinders 16 \
	--heads 4 \
	--sectors 17 \
	--slice 0:backup:1:1087:0x201 \
	--slice 1:root:64:128:0x200 \
	--slice 10:stand:32:32:0x200
python3 host-tools/ufs_mount.py build/boot-media/att_unix_reference_install.raw /tmp/svr4-root \
	--slice root
python3 host-tools/bfs_mount.py build/boot-media/att_unix_reference_install.raw /tmp/svr4-stand \
	--slice stand
```

Current commands:

- `inspect`: decode the MBR, active UNIX partition, pdinfo, VTOC, and detected BFS/UFS slices.
- `format-bfs`: copy a raw image, format one slice as BFS, and populate its root directory from host files.
- `create-skeleton`: create a blank raw disk image with MBR, pdinfo, and VTOC metadata.

FUSE entrypoint:

- `bfs_mount.py`: mount a detected BFS slice from a raw disk image through `pyfuse3`. The mount path exposes the flat `/stand` namespace directly, supports regular-file mutation, and flushes changes back into the selected raw-image slice.
- `ufs_mount.py`: mount a detected UFS slice from a raw disk image through `pyfuse3`. The mount path uses the writable UFS core directly, flushes changes back into the selected raw-image slice, runs with `direct_io`, and defaults the entry/attribute cache timeout to one second unless overridden with `--cache-timeout`.

The filesystem logic under [host-tools/host_tools/fs/ufs.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/ufs.py), [host-tools/host_tools/fs/ufs_directory.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/ufs_directory.py), [host-tools/host_tools/fs/ufs_lowlevel.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/ufs_lowlevel.py), and [host-tools/host_tools/fs/ufs_backend.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/ufs_backend.py) remains the active path for writable UFS behavior.

There is now an equivalent BFS path in [host-tools/host_tools/fs/bfs.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/bfs.py), [host-tools/host_tools/fs/bfs_backend.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/bfs_backend.py), and [host-tools/host_tools/fs/bfs_fuse.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/bfs_fuse.py). It keeps BFS flat, exposes only the root directory, and supports regular-file create, write, rename, unlink, and truncate semantics suitable for the `/stand` slice.

There is now a thin backend wrapper for future FUSE work in [host-tools/host_tools/fs/ufs_backend.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/ufs_backend.py). It exposes filesystem-style operations such as `lookup`, `getattr`, `readdir`, `read`, `write`, `create`, `mkdir`, `unlink`, `rmdir`, `link`, `rename`, `symlink`, and `readlink` over an in-memory UFS image slice, and the concrete `pyfuse3` frontend lives in [host-tools/host_tools/fs/ufs_fuse.py](/home/alexander/projects/classic_unix_playing/svr4-src/host-tools/host_tools/fs/ufs_fuse.py).