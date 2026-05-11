# Kernel Profiler Driver

The `prf` driver in `uts/i386/io/prf.c` is the UNIX kernel profiler. It samples the processor state at clock interrupts and maintains profiling counters that can be read through a character-device interface.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/prf.c` |
| Handler prefix | `prf` |
| Character major | `6` |
| Mask / Type | `rwi` / `icof` |
| Configured units | `1` |
| Static node metadata | `prf prf c 0 0 3 644` |

## Current Role

- Provides kernel profiling data rather than general-purpose data transport.
- Depends on profiling support state staged alongside the driver.
- Exposes a single named profiling node in the staged metadata.