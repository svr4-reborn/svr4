# NXT Windowing Terminal Driver

The `nxt` driver in `uts/i386/io/nxt.c` is the older AT&T windowing-terminal STREAMS driver for 5620/615/620/630-style terminals. It supports the network and regular XT protocol variants used by that environment.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/nxt.c` |
| Handler prefix | `nxt` |
| Character major | `33` |
| Mask / Type | `oc` / `icSr` |
| Configured units | `1` |
| Generated `space.c` | Yes |
| Static node metadata | None staged |

## Current Role

- Supports the legacy windowing-terminal protocol stack.
- Is closely related to the older `xt`, `sxt`, and `nsxt` terminal/multiplexor code paths.
- Matters mainly for historical terminal support rather than the current libc bringup path.