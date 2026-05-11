# Shell Layers Driver

The `sxt` driver in `uts/i386/io/sxt.c` is the older shell-layers driver. It provides multiple virtual terminal sessions over a single real tty in the classic shell-layers model.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/sxt.c` |
| Handler prefix | `sxt` |
| Character major | `14` |
| Mask / Type | `ocrwi` / `irco` |
| Configured units | `1` |
| Generated `space.c` / `stubs.c` | Yes / Yes |
| Static node metadata | None staged |

## Current Role

- Provides the older shell-layers virtual-terminal abstraction.
- Is part of the legacy terminal/windowing environment rather than the core storage or network paths.
- Should be read alongside `nsxt` when tracing shell-layers behavior.