# ICMP Endpoint

The `icmp` endpoint is the clone-backed ICMP protocol entry point for the STREAMS TCP/IP stack. Its implementation lives in `uts/i386/netinet/ip_icmp.c`, but it is exposed to userspace through clone-backed node metadata.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/ip_icmp.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone icmp c icmp` |
| Dedicated major | None; shares clone-open machinery |

## Current Role

- Provides the ICMP-facing protocol endpoint in the network stack.
- Uses clone-open naming rather than a dedicated switch-table major.
- Belongs to the protocol stack, not the hardware-interface layer.