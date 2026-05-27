# ICMP Endpoint

The `icmp` endpoint is the clone-backed ICMP protocol entry point for the STREAMS TCP/IP stack. Its implementation lives in `uts/i386/netinet/ip_icmp.c`, but it is exposed to userspace through clone-backed node metadata.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/ip_icmp.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone icmp c icmp` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `icmp` STREAMS `cdevsw` entry |

## Current Role

- Provides the ICMP-facing protocol endpoint in the network stack.
- When enabled, uses clone-open public naming; the target remains the ICMP STREAMS switch-table entry.
- Belongs to the protocol stack, not the hardware-interface layer.