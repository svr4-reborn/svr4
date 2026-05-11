# LLC Loopback Endpoint

The `llcloop` endpoint is the clone-backed LLC loopback entry point for the network stack. Its implementation lives in `uts/i386/netinet/llcloop.c` and is used for loopback/testing traffic rather than external hardware transport.

## Endpoint Summary

| Field | Value |
| --- | --- |
| Key source file | `uts/i386/netinet/llcloop.c` |
| Access path | Clone-backed via the `clone` driver |
| Staged node metadata | `clone loop c llcloop` |
| Dedicated major | None; shares clone-open machinery |

## Current Role

- Provides a link-level loopback/testing endpoint.
- Exposes its name through clone-backed node metadata.
- Is a diagnostic/support endpoint rather than a hardware NIC driver.