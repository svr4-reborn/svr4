# Pseudo-Terminal Slave Driver

The `pts` driver in `uts/i386/io/pts.c` is the pseudo-terminal slave endpoint. It is the slave-side STREAMS device paired with the pseudo-terminal master.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/pts.c` |
| Handler prefix | `pts` |
| Character major | `35` |
| Mask / Type | `-` / `Scio` |
| Configured units | `1` |
| Static node metadata | None staged |

## Current Role

- Acts as the slave-side half of the pseudo-terminal pair.
- Works together with [`ptm`](ptm.md), which owns the master endpoint.
- Exposes a STREAMS tty-style interface rather than a hardware line.