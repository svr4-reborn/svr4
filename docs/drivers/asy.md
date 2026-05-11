# Asynchronous Serial Driver

The `asy` driver in `uts/arch/at/i386/io/asy.c` is the default AT386 serial and asynchronous console driver. It is a STREAMS driver with a `streamtab` (`asyinfo`) and a large bank of staged device nodes for terminal-style access.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/asy.c` |
| `mdev` record | `asy Ioc iHcSf asy 0 3 1 6 -1` |
| Character major range | `3` |
| Configured ports | `6` total, staged as six separate `sdev` entries |
| Handler prefix | `asy` |
| STREAMS export | `struct streamtab asyinfo` |
| Static `node` metadata | `tty00`, `term/00`, `tty00s`, `tty00h`, and corresponding families through port `05` |

The staged `sdev` records configure six serial ports with these IO ranges and vectors:

- `0x3f8-0x3ff`, vector `4`
- `0x2f8-0x2ff`, vector `3`
- `0x3e8-0x3ef`, vector `4`
- `0x2e8-0x2ef`, vector `3`
- `0x3220-0x3227`, vector `3`
- `0x3228-0x322f`, vector `3`

## What The Driver Exposes

`asy` is a character-only STREAMS serial driver. In this tree it contributes:

- STREAMS open and close through `asyopen()` and `asyclose()`.
- STREAMS read/write-side queue handling through the `qinit` pairs behind `asyinfo`.
- terminal control and serial-line configuration logic.
- interrupt-driven receive and transmit handling.
- per-device `tty`/`strtty` state.

The presence of both `c` and `S` in the type flags matters here: the driver is reachable both through `cdevsw` and as a STREAMS endpoint.

## Node Naming

The staged `node` file is unusually rich and is worth preserving because userspace paths depend on it. For each configured minor, the metadata declares names such as:

- `tty00`
- `term/00`
- `tty00s`
- `tty00h`

with the same pattern repeated through `tty05` and `term/05`.

That means the node metadata is part of the driver ABI here, not just a packaging convenience.

## Source-Level Responsibilities

The first part of `asy.c` shows the main design points:

- It identifies itself as the asynchronous console driver.
- It uses STREAMS and `strtty` rather than a simpler raw character-only interface.
- It keeps watchdog timing, baud-rate tables, ring buffers, and interrupt-level buffering.
- It explicitly notes that the driver runs at `spl` 7 and cannot do STREAMS work directly at interrupt level.

This is the right place to look for:

- serial console bringup
- tty node behavior
- baud-rate and line-discipline integration
- interrupt and buffering problems on the serial path

## Related Files

- `uts/arch/at/i386/master.d/asy/mdev`
- `uts/arch/at/i386/master.d/asy/sdev`
- `uts/arch/at/i386/master.d/asy/node`