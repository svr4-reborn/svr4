# Terminal Line Discipline Module

The `ldterm` module in `uts/i386/io/ldterm.c` is the standard STREAMS terminal line discipline. It implements terminal input processing, output formatting, and job-control-facing line discipline behavior.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/ldterm.c` |
| Handler prefix | `ldtr` |
| Mask / Type | `oci` / `iSf` |
| User-visible major | None; documented in the catalog as a STREAMS-only module |

## Current Role

- Provides the mainstream STREAMS tty line-discipline behavior.
- Sits between tty-like endpoints and higher-level terminal consumers.
- Is one of the key modules to inspect when termio/termios-style behavior diverges from expectations.