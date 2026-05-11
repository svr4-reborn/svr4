# Raw IP Endpoint

The `rawip` endpoint is the clone-backed raw-IP entry point for the STREAMS network stack. Its protocol implementation is centered in `uts/i386/netinet/raw_ip_main.c`.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/raw_ip_main.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone rawip c rawip` |
| Dedicated major | None; shares clone-open machinery |

## Current Role

- Provides raw IP datagram access for protocol consumers that operate below the usual transport abstractions.
- Uses clone-open endpoint naming rather than a dedicated device major.
- Is a protocol/service endpoint, not a hardware interface.