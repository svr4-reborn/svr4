# TCP Endpoint

The `tcp` endpoint is the clone-backed TCP protocol entry point for the STREAMS TCP/IP stack. Its core implementation lives in `uts/i386/netinet/tcp_main.c`.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/tcp_main.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone tcp c tcp`; `tcp inet/tcp000 c 000`; `tcp inet/tcp001 c 001`; further `inet/tcp*` entries are also staged |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone` for `tcp`; `tcp` target metadata also declares the `inet/tcp*` aliases |

## Current Role

- Provides the connection-oriented reliable-stream transport endpoint.
- When enabled, uses clone-backed naming plus a bank of `inet/tcp*` node names.
- Is a key protocol endpoint when debugging userspace socket/TLI traffic over TCP.