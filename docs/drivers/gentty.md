# Generic TTY Driver

The `gentty` driver in `uts/i386/io/gentty.c` is the generic/indirect tty driver. It routes access to the session-controlling tty through a generic character-device entry point.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/gentty.c` |
| Handler prefix | `sy` |
| Character major | `16` |
| Mask / Type | `orwi` / `icorf` |
| Configured units | `1` |
| Static node metadata | None staged |

## Current Role

- Provides indirection to the controlling tty rather than a concrete hardware tty.
- Sits on top of the tty/session model instead of managing hardware ports directly.
- Is the right place to inspect when `/dev/tty`-style behavior is in question.