# Character Translation Module

The `char` module in `uts/i386/io/char.c` is the IWE character and scan-code translation module. It performs keyboard/input translation and related screen/console character handling in the AT386 console stack.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/char.c` |
| Handler prefix | `char` |
| Mask / Type | `-` / `iSf` |
| User-visible major | None; documented in the catalog as a STREAMS-only module |

## Current Role

- Translates keyboard and character-stream data for the console pipeline.
- Pairs naturally with `ansi` and `kd` in the console stack.
- Exists as module plumbing rather than as a separate opened device node.