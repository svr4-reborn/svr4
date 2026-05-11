# Channel Multiplexer Driver

The `cmux` driver in `uts/arch/at/i386/io/chanmux.c` is the IWE channel multiplexer. It multiplexes secondary input devices across a primary channel set and appears as a STREAMS-capable character device in the configured kernel.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/chanmux.c` |
| Handler prefix | `cmux` |
| Character major | `5` |
| Mask / Type | `s` / `ifrSc` |
| Configured units | `1` |
| Static node metadata | None staged |

## Current Role

- Multiplexes channel-oriented input streams for the AT386 environment.
- Lives in the AT platform IO tree rather than the generic STREAMS module set.
- Is part of the older windowing/input plumbing rather than the modernized userspace bringup path.