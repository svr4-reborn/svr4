# Keyboard/Display Video Mapper

The `kdvm` driver in `uts/arch/at/i386/io/kdvm/kdvm.c` manages keyboard/display video-memory mapping. It is a character device used for video-memory range and mapping control rather than for block or tty-style data transport.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/arch/at/i386/io/kdvm/kdvm.c` |
| Handler prefix | `kdvm_` |
| Character major | `20` |
| Mask / Type | `oci` / `icorf` |
| Configured units | `1` |
| Static node metadata | None staged |

## Current Role

- Manages video-memory mapping and protection for the AT keyboard/display stack.
- Sits alongside the broader `kd` console code rather than replacing it.
- Matters when debugging user access to video memory and console/video interaction.