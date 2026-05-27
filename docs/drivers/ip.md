# IP Endpoint

The `ip` endpoint is the clone-backed Internet Protocol entry point. Its core implementation lives in `uts/i386/netinet/ip_main.c`, with related IP logic distributed across the `uts/i386/netinet/` sources.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/ip_main.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone ip c ip` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `ip` STREAMS `cdevsw` entry |

## Current Role

- Implements the core IPv4 protocol layer for routing, fragmentation, and mux coordination.
- When enabled, exposes its user-visible endpoint through clone-backed naming.
- Is a central anchor for network-stack debugging above the link layer.