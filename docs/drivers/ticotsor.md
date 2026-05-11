# TLI Orderly-Release Endpoint

The `ticotsor` endpoint in `uts/i386/io/ticotsord.c` is the clone-backed orderly-release variant of the connection-oriented TLI transport provider.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/io/ticotsord.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone ticotsord c ticotsor` |
| Dedicated major | None; shares clone-open machinery |

## Current Role

- Provides the orderly-release flavor of the connection-oriented TLI endpoint.
- Keeps graceful/ordered shutdown semantics distinct from plain `ticots`.
- Is part of the legacy STREAMS/TLI compatibility surface.