# UDP Endpoint

The `udp` endpoint is the clone-backed UDP protocol entry point for the STREAMS TCP/IP stack. Its implementation lives in `uts/i386/netinet/udp_main.c`.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/udp_main.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone udp c udp` |
| Dedicated major | None; shares clone-open machinery |

## Current Role

- Provides the connectionless datagram transport endpoint.
- Reaches userspace through clone-backed naming instead of a dedicated major.
- Is one of the core transport endpoints in the network stack.