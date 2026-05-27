# TLI Connectionless Endpoint

The `ticlts` endpoint in `uts/i386/io/ticlts.c` is the clone-backed TLI connectionless transport provider. It represents the datagram-mode loopback transport endpoint in the older TLI stack.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/io/ticlts.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone ticlts c ticlts` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `ticlts` STREAMS `cdevsw` entry |

## Current Role

- Provides a connectionless TLI transport endpoint.
- When enabled, is opened through the clone path rather than a private major number.
- Belongs to the historical STREAMS/TLI API surface.