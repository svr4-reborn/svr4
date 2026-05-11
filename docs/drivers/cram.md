# CMOS RAM Driver

The `cram` driver in `uts/arch/at/i386/io/cram.c` is the PC AT CMOS RAM device. It exposes battery-backed configuration storage through a character-device interface.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/cram.c` |
| Handler prefix | `cmos` |
| Character major | `18` |
| Mask / Type | `ocrwi` / `icorf` |
| Configured units | `1` |
| Static node metadata | None staged |

## Current Role

- Provides read/write access to CMOS-backed machine configuration state.
- Sits next to the RTC/AT platform support code rather than the general STREAMS or tty paths.
- Is best treated as platform support plumbing for AT386-specific machine state.