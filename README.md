# svr4-src

Historical UNIX System V/386 source tree.

This repository is not just the kernel. It is a broad source provision rooted in the old `usr/src` layout: kernel, userland commands, libraries, compatibility layers, packaging metadata, optional add-ons, and the shell-script build wrappers used to assemble them.

The tree is useful as a starting point for a kernel port or modernization project, but it helps to treat it as an imported historical source dump rather than a clean, self-describing modern project.

## YAML Builder Helper

The repository also includes a small Python build driver in [build.py](build.py) for the in-progress YAML-based kernel build flow.

To emit a VS Code and clangd compatible compilation database while walking the selected target, use:

```sh
python3 build.py -t kernel-at386 --dry-run --emit-compile-commands
```

That writes `compile_commands.json` at the workspace root by default. You can also pass an explicit path, for example `--emit-compile-commands build/kernel-at386/compile_commands.json`.

## What this repository appears to be

- An extracted `usr/src`-style source tree for a UNIX System V/386 release.
- Built by top-level shell entry points such as `:mk`, `:mkuts`, `:mkcmd`, and `:mklib` rather than a single central `Makefile`.
- Oriented around a staging root set through `ROOT`, with sources expected under `$ROOT/usr/src` and outputs installed relative to `$ROOT`.

There are provenance/versioning inconsistencies inside the tree:

- The previous README described this as "UNIX System V Release 4 Version 3".
- `:mk` identifies itself as rebuilding "UNIX System V/386 Release 4.0".
- [proto/i386/README](proto/i386/README) still documents a "Release 3.2" style build.

For planning purposes, it is safest to think of this checkout as an SVR4-era System V/386 source tree with mixed historical packaging and build metadata.

## Repository Inventory

| Path | Purpose |
| --- | --- |
| `:mk*` | Top-level shell entry points for full builds, partial builds, kernel-only builds, library-only builds, compatibility-package builds, and header installation. |
| [uts/](uts/) | Core kernel sources. The main kernel implementation visible in this checkout is under [uts/i386/](uts/i386/), including boot, exec, VM, filesystems, networking, NFS/RPC, debugger support, and device drivers. |
| [arch/](arch/) | Machine and bus-specific support fragments. Present subtrees include `at`, `eisa`, `mb1`, and `mbus`. |
| [head/](head/) | Main system headers installed into `/usr/include`. |
| [cmd/](cmd/) | Main System V userland. This includes standard utilities, admin tools, daemons, shells, networking tools, filesystem utilities, packaging tools, and the software generation system. |
| [lib/](lib/) | Core libraries such as `libc`, `libm`, `libcrypt`, `libsocket`, `libnsl`, `libpkg`, `libgen`, `rtld`, curses-related libraries, and other system libraries. |
| [pkg/](pkg/) | Packaging and product-assembly metadata. In this checkout it contains at least `face`, `scde`, and `terminf`. |
| [proto/](proto/) | Historical build and install documentation plus prototype files. [proto/i386/README](proto/i386/README) is the main surviving build note. |
| [add-on/](add-on/) | Optional packages, hardware and vendor bundles, compatibility add-ons, storage and network extras, debugger packages, and installable product payloads. |
| [ucbcmd/](ucbcmd/) | BSD/UCB compatibility commands installed under `/usr/ucb`. |
| [ucbhead/](ucbhead/) | BSD/UCB compatibility headers installed under `/usr/ucbinclude`. |
| [ucblib/](ucblib/) | BSD/UCB compatibility libraries. |
| [xcplib/](xcplib/) | XENIX compatibility libraries. |
| [ucb.dirs](ucb.dirs) | Directory manifest used by the BSD compatibility package build. |

## Notable Subsystems

### Kernel and low-level system software

