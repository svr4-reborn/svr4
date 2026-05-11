# STREAMS Administrative Driver

The `sad` driver in `uts/i386/io/sad.c` is the STREAMS administrative driver. It is the control point for autopush configuration and STREAMS module-name verification.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/sad.c` |
| Handler prefix | `sad` |
| Character major | `25` |
| Mask / Type | `I` / `Scfior` |
| Configured units | `1` |
| Generated `space.c` | Yes |
| Static node metadata | None staged |

## Current Role

- Owns administrative STREAMS control operations such as autopush state management.
- Is part of STREAMS configuration and validation rather than data-path transport.
- Is a useful anchor when module-push policy is involved in tty or networking behavior.