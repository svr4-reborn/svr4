# Operating System Messages Driver

The `osm` driver in `uts/i386/io/osm.c` is the operating-system messages driver. It provides access to the system printf-style message buffer through a character-device interface.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/osm.c` |
| Handler prefix | `osm` |
| Character major | `17` |
| Mask / Type | `orw` / `irco` |
| Configured units | `1` |
| Static node metadata | None staged |

## Current Role

- Exposes buffered system messages for administrative inspection.
- Sits close to the kernel message and debugging path, but is distinct from the STREAMS `log` driver.
- Is relevant when tracing older console/message buffer behavior.