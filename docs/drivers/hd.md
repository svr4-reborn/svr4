# AT Hard Disk Driver

The `hd` driver is the built-in AT hard-disk driver under `uts/arch/at/i386/io/hd.c`. In the default full AT386 configuration it is both the primary block device and a character device, and the generated `sassign` metadata points the system `root`, `swap`, `dump`, and `pipe` devices at `hd` minors.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/hd.c` |
| `mdev` record | `hd Iocrwiz iHrobcf hd 0 0 1 2 -1` |
| Block major | `0` |
| Character major | `0` |
| Configured `sdev` record | `hd Y 2 5 1 14 1f0 1ff 0 0` |
| Handler prefix | `hd` |
| Static `node` metadata | None staged |

The single staged controller record gives the classic primary AT disk IO window `0x1f0-0x1ff` and interrupt vector `14`, with two configured units.

## What The Driver Exposes

From the generated switch-table metadata and the implementation source, `hd` contributes:

- `hdopen()` and `hdclose()` for device open and close.
- `hdstrategy()` for block IO scheduling.
- `hdioctl()` for control operations.
- `hdsize()` through the `z` mask handling in the generated block switch.
- `hdprint()` for error reporting via `bdevsw`.
- `hdinit()` through the `I` mask during generated initialization.

The source also contains explicit async-IO related handling through `raioctl()` calls in `hdioctl()`, so this driver is not just a minimal synchronous disk strategy routine.

## Source-Level Responsibilities

The top of `hd.c` makes the driver’s scope fairly clear:

- It pulls in `sys/vtoc.h`, `sys/fdisk.h`, and `sys/bootinfo.h`, so it sits at the geometry and partitioning boundary as well as the raw transport boundary.
- It carries detailed bad-block handling, alternate-sector, ECC, and verification paths.
- It uses `MAXXFER` and breakup logic, which matches the block-driver role signaled by the `b` type flag.

In practice this is the driver to look at for:

- boot-time disk discovery on AT IDE hardware
- root and swap device selection
- partition-table and VTOC interaction
- block remapping and bad-block recovery behavior

## Notes For Bringup

- The default configured kernel expects `hd` to exist even when the reduced boot-floppy profile excludes it.
- Because `root`, `swap`, `dump`, and `pipe` all default to `hd` in `master.d/sassign`, failures here tend to surface as system-level storage failures rather than as one isolated device problem.
- For debugging, `hdopen()`, `hdstrategy()`, and `hdioctl()` are the best first anchor points.

## Related Files

- `uts/arch/at/i386/master.d/hd/mdev`
- `uts/arch/at/i386/master.d/hd/sdev`
- `uts/i386/master.d/sassign`