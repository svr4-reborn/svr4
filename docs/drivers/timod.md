# TLI Compatibility Module

The `timod` module in `uts/i386/io/timod.c` is the TLI/XTI compatibility module layered over STREAMS transport providers. It is used by user-space TLI/XTI callers and by KTLI setup paths that need a TLI-style control surface.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/timod.c` |
| Handler prefix | `tim` |
| Mask / Type | `-` / `Sif` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| User-visible major | None; `timod` is pushed as a STREAMS module |

## Current Role

- Provides the generic TLI/XTI module layer over transport endpoints.
- Lets TLI callers issue bind, connect, option, and name operations without using `sockmod`.
- Is pushed by KTLI setup helpers when the opened transport stream does not already have it.
- May be popped by in-kernel RPC/NFS clients after setup when they choose to send runtime traffic directly to the transport stream.