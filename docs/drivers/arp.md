# ARP Control Endpoint

The `arp` driver is the clone-backed Address Resolution Protocol control side for the STREAMS network stack. Its protocol implementation lives in `uts/i386/netinet/arp.c`, and it pairs with the APP STREAMS module for per-interface address resolution.

Although `arp` has clone-backed node metadata, it is not a normal user-level packet endpoint. The source describes the upper side as an ioctl interface; ARP packet generation is driven by failed `arpresolve()` requests and by ARP traffic arriving from the linked lower provider.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/arp.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone arp c arp` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `arp` STREAMS `cdevsw` entry |

## Current Role

- Implements ARP address-to-link-layer mapping and cache maintenance in the network stack.
- Provides ioctl handling for ARP table operations such as set, delete, and get.
- Links to the APP per-interface state so unresolved outbound IPv4 packets can trigger ARP requests and later be released when a mapping arrives.
- When enabled, is opened through the clone path, but it should be treated as a protocol/control driver rather than a general userspace ARP packet interface.