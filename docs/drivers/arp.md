# ARP Endpoint

The `arp` endpoint is the clone-backed Address Resolution Protocol entry point for the STREAMS network stack. Its protocol implementation lives in `uts/i386/netinet/arp.c`, while userspace reaches it through clone-backed node metadata.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/arp.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone arp c arp` |
| Dedicated major | None; shares clone-open machinery |

## Current Role

- Implements ARP address-to-link-layer mapping in the network stack.
- Is opened through the clone path rather than through a separate major.
- Matters when debugging protocol stack bringup and endpoint naming under `/dev`.