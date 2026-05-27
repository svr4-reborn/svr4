# TLI Connection-Oriented Endpoint

The `ticots` endpoint in `uts/i386/io/ticots.c` is the clone-backed TLI connection-oriented transport provider. It implements the older virtual-circuit mode transport abstraction.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/io/ticots.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone ticots c ticots` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `ticots` STREAMS `cdevsw` entry |

## Current Role

- Provides a connection-oriented TLI endpoint.
- When enabled, uses clone-backed public naming; clone-open dispatches to the `ticots` STREAMS `cdevsw` entry.
- Sits in the historical STREAMS/TLI transport layer rather than the IP stack proper.