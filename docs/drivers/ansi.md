# ANSI Parser Module

The `ansi` module in `uts/i386/io/ansi.c` is the IWE ANSI escape-sequence parser. It translates X3.64/ANSI terminal control sequences into console/display operations for the AT386 console stack.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/ansi.c` |
| Handler prefix | `ansi` |
| Mask / Type | `-` / `iSf` |
| User-visible major | None; documented in the catalog as a STREAMS-only module |

## Current Role

- Parses ANSI escape/control traffic for the console path.
- Lives in the console module stack alongside `char`, `kd`, and the display/video support pieces.
- Is a module-level component rather than a standalone user-opened device.