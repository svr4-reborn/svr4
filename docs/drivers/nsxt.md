# NSXT Shell Layers Multiplexor

The `nsxt` driver in `uts/i386/io/nsxt.c` is the STREAMS shell-layers multiplexor. It routes virtual tty sessions through a control-channel model used by the older shell-layers tooling.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/nsxt.c` |
| Handler prefix | `nsxt` |
| Character major | `34` |
| Mask / Type | `oc` / `icSr` |
| Configured units | `1` |
| Generated `space.c` | Yes |
| Static node metadata | None staged |

## Current Role

- Implements the multiplexor side of the older shell-layers stack.
- Complements `sxt` rather than replacing it.
- Belongs to the historical terminal/windowing subsystem.