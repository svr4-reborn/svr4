# AT Floppy Disk Driver

The `fd` driver under `uts/arch/at/i386/io/fd.c` is the configured floppy controller driver for the default AT386 kernel. It appears in both `bdevsw` and `cdevsw`, which matches how SVR4 historically used floppy devices for both block-style filesystem access and character-style administrative access.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/fd.c` |
| `mdev` record | `fd Iocrwi iHrbcf fd 1 1 1 2 2` |
| Block major | `1` |
| Character major | `1` |
| Configured `sdev` record | `fd Y 1 4 2 6 3f0 3f7 0 0` |
| Handler prefix | `fd` |
| Static `node` metadata | None staged |

The configured controller record matches the usual floppy-controller IO range `0x3f0-0x3f7` and vector `6`.

## What The Driver Exposes

From the generated metadata and the implementation source, `fd` contributes:

- `fdopen()` and close handling.
- `fdstrategy()` for buffered block IO.
- `fdioctl()` for formatting and drive-control operations.
- initialization via the `I` mask.

The source also sets `fddevflag = D_DMA`, which is the clearest high-level summary of how the driver expects to move data.

## Source-Level Responsibilities

The implementation is strongly geometry- and media-oriented:

- The file begins with detailed tables for double-density, quad-density, and 3.5-inch floppy characteristics.
- It tracks CMOS-reported drive types.
- It carries explicit controller-state and motor-door handling.
- It depends on DMA support headers and the AT floppy controller support code.

This is the driver to inspect for:

- floppy geometry selection and auto-detection
- media-format IOCTL handling
- DMA path issues on legacy removable media
- boot-media bringup when reproducing the original install path

## Notes For Bringup

- The floppy build profile is still highly relevant to this project, so regressions here can block reproducing the current boot-media workflow.
- Because the driver is both block and character facing, `fdstrategy()` and `fdioctl()` are usually the most useful first breakpoints.
- The lack of staged `node` metadata means the current documentation should treat the switch-table presence as authoritative, not `/dev` naming.

## Related Files

- `uts/arch/at/i386/master.d/fd/mdev`
- `uts/arch/at/i386/master.d/fd/sdev`
- `docs/boot-floppy-tooling.md`