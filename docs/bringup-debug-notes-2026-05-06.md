Bring-up debug notes

Temporary notes for the current SVR4/i386 boot bring-up.

Hotspots that still look compiler/ABI-sensitive:

- `uts/i386/os/fork.c`: `procdup()` and `cpreg()` depend on saved register variables and a specific stack/prologue layout. This is the highest-risk path and already required a child-return fix.
- `uts/i386/ml/misc.s`: `resume()` restores `eax`, `ebx`, `esi`, and `edi` into a live C activation before a plain `ret`. This is the assembly half of the same fork coroutine.
- `uts/i386/io/ctl87.c`: `get87()` used `%ebp`-relative inline asm inside C. Rewritten on 2026-05-06 to use operand-based inline asm.
- `uts/i386/os/slp.c`: KPERF hooks read the caller PC with `movl 4(%ebp), Kpc`. Likely harmless unless KPERF is active, but it depends on frame pointers.
- `uts/i386/io/prf.c`: `prfintr()` walks the `%ebp` chain in inline asm to recover an interrupted caller. Profiling/debug path, but frame-pointer-dependent.
- `uts/i386/io/kmacct.c`: `getfp()`/`getcaller()` backtrace logic assumes a conventional frame chain.
- `uts/i386/sys/kdebugger.h`: `db_get_stack()` snapshots `%ebp`/`%esp` for stack tracing. Debug-only, but still ABI-sensitive.
- `uts/i386/vm/faultcatch.h` and `uts/i386/vm/ucopy.c`: explicit kernel `setjmp`/`longjmp` fault recovery. Non-local control flow by design, but it is at least explicit and self-contained.

Likely lower priority unless symptoms point there:

- Hand-written assembly trap/entry paths such as `uts/i386/ml/ttrap.s` and `uts/i386/ml/v86gptrap.s`. These are machine-dependent by nature, but they are self-contained assembly rather than C relying on undocumented compiler layout.

Current runtime blocker after the fork/FPU fixes:

- `init` reaches `r0:0:respawn:/sbin/-sh </dev/console >/dev/console 2>&1` and respawns rapidly.
- Boot floppy proto data under `proto/i386/at386/` shows this is intentional installer-shell behavior, not a stray string.
- `proto/i386/at386/cmd/boot_make.sh` historically created `/sbin/-sh` as a hard link to `/sbin/sh` on the mounted boot floppy.
- Next checks should focus on whether the modern image builder preserves that link or otherwise provides an executable `/sbin/-sh` with its runtime dependencies.