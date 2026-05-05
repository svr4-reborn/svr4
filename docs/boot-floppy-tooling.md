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
- s5 replacement now also reclaims blocks when a replacement shrinks a file.
- BFS and UFS support remains inspection-oriented; mutation support is currently s5 only.
