# Generic Video Dispatcher

The `gvid` driver in `uts/arch/at/i386/io/genvid.c` is the generic video-device dispatcher for the AT386 console stack. It routes the generic video entry point to the configured concrete video implementation.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/genvid.c` |
| Handler prefix | `gvid` |
| Character major | `29` |
| Mask / Type | `ocrwi` / `icofr` |
| Configured units | `1` |
| Static node metadata | None staged |

## Current Role

- Provides an indirect, generic video-facing device entry point.
- Separates user/kernel consumers of generic video operations from the concrete AT display backend.
- Is most relevant when the active video path behaves differently from the generic `/dev/video` style expectations.