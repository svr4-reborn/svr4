# Kernel Device Drivers

This tree keeps the historical SVR4 driver metadata format, but it no longer uses the legacy `idtools` or the old `master.d` makefiles to turn that metadata into a kernel configuration. The modern build path is entirely driven by the Python tooling under `uts/tools/` and the YAML build spec under `uts/build-specs/`.

## Modern Configuration Pipeline

For the normal AT386 kernel configuration, the driver path is:

1. `uts/tools/uts_stage_master_at386.py` preprocesses and stages `uts/i386/master.d/` and `uts/arch/at/i386/master.d/` into a synthetic configuration tree under `build/uts/i386/conf/`.
2. `uts/tools/uts_idconfig.py` parses the staged metadata and generates:
   - `config.h`
   - `conf.c`
   - `fsconf.c`
   - `vector.c`
   - `direct`
   - `simple-idconfig.json`
3. `uts/tools/uts_driver_compose.py` uses the generated manifest to compose `pack.d/<module>/Driver.o` from the implementation objects or, for excluded modules, from `stubs.c`.

The modern build only sees modules that are explicitly listed in `COMMODS` or `AT386MODS` inside `uts/tools/uts_stage_master_at386.py`. Adding a new directory under `master.d/` is not sufficient by itself.

## Files A Driver Contributes

The modern build expects the historical SVR4 split between implementation sources and configuration metadata:

- Implementation sources live under the kernel source tree, typically in places such as `uts/i386/io/`, `uts/arch/at/i386/io/`, `uts/i386/netinet/`, or another subsystem-specific directory.
- `master.d/<module>/mdev` declares switch-table membership, major numbers, and the handler symbol prefix.
- `master.d/<module>/sdev` declares whether the driver is configured and, if applicable, how many units/controllers exist and which interrupt/vector/IO resources they use.
- `master.d/<module>/node` is optional and carries the intended `/dev` node metadata.
- `master.d/<module>/space.c` is optional and carries per-driver configuration data.
- `master.d/<module>/stubs.c` is optional and provides linkable stubs when a driver is excluded.

The build then stages those files into synthetic `mdevice.d/`, `sdevice.d/`, `node.d/`, and `pack.d/` trees before generating `conf.c` and `Driver.o` files.

## `mdev` Record Format

The replacement `idconfig` parser expects nine whitespace-separated fields after preprocessing:

| Field | Meaning |
| --- | --- |
| `name` | Module name. Also becomes the staged directory name under `pack.d/`. |
| `mask` | Entry points and lifecycle hooks that the generated tables should wire up. |
| `type flags` | Switch-table membership and other special handling. |
| `handler` | C symbol prefix used for generated declarations, such as `hdopen()` or `asyinfo`. |
| `block major` | Block-major range, or `-` if no block major is assigned. |
| `char major` | Character-major range, or `-` if no character major is assigned. |
| `minimum units` | Historical lower bound for configured units. |
| `maximum units` | Historical upper bound for configured units. |
| `channel` | Driver channel value carried into the generated config. |

Example:

```text
hd Iocrwiz iHrobcf hd 0 0 1 2 -1
```

That one line is enough for the generated configuration to know that `hd` is both a block and character driver, that it should expose `open`, `close`, `read`, `ioctl`, `init`, and `size`-style hooks, and that its handler prefix is `hd`.

## `sdev` Record Format

The staged `sdevice.d/<module>` files are parsed as ten-field records:

| Field | Meaning |
| --- | --- |
| `name` | Module name. |
| `Y` or `N` | Whether the module is configured into the current kernel. |
| `units` | Number of units for this controller record. |
| `ipl` | Interrupt priority level. |
| `interrupt type` | Historical interrupt style value carried into `config.h`. |
| `vector` | Interrupt vector. |
| `sioa` | Start of IO address range. |
| `eioa` | End of IO address range. |
| `scma` | Start of controller memory address range. |
| `ecma` | End of controller memory address range. |

For example, `hd` currently stages one configured controller record with two units, vector `14`, and the standard AT IDE IO window.

## Mask Letters Interpreted By `uts_idconfig.py`

The modern generator does not need every historical idtools feature, but it does interpret the following `mask` letters today:

