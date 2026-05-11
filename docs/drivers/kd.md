# Keyboard/Display Driver

The `kd` driver is the AT keyboard/display STREAMS console driver. Its implementation spans `uts/arch/at/i386/io/kd/`, and it is the main keyboard, console-display, and terminal-emulation path for the AT386 console.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source tree | `uts/arch/at/i386/io/kd/` |
| Handler prefix | `kd` |
| Character major | `30` |
| Mask / Type | `Is` / `iHfSrc` |
| Configured units | `2` |
| Generated `space.c` | Yes |
| Static node metadata | None staged |

## Current Role

- Handles console display and keyboard input on the AT386 platform.
- Works together with the `ansi`, `char`, `gvid`, and `kdvm` pieces of the console stack.
- Exposes the main keyboard/display device major in the default AT386 configuration.

Because `kd` spans a directory rather than a single small source file, it is best treated as a console subsystem rather than an isolated leaf driver.