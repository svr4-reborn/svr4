# Syscall Porting Guide

This page is a practical companion to the full [syscall reference](syscalls.md). It is written for libc and runtime work rather than kernel maintenance.

## Start From `sysent[]`

The kernel's authoritative top-level syscall ABI is the `sysent[]` table in `uts/i386/os/sysent.c`.

That table gives you three things immediately:

- the raw syscall number,
- the raw argument count,
- the top-level handler function.

That is the right first anchor when implementing or auditing a libc wrapper. Do not start from random helper functions or header guesses when the dispatch table already tells you which entry point really owns the ABI.

## Expect Old-Style SVR4 Patterns

Several interfaces in this tree are not Linux-style one-syscall-one-operation ABIs. The kernel uses multiplexed entries heavily.

The most important cases for libc work are:

- `39` `pgrpsys`
- `48` `signal`
- `49` `msgsys`
- `50` `sysi86`
- `52` `shmsys`
- `53` `semsys`
- `57` `utssys`
- `78` `rfsys`
- `84` `sysfs`
- `99` `sigpending`
- `100` `context`
- `106` `nfssys`
- `109` `hrtsys`

For these, the top-level syscall number is only the first half of the ABI. The second half is the subcommand field and the argument structure expected by the dispatcher.

## Return Value Conventions

The kernel handlers in this tree usually follow the classic SVR4 convention:

- return `0` from the kernel handler for success,
- return an `errno` value from the kernel handler for failure,
- place scalar user-visible return values in `rval_t *rvp`.

That matters when porting libc wrappers, because a handler that returns success may still communicate the real user-visible value through `rvp->r_val1`, `rvp->r_val2`, or one of the typed aliases like `r_time` or `r_off`.

Examples:

- `read`, `write`, `readv`, `writev`: byte counts come back through `rvp->r_val1`.
- `open`, `creat`, `dup`, `pipe`: file descriptors are returned through `rvp` rather than through the handler's C return value.
- `time`, `lseek`, and similar calls use typed `rval_t` fields.

## `SETJUMP`, `ASYNC`, `IOSYS`

`sysent[]` also carries per-syscall flags.

- `SETJUMP`: the trap layer may need to establish restart or unwind state around the call.
- `ASYNC`: the path is marked as async-sensitive.
- `IOSYS`: the path is part of the core I/O syscall set.

For libc work, these flags are mostly diagnostic rather than directly consumable. They are still useful when trying to understand why two seemingly similar calls are treated differently by the kernel entry layer.

## What To Check After Finding The Handler

Once you know the owning handler, check these things in order:

1. Whether the handler reads a dedicated argument struct.
2. Whether the handler immediately switches on a subcommand.
3. Whether the handler copies data in or out with versioned user structs.
4. Whether the handler is conditionally stubbed by package configuration.

The biggest libc mistakes on this tree come from stopping at step 1 and assuming the user ABI is obvious.

## Package Stubs Matter

Some syscall families appear twice in the tree:

- a real implementation under `uts/i386/fs/...` or `uts/i386/os/...`, and
- a package stub under `uts/i386/master.d/.../stubs.c`.

That does not mean the ABI is fake. It usually means the subsystem is optional in the kernel configuration.

The current tree shows that pattern for:

- `rfsys`,
- `nfssys`,
- `evsys` / `evtrapret`,
- `async` / `acancel`.

For libc, that means you should separate these questions:

- what is the ABI when the subsystem is present?
- what failure mode should userland expect when the subsystem is absent?

## Best Candidates For Early libc Support

If the goal is a usable libc rather than total syscall coverage, the highest-value buckets are:

- process and credential syscalls,
- file descriptor and pathname I/O,
- memory management,
- signal control,
- stat/statvfs,
- System V IPC,
- STREAMS-facing socket and message plumbing where the userland ABI depends on it.

The syscall reference already groups the major families by number range, which is usually enough to keep implementation work staged.

## Files Worth Keeping Open While Porting

- `uts/i386/os/sysent.c`
- `uts/i386/sys/syscall.h`
- `uts/i386/fs/vncalls.c`
- `uts/i386/os/scalls.c`
- `uts/i386/os/grow.c`
- `uts/i386/os/exit.c`
- `uts/i386/os/exec.c`
- `uts/i386/os/msg.c`
- `uts/i386/os/sem.c`
- `uts/i386/os/shm.c`
- `uts/i386/fs/strcalls.c`

Those files cover most of the ABI surface that a libc port hits first.