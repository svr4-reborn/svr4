# Boot Floppy Tooling

This document collects the detailed command-level workflows for the SVR4 boot floppy image tooling.

## Reusable Module

The reusable implementation lives in `tools.floppyfs`, backed by the smaller internal package under `tools/floppyfslib/`.

Example import:

```python
from pathlib import Path
from tools.floppyfs import detect_layout, load_replacement_set, validate_replacements

image = Path("original_diskettes/Base 01 (2.1a).img")
layout = detect_layout(image)
replacements = load_replacement_set(Path("build-specs/uts/i386/boot-floppy-replacements.json"), "label-hybrid")
validate_replacements(image, replacements)
```

## Build Targets

Build the base hybrid floppy image:

```sh
python3 build.py -t boot-floppy-hybrid-at386
```

Build the repo-owned named replacement set:

```sh
python3 build.py -t boot-floppy-hybrid-at386-labeled
```

Validate the named replacement set without writing a new image:

```sh
python3 build.py -t boot-floppy-validate-replacements-at386-labeled
```

## CLI Commands

Inspect the detected boot boundary and filesystem roots:

```sh
python3 tools/boot_floppy_image.py inspect --image "original_diskettes/Base 01 (2.1a).img"
```

Extract an s5 file from the image:

```sh
python3 tools/boot_floppy_image.py extract-s5-file \
  --image "original_diskettes/Base 01 (2.1a).img" \
  --target-path /unix \
  --output build/boot-media/unix.reference
```

Diff an s5 file in the image against a host file:

```sh
python3 tools/boot_floppy_image.py diff-s5-file \
  --image build/boot-media/base01-hybrid.img \
  --target-path /LABEL \
  --source tools/boot-media/label.hybrid
```

Replace an s5 file in an existing image:

```sh
python3 tools/boot_floppy_image.py replace-s5-file \
  --image build/boot-media/base01-hybrid.img \
  --target-path /unix \
  --source build/boot-media/unix.reference
```

Validate one or more requested replacements against an image without writing changes:

```sh
python3 tools/boot_floppy_image.py validate-replacements \
  --image "original_diskettes/Base 01 (2.1a).img" \
  --replacement-manifest build-specs/uts/i386/boot-floppy-replacements.json \
  --replacement-set label-hybrid
```

Build a hybrid image with manifest-backed and inline replacements:

```sh
python3 tools/boot_floppy_image.py build-hybrid \
  --reference-image "original_diskettes/Base 01 (2.1a).img" \
  --bootloader build/uts/i386/boot/build/fdboot \
  --output build/boot-media/base01-hybrid-with-replacement.img \
  --replacement-manifest build-specs/uts/i386/boot-floppy-replacements.json \
  --replacement-set label-hybrid \
  --replace-s5-file /yes=build/boot-media/yes.from-hybrid
```

## Current Behavior

- `build-hybrid` validates requested replacements before writing the output image.
- s5 replacement can grow existing files by allocating data and indirect blocks from the image free list.

## Debugging A Hybrid Boot Floppy

If the BIOS loads the floppy image but nothing is printed afterward, treat that as an early-boot control-flow problem first. The fastest discriminator is to stop the virtual machine on the very first instruction and check whether execution reaches the stage-1 `readboot` path, the far-return handoff, and eventually the second-stage loader in `fdboot`.

Rebuild the local bootloader and hybrid image first:

```sh
python3 build.py -t boot-floppy-hybrid-at386-labeled
```

The boot build now preserves an unstripped linked image at `build/uts/i386/boot/build/fdboot.debug.elf` alongside the stripped boot binary used in the floppy image.

The synthetic AT386 boot build also now enables `DEBUG` by default, so the existing `debug(...)` traces in the bootloader are compiled in automatically.

The `/unix` loader no longer pauses for a keystroke after printing `BKI found version 2`; the historical debug macro wrapped a `getchar()` there, which would otherwise stall every debug boot right before handing control to the kernel.

The hybrid image builder now overlays the local bootloader onto the reference image boot region instead of zeroing the whole region first. This preserves required trailing bytes from the historical floppy boot area.

For repeatable launch and probe flows, use the helper script:

```sh
python3 tools/debug_hybrid_boot.py probe --mode handoff
```

Available probe modes:

- `entry`: stop at `0x7c00` and dump the initial stage-1 state.
- `handoff`: stop at `0x7c00`, the `readboot` call site at `0x7c1e`, and the far return at `0x7c29`, then single-step into the relocated second stage.
- `main`: run the handoff probe and then load `fdboot.debug.elf` at the protected-mode bootstrap base (`0x1000`) before attempting to break in `main`.

Start QEMU with a halted CPU and GDB stub:

```sh
python3 tools/debug_hybrid_boot.py launch --foreground
```

Then attach GDB in a second terminal:

```sh
gdb \
  -ex 'set remote hardware-breakpoint-limit 0' \
  -ex 'set architecture i8086' \
  -ex 'target remote :1234' \
  -ex 'b *0x7c00' \
  -ex 'c'
```

Do not use `hb` here. The QEMU GDB stub on this setup accepts software breakpoints (`Z0`) but reports no hardware breakpoint support.

Recommended debug flow:

- First confirm stage 1 runs by stopping at `0x7c00`.
- Step through `firststage`, `readboot`, and the `lret` in `uts/i386/boot/at386/start.s`, or use `python3 tools/debug_hybrid_boot.py probe --mode handoff` to do that automatically.
- If execution reaches the relocated second stage, load symbols from `build/uts/i386/boot/build/fdboot.debug.elf` and switch to 32-bit mode in GDB.

Example follow-up commands once you have crossed into the second stage:

```gdb
set architecture i386
add-symbol-file build/uts/i386/boot/build/fdboot.debug.elf 0x1000 -s .data 0x4000 -s .bss 0x47a0
b *0x15b2
b loadprog
c
```

Useful interpretation:

- If `0x7c00` hits but `main` never does, the failure is in first-stage relocation, BIOS reads, or the real-mode to protected-mode handoff in `start.s`.
- If `main` hits but no text ever appeared on screen, the BIOS teletype path or later bootloader control flow is the next place to instrument.
- The default synthetic boot build now compiles the bootloader with `DEBUG`, so the existing `debug(...)` calls in `boot.c`, `load.c`, and `disk.c` are active by default.
- s5 replacement now also reclaims blocks when a replacement shrinks a file.
- BFS and UFS support remains inspection-oriented; mutation support is currently s5 only.
