# System Message Driver

The `sysmsg` driver in `uts/i386/io/sysmsg.c` is the system-message device used for early boot and debug-oriented console/message handling.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/sysmsg.c` |
| Handler prefix | `smsg` |
| Character major | `19` |
| Mask / Type | `owi` / `irco` |
| Configured units | `1` |
| Generated `space.c` | Yes |
| Static node metadata | None staged |

## Current Role

- Bridges console/message handling in earlier boot and debug scenarios.
- Lives in the i386 core IO tree rather than the AT-only console subdirectories.
- Complements, rather than replaces, the other logging and console-message paths.