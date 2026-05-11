# Connection Establishment Module

The `connld` module in `uts/i386/io/connld.c` is the STREAMS connection-establishment module used in pipe/FIFO-style plumbing. It provides the unique connection behavior expected by the historical STREAMS stack.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/connld.c` |
| Handler prefix | `conn` |
| Mask / Type | `-` / `Simo` |
| User-visible major | None; documented in the catalog as a STREAMS-only module |

## Current Role

- Participates in STREAMS-based connection setup rather than endpoint data transport.
- Shows up most often in pipe/FIFO and STREAMS plumbing paths.
- Is a module-level component, not a standalone driver entry in the user-visible device-major tables.