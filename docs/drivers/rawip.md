# Raw IP Endpoint

The `rawip` endpoint is the clone-backed raw-IP entry point for the STREAMS network stack. Its protocol implementation is centered in `uts/i386/netinet/raw_ip_main.c`.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/raw_ip_main.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone rawip c rawip` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `rawip` STREAMS `cdevsw` entry |

## Current Role

- Provides raw IP datagram access for protocol consumers that operate below the usual transport abstractions.
- When enabled, uses clone-open public naming; the target remains the raw IP STREAMS `cdevsw` entry.
- Is a protocol/service endpoint, not a hardware interface.