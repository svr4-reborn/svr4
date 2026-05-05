# AT386 Kernel Build Coverage Audit

This note compares the historical top-level `uts/i386/unix.mk` families with the current YAML-driven build graph in `build-specs/uts/i386/kernel.yaml`.

## Coverage Matrix

| Historical family | Historical directory | Current YAML target | Status | Notes |
| --- | --- | --- | --- | --- |
| `master` | `uts/i386/master.d` | `master-tree-at386` | Covered | Staged into the synthetic `conf` tree. |
| `machine` | `uts/i386/ml` | `ml-at386` | Partial | Helper now builds the historical generated-object flow, but `locore.s` still stops at GNU `as` dialect incompatibilities. |
| `exec` | `uts/i386/exec` | `exec-at386` | Covered | Recursive discovery matches the historical nested loaders. |
| `system` | `uts/i386/os` | `os-at386` | Covered | Flat source directory; no missing subtrees found. |
| `vmsys` | `uts/i386/vm` | `vm-at386` | Covered | Flat source directory; no missing subtrees found. |
| `vpix` | `uts/i386/vx` | `vx-at386` | Covered | Flat source directory. |
| `filsys` | `uts/i386/fs` | `fs-at386` | Covered | Recursive discovery covers nested filesystem implementations, including `fs/nfs`. |
| `drivers` | `uts/i386/io` plus `arch/at/uts/i386/io` | `io-at386` | Covered | Split across `io-core-at386`, `io-ws-at386`, `io-kd-at386`, and `io-kdvm-at386`. |
| `disp` | `uts/i386/disp` | `disp-at386` | Covered | Flat source directory. |
| `kdb` | `uts/i386/kdb` | `kdb-at386` | Covered | Split across `kdb-core-at386`, `kdb-gdebugger-at386`, and `kdb-util-at386`. |
| `bootstrap` | `uts/i386/boot` | `boot-at386` | Partial | Target added and reaches the historical bootlib and AT386 build flow; current blocker is the hardcoded host-side `rmhdr` tool build under the AT386 boot helper makefile. |
| `emulator` | `uts/i386/fp` | `fp-at386` | Partial | Target added and reaches the historical emulator build flow; current blocker is the legacy assembler syntax in `dcode.s` under the modern host toolchain. |
| `vuifile` | `uts/i386/vuifile` | `config-at386` | Covered | Preprocessed into `cf.d/vuifile`. |
| `kernmap` | `uts/i386/kernmap` | `config-at386` | Covered | Preprocessed into `cf.d/kernmap`. |
| `des` | `uts/i386/des` | `des-at386` | Covered | Flat source directory. |
| `inet` | `uts/i386/netinet` | `network-at386` | Covered | Modeled by `netinet-at386`; top-level `net` remains header-only. |
| `klm` | `uts/i386/klm` | `klm-at386` | Covered | Flat source directory. |
| `rpc` | `uts/i386/rpc` | `rpc-at386` | Covered | Flat source directory. |
| `ktli` | `uts/i386/ktli` | `ktli-at386` | Covered | Flat source directory. |

## Additional Notes

- The current non-recursive targets are flat directories in practice: `os`, `vm`, `disp`, `vx`, `rpc`, `ktli`, and `klm` do not appear to hide unmodeled nested source trees.
- The top-level `uts/i386/net` and `uts/i386/nfs` directories do not need standalone compile targets in the current graph. `net` is header-oriented, and the NFS implementation lives under `uts/i386/fs/nfs`, which is already covered by the recursive `fs-at386` target.
- The `ml-at386` gap is no longer a missing graph edge. It is now a concrete compatibility issue with the historical assembler dialect used by `locore.s` under modern GNU `as`.
- The `boot-at386` and `fp-at386` gaps are also no longer missing graph edges. Both historical families are now represented explicitly in the YAML graph and run until concrete host-tool or assembler-compatibility failures.