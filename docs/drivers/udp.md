# UDP Endpoint

The `udp` endpoint is the clone-backed UDP protocol entry point for the STREAMS TCP/IP stack. Its implementation lives in `uts/i386/netinet/udp_main.c`.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/udp_main.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone udp c udp` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `udp` STREAMS `cdevsw` entry |

## Current Role

- Provides the connectionless datagram transport endpoint.
- When enabled, reaches userspace through clone-backed public naming; clone-open dispatches to the UDP STREAMS `cdevsw` entry.
- Is one of the core transport endpoints in the network stack.