# Socket Compatibility Module

The `sockmod` module in `uts/i386/io/sockmod.c` is the BSD socket compatibility layer for STREAMS transports. User-space socket code opens a transport endpoint and pushes `sockmod` so socket operations can be expressed as TPI requests and socket-facing state can be maintained above the provider.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/sockmod.c` |
| Handler prefix | `sock` |
| Mask / Type | `ico` / `iSf` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| User-visible major | None; `sockmod` is pushed as a STREAMS module |

## Current Role

- Sends `T_INFO_REQ` on open and records provider capabilities from `T_INFO_ACK`.
- Maintains socket-facing state such as cached local and peer addresses, options, connected or bound state, and shutdown state.
- Translates socket operations and ioctls into TPI requests or provider queries.
- Converts upstream TPI indications into BSD-socket-facing behavior for callers above the stream.