# XT Packet Protocol Driver

The `xt` driver in `uts/i386/io/xt.c` is the blit packet protocol driver. It multiplexes virtual tty lines over physical tty lines and carries the older packetized terminal/windowing transport used by the classic workstation stack.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/xt.c` |
| Handler prefix | `xt` |
| Character major | `13` |
| Mask / Type | `Iocrwi` / `icor` |
| Configured units | `1` |
| Generated `space.c` / `stubs.c` | Yes / Yes |
| Static node metadata | None staged |

## Current Role

- Carries the legacy XT packet protocol for virtual-terminal style traffic.
- Sits firmly in the older windowing and multiplexed-terminal part of the tree.
- Is most relevant when debugging legacy terminal protocol paths rather than modern libc bringup.