# TTY Compatibility Module

The `ttcompat` module in `uts/i386/io/ttcompat.c` is the tty-compatibility module. It intercepts older V7/4BSD/XENIX-style tty ioctls and translates them into the STREAMS-oriented terminal model.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/ttcompat.c` |
| Handler prefix | `ttco` |
| Mask / Type | `-` / `Smio` |
| User-visible major | None; documented in the catalog as a STREAMS-only module |

## Current Role

- Preserves older tty ioctl compatibility on top of the STREAMS tty stack.
- Is most relevant when historical userspace expects older tty control conventions.
- Exists as translation/plumbing logic rather than as a standalone endpoint.