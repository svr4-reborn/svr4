# Line Printer Driver

The `lp` driver in `uts/arch/at/i386/io/lp.c` is the configured line-printer driver for the default AT386 kernel. Like `asy`, it is a STREAMS-backed character driver rather than a block device.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/lp.c` |
| `mdev` record | `lp Ioc iHcSf lp 0 7 1 2 -1` |
| Character major | `7` |
| Configured `sdev` record | `lp Y 1 3 1 7 378 37f 0 0` |
| Handler prefix | `lp` |
| STREAMS export | `struct streamtab lpinfo` |
| Static `node` metadata | `lp0`, `lp`, `lp1`, `lp2` |

The configured controller record matches the usual parallel-port IO window `0x378-0x37f` on vector `7`.

## What The Driver Exposes

The generated configuration wires `lp` as a character STREAMS device with:

- `lpopen()` and `lpclose()`.
- a STREAMS `streamtab` named `lpinfo`.
- write-side queue handling for queued printer output.
- initialization via the `I` mask.

The implementation is very much oriented around queued output, termio-like control, and printer presence/open-state tracking rather than around generic file-style buffered IO.

## Node Naming

The staged `node` file declares a small family of printer aliases:

- `lp0`
- `lp`
- `lp1`
- `lp2`

The alias `lp` to minor `0` is the main compatibility detail to remember.

## Source-Level Responsibilities

The implementation identifies itself as the line-printer driver and uses:

- STREAMS queue setup through `lpinfo`
- `strtty` state per device
- watchdog timing to avoid output hangs
- printer-presence checks before open

This is the place to look when debugging:

- printer open failures
- queued write drain behavior
- STREAMS message handling on the printer path
- parallel-port presence or timeout issues

## Related Files

- `uts/arch/at/i386/master.d/lp/mdev`
- `uts/arch/at/i386/master.d/lp/sdev`
- `uts/arch/at/i386/master.d/lp/node`