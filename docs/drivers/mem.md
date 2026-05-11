# Memory Special-File Driver

The `mem` driver in `uts/i386/io/mem.c` is the special-memory character device for the kernel. In this tree it is the implementation behind the traditional memory-style minor devices such as `/dev/mem`, `/dev/kmem`, `/dev/null`, `/dev/pmem`, and `/dev/zero`.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/mem.c` |
| Handler prefix | `mm` |
| Character major | `2` |
| Mask / Type | `rwociSM` / `irscof` |
| Configured units | `1` |
| Static node metadata | None staged in the default `master.d` tree |

## Current Role

- Provides privileged access paths to physical and kernel memory.
- Carries the minor-number special cases for sink/source devices such as null and zero.
- Appears as a character-only device in the generated configuration.

The absence of staged node metadata here does not mean the driver lacks a stable ABI. The minor-number behavior in `mem.c` is the important compatibility surface.