# SVR4 Kernel Documentation

This site collects working notes for the SVR4 kernel tree, with an emphasis on interfaces that are immediately useful for bringup and libc work.

## Main Sections

- [Syscall Reference](syscalls.md): complete syscall table derived from the kernel dispatch table and owning handlers under `uts/`.
- [Syscall Porting Guide](syscall-porting-guide.md): practical notes for implementing libc wrappers against this kernel ABI.
- [Multiplexed Syscall Families](syscall-families.md): deeper breakdown of the syscall families that hide multiple operations behind one entry number.
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