| Mask | Effect in the generated configuration |
| --- | --- |
| `o` | Wires `handleropen()` into `bdevsw` and/or `cdevsw`. |
| `c` | Wires `handlerclose()` into `bdevsw` and/or `cdevsw`. |
| `r` | Wires `handlerread()` into `cdevsw`. |
| `w` | Wires `handlerwrite()` into `cdevsw`. |
| `i` | Wires `handlerioctl()` into `cdevsw`. |
| `M` | Wires `handlermmap()` into `cdevsw`. |
| `S` | Wires `handlersegmap()` into `cdevsw`. |
| `L` | Wires `handlerchpoll()` into `cdevsw.d_poll`. |
| `p` | Wires `handlerpoll()` into the `xpoll` slots and into `io_poll[]`. |
| `h` | Wires `handlerhalt()` into the `xhalt` slots and into `io_halt[]`. |
| `I` | Adds `handlerinit()` to `io_init[]`. |
| `s` | Adds `handlerstart()` to `io_start[]`. |
| `E` | Adds `handlerkenter()` to `io_kenter[]`. |
| `X` | Adds `handlerkexit()` to `io_kexit[]`. |
| `z` | Wires `handlersize()` into `bdevsw.d_size` when the driver also carries the `f` type flag. |
| `f` | Declares a legacy `handlerfork()` entry point for compatibility. |
| `e` | Declares a legacy `handlerexec()` entry point for compatibility. |
| `x` | Declares a legacy `handlerexit()` entry point for compatibility. |

Not every one of those hooks is used by every driver class. The generator only emits the ones that make sense for the switch table the driver participates in.

## Type Flags Interpreted By `uts_idconfig.py`

The modern generator actively interprets these `type flags`:

| Flag | Effect in the generated configuration |
| --- | --- |
| `b` | Driver appears in `bdevsw`. |
| `c` | Driver appears in `cdevsw`. |
| `S` | Driver or module exports `struct streamtab handlerinfo`. This populates `cdevsw.d_str` and/or `fmodsw`. |
| `m` | Treat the STREAMS entry as a module in `fmodsw`. |
| `t` | Expects `struct tty handler_tty[]` and wires it into `cdevsw.d_ttys`. |
| `f` | Expects `int handlerdevflag` and uses it instead of `nodevflag` in generated tables. |
| `e` | Adds an exec-format entry to `execsw` using `handlermagic[]`, `handlerexec()`, and `handlercore()`. |
| `d` | Adds `handler_init()` to the generated scheduling-class table. |
| `G` | Suppresses interrupt-vector generation for that device. |
| `R` | Declares a legacy `handlerreset()` symbol for compatibility. |

Historical type letters that are not listed above still remain in the staged metadata, but the Python replacement does not currently consult them when generating `conf.c` or `vector.c`.

## `node` Files

`node` files are still useful, but the current Python replacement does not parse them into C structures. It stages them verbatim into `build/uts/i386/conf/node.d/` and leaves them as metadata for packaging, documentation, and operator inspection.

In-tree examples show several common forms:

```text
asy tty00 c 0
lp lp0 c 0
clone ip c ip
log conslog c 0 0 0 222
```

The important practical point is that a `node` file is where the intended device names live. If a driver should advertise static `/dev` entries, add a `node` file even though the current configuration generator does not consume it directly.

## Adding A New Driver

Use this checklist for new or newly-ported drivers:

1. Put the implementation sources in the right subsystem directory under `uts/`.
2. Add a `master.d/<module>/` directory with at least `mdev` and `sdev`.
3. Add `node`, `space.c`, and `stubs.c` when the driver needs static node metadata, tunables, or excluded-build stubs.
4. Register the module name in `COMMODS` or `AT386MODS` inside `uts/tools/uts_stage_master_at386.py`, otherwise it never reaches the synthetic conf tree.
5. Check that `uts/tools/uts_idconfig.py` can map the implementation sources to object files. If it reports an `unmapped` package or missing inputs, extend `PACKAGE_SOURCE_RULES` or `SINGLE_SOURCE_FALLBACKS`.
6. Regenerate the configuration with at least:

   ```bash
   python3 uts/build.py -t simple-idconfig-at386
   ```

   For a full installed-kernel style build, use `python3 uts/build.py -t kernel-system-at386`.

7. Inspect the generated outputs under `build/uts/i386/conf/cf.d/`, especially `conf.c`, `config.h`, `simple-idconfig.json`, and `driver-compose-report.json`.
8. If the driver is hardware-facing, validate it in QEMU and debug through the GDB stub instead of trying to infer behavior from source alone.

## Practical Notes

- The boot-floppy profile deliberately excludes many modules. If a driver exists in the full AT386 configuration but not in the floppy build, check the `simple-idconfig-at386-floppy` exclusions in `uts/build-specs/i386/kernel/10-config-and-link.yaml` before assuming the driver is broken.
- The source tree also contains add-on drivers under `uts/add-ons/`, but they are not part of the default AT386 staging lists. They do not appear in the generated tables until they are explicitly integrated into the modern build path.
- The legacy `master.d` makefiles are still useful as historical reference, but they are not the live control path anymore.