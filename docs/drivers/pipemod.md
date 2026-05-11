# Pipe Flush Module

The `pipemod` module in `uts/i386/io/pipemod.c` is the STREAMS pipe-flushing module. It swaps the read/write flush semantics needed for proper STREAMS-based pipe behavior.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/pipemod.c` |
| Handler prefix | `pipe` |
| Mask / Type | `-` / `Smio` |
| User-visible major | None; documented in the catalog as a STREAMS-only module |

## Current Role

- Adjusts flush semantics so STREAMS pipes behave correctly.
- Belongs to plumbing/support code rather than endpoint or hardware code.
- Is a useful anchor when pipe behavior differs from expectation in the STREAMS stack.