- [uts/i386/](uts/i386/) is the main kernel target in this checkout.
- The visible i386 kernel tree includes boot code, memory management, executable loading, filesystems, networking stacks, NFS/RPC, kernel debugger support, and a large device-driver surface.
- If your project goal is to port and modernize the kernel, [uts/](uts/), [head/](head/), and [arch/](arch/) are the first places to model as separate build domains.

### Userland and toolchain

- [cmd/](cmd/) is large and broad; it contains both ordinary commands and substantial subsystem collections.
- [cmd/sgs/](cmd/sgs/) is the software generation system: compiler, assembler, linker, ELF tools, lex, yacc, and related toolchain pieces.
- [cmd/fs.d/](cmd/fs.d/) groups filesystem utilities.
- [cmd/cmd-inet/](cmd/cmd-inet/) contains networking-related commands and service layout.
- [cmd/oamintf/](cmd/oamintf/) contains the OAM and admin interface framework plus its install metadata.

### Compatibility layers

- The `ucb*` trees are a BSD compatibility package rather than part of the native System V base.
- [xcplib/](xcplib/) is the XENIX compatibility library side.
- The XENIX compatibility command side appears incomplete in this checkout: `:mkxcpcmd` expects sources under `$SRC/xcpcmd`, but no top-level `xcpcmd/` tree is present here.

### Add-ons, packaging, and product assembly

- [add-on/](add-on/) contains optional product payloads and hardware or vendor-specific extras, including package trees such as `pkg.kdb`, `pkg.nfs`, `pkg.rfs`, `pkg.rpc`, `pkg.sec`, `pkg.termcap`, and `pkg.xx`.
- [add-on/source/](add-on/source/) contains build helper material such as `.setup`, `Files.base`, `Files.scde`, and `source.mk`.
- [pkg/](pkg/) and the package-oriented subtrees under [add-on/](add-on/) are important if you want to reproduce historical media images, but they can be separated from a kernel-first modernization effort.

## Legacy Build Entry Points

There is no single root `Makefile`. The top-level shell wrappers are the real build entry points:

- `:mk` builds the broad system.
- `:mk.fnd` builds the foundation set without the developer toolchain.
- `:mk.csds` builds the C software development set.
- `:mkcmd` builds commands.
- `:mklib` builds libraries.
- `:mkuts` builds the kernel.
- `:mkhead` and `:mksyshead` install headers.
- `:mkucb`, `:mkucbcmd`, `:mkucblib`, and `:mkucbhead` build the BSD compatibility package.
- `:mkxcp`, `:mkxcpcmd`, and `:mkxcplib` build the XENIX compatibility package.
- `:mk.addon` builds selected add-ons.

The historical build instructions are in [proto/i386/README](proto/i386/README). They assume:

- `ROOT` points at a separate staging tree, not `/`.
- sources live under `$ROOT/usr/src`.
- outputs are installed relative to `$ROOT`.
- builds are long-running and largely script-driven.

## Audit Notes Relevant To A New Build System

- The tree is already split into natural build domains: kernel, core headers, system libraries, commands, BSD compatibility, XENIX compatibility, add-ons, and package assembly.
- A practical first cut for a modern build graph is probably:
	1. `head` and generated or installed headers
	2. `lib` and runtime support
	3. `uts` kernel objects
	4. `cmd` base userland
	5. `ucb*` and `xcp*` compatibility layers
	6. `add-on` and `pkg` packaging or media assembly
- Some historical build references do not line up cleanly with this checkout. In particular, `:mkxcp` expects an `xcp.dirs` manifest and `:mkxcpcmd` expects an `xcpcmd/` source tree, neither of which is present at the repository root.
- Because the source tree is packaged around install-time destinations, a modern build system will likely need to separate compile units, install images, and package images, which are currently interleaved.

## Historical Notes

- If you want a built reference artifact for comparison, the archived media linked by the previous README is still available: [SVR4 v3.7z on archive.org](https://archive.org/details/svr4-v3.7z).
- The surviving build documentation should be treated as guidance, not as an exact description of this checkout.

