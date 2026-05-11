# TLI Connection-Oriented Endpoint

The `ticots` endpoint in `uts/i386/io/ticots.c` is the clone-backed TLI connection-oriented transport provider. It implements the older virtual-circuit mode transport abstraction.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/io/ticots.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone ticots c ticots` |
| Dedicated major | None; shares clone-open machinery |

## Current Role

- Provides a connection-oriented TLI endpoint.
- Uses clone-backed naming rather than a standalone major.
- Sits in the historical STREAMS/TLI transport layer rather than the IP stack proper.