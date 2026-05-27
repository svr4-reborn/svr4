# APP Link-Convergence Module

The `app` module in `uts/i386/netinet/app.c` is the STREAMS convergence layer between IP and Ethernet-like lower providers. It is pushed on the IP-to-link packet path rather than opened as a normal user-visible character endpoint.

## Module Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/netinet/app.c` |
| Handler prefix | `app` |
| Mask / Type | `-` / `Sio` |
| Default generated state | Enabled in the default AT386 config; historical `sdev` record is `N` |
| User-visible major | None; APP is a STREAMS module on the linked packet path |

## Current Role

- Receives `DL_UNITDATA_REQ` packets from IP carrying an IPv4 destination.
- Calls ARP resolution when a cached link-layer mapping is missing.
- Rewrites the destination into the final link-layer address before handing the frame to the lower provider.
- Keeps per-interface `app_pcb[]` state and pairs it with ARP per-interface state by interface name.