# LLC Loopback Endpoint

The `llcloop` endpoint is the clone-backed LLC loopback entry point for the network stack. Its implementation lives in `uts/i386/netinet/llcloop.c` and is used for loopback/testing traffic rather than external hardware transport.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/llcloop.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone loop c llcloop` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| Public node major | `clone`; clone-open dispatches to the `llcloop` STREAMS `cdevsw` entry |

## Current Role

- When enabled, provides a link-level loopback/testing endpoint.
- Exposes its name through clone-backed node metadata.
- Is a diagnostic/support endpoint rather than a hardware NIC driver.