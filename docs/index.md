# SVR4 Kernel Documentation

This site collects working notes for the SVR4 kernel tree, with an emphasis on interfaces that are immediately useful for bringup and libc work.

## Main Sections

- [Kernel Modernization Plan](kernel-modernization-plan.md): staged plan for ANSI-fying the kernel C sources, validating slices without a compile database, and deferring formatting until the syntax migration is stable.
- [Syscall Reference](syscalls.md): complete syscall table derived from the kernel dispatch table and owning handlers under `uts/`.
- [Syscall Porting Guide](syscall-porting-guide.md): practical notes for implementing libc wrappers against this kernel ABI.
- [Multiplexed Syscall Families](syscall-families.md): deeper breakdown of the syscall families that hide multiple operations behind one entry number.
- [Kernel Device Drivers](kernel-drivers.md): how the modern build stages `master.d` metadata, generates switch tables, and how to add new drivers.
- [Block And Character Device Catalog](kernel-device-catalog.md): inventory of the default AT386 block devices, character devices, clone-backed endpoints, and STREAMS-only modules.
- [Per-Driver Notes](drivers/index.md): focused notes for the main configured AT386 drivers under `docs/drivers/`.
- [Boot Floppy Tooling](boot-floppy-tooling.md): notes on the current boot-media tooling.
- [Bringup Debug Notes](bringup-debug-notes-2026-05-06.md): running notes from kernel bringup and debugging.

## Building The Site

Install the docs extra from the repo root:

```bash
pip install -e .[docs]
```

Then build or serve the site:

```bash
mkdocs build --strict
mkdocs serve
```