# Pseudo-Terminal Master Driver

The `ptm` driver in `uts/i386/io/ptm.c` is the pseudo-terminal master endpoint. It is the master-side STREAMS device used to create and control pseudo-terminal sessions.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/ptm.c` |
| Handler prefix | `ptm` |
| Character major | `11` |
| Mask / Type | `-` / `Scio` |
| Configured units | `16` |
| Generated `space.c` | Yes |
| Static node metadata | None staged |

## Current Role

- Acts as the master-side half of the pseudo-terminal pair.
- Works together with [`pts`](pts.md), the pseudo-terminal slave endpoint.
- Exposes a STREAMS interface rather than a block or raw memory-style interface.