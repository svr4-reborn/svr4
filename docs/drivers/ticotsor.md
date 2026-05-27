# TLI Orderly-Release Endpoint

The `ticotsor` endpoint in `uts/i386/io/ticotsord.c` is the clone-backed orderly-release variant of the connection-oriented TLI transport provider.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/io/ticotsord.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone ticotsord c ticotsor` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `ticotsor` STREAMS `cdevsw` entry |

## Current Role

- Provides the orderly-release flavor of the connection-oriented TLI endpoint.
- Keeps graceful/ordered shutdown semantics distinct from plain `ticots`.
- Is part of the legacy STREAMS/TLI compatibility surface.