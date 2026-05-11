# Real-Time Clock Driver

The `rtc` driver in `uts/arch/at/i386/io/rtc.c` is the PC AT calendar-clock driver. It is a character device used for reading and writing the hardware clock rather than for data transport.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/rtc.c` |
| `mdev` record | staged as character driver `rtc` on major `8` |
| Character major | `8` |
| Configured `sdev` record | `rtc Y 1 5 1 8 0 0 0 0` |
| Handler prefix | `rtc` |
| Static `node` metadata | None staged |

## What The Driver Exposes

The source provides a very small interface surface:

- `rtcinit()` to set the chip up for periodic update interrupts.
- `rtcopen()` with privilege checks for writers.
- `rtcread()` and `rtcwrite()`, both trivial in this file.
- `rtcioctl()` as the real operational interface.

`rtcioctl()` handles at least two commands:

- `RTCRTIME` to fetch the RTC register set
- `RTCSTIME` to update the RTC register set

The write path is privilege-gated through `drv_priv()`.

## Behavioral Notes

The source header documents two strong compatibility choices:

- the chip is treated as local time rather than GMT
- the chip is used in BCD mode rather than binary mode

Those choices are explicitly framed as PC-DOS compatibility requirements, which makes this driver a compatibility boundary as much as a hardware boundary.

## When To Read This Driver

`rtc.c` is the right place to inspect when debugging:

- hardware clock drift or readout issues
- boot-time time initialization behavior
- privileged time-setting semantics
- differences between the system clock and the RTC contents

## Related Files

- `uts/arch/at/i386/master.d/rtc/mdev`
- `uts/arch/at/i386/master.d/rtc/sdev`