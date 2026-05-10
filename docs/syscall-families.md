# Multiplexed Syscall Families

This page expands the multiplexed entries from the main [syscall reference](syscalls.md). These are the syscall numbers where one top-level table entry hides multiple logical operations.

## Why These Matter

Classic SVR4 makes heavy use of multiplexed syscall ABIs. From a libc perspective, these are the places where a Linux-shaped wrapper strategy fails fastest.

The kernel generally chooses one of these patterns:

- the first integer argument is an opcode,
- an embedded struct starts with an opcode field,
- the apparent syscall name in `sysent[]` is only one historical member of a broader family.

## `pgrpsys` (`39`)

Top-level dispatch comments live in `uts/i386/sys/syscall.h`, and the implementation is in `uts/i386/os/scalls.c`.

| Subcode | Operation | Practical libc consequence |
|---:|---|---|
| 0 | `getpgrp()` | No path or pointer arguments; scalar return only. |
| 1 | `setpgrp()` | Historical BSD/System V style process-group creation. |
| 2 | `getsid(pid)` | Session query path shares the same syscall number. |
| 3 | `setsid()` | Session creation is not a separate top-level syscall here. |
| 4 | `getpgid(pid)` | Process-group query variant. |
| 5 | `setpgid(pid, pgid)` | POSIX-style setpgid operation. |

## `signal` (`48`)

This is the old signal family, encoded partly in the signal number argument.

| Encoding | Operation |
|---|---|
| plain signal number | `signal()` |
| `SIGDEFER` bit set | `sigset()` |
| `SIGHOLD` bit set | `sighold()` |
| `SIGRELSE` bit set | `sigrelse()` |
| `SIGIGNORE` bit set | `sigignore()` |
| `SIGPAUSE` bit set | `sigpause()` |

The important implementation detail is that the libc-visible API split is not mirrored 1:1 in the syscall table.

## System V IPC Families

### `msgsys` (`49`)

Implementation: `uts/i386/os/msg.c`.

| Opcode | Operation |
|---:|---|
| 0 | `msgget` |
| 1 | `msgctl` |
| 2 | `msgrcv` |
| 3 | `msgsnd` |

### `shmsys` (`52`)

Implementation: `uts/i386/os/shm.c`.

| Opcode | Operation |
|---:|---|
| 0 | `shmat` |
| 1 | `shmctl` |
| 2 | `shmdt` |
| 3 | `shmget` |

### `semsys` (`53`)

Implementation: `uts/i386/os/sem.c`.

| Opcode | Operation |
|---:|---|
| 0 | `semctl` |
| 1 | `semget` |
| 2 | `semop` |

## `sysi86` (`50`)

This is the widest and least libc-friendly multiplexer in the tree. The stable user-facing surface is whatever `uts/i386/sys/sysi86.h` names and whatever `uts/i386/os/sysi86.c` actually switches on.

Notable command groups named directly in the kernel headers:

- swap-management operations: `SI86SWAP`, `SI86SWPI`
- boot/configuration queries: `SI86SYM`, `SI86CONF`, `SI86BOOT`, `SI86AUTO`, `SI86EDT`
- machine/time control: `STIME`, `SETNAME`, `RTODC`, `SI86MEM`
- firmware/platform control: `SI86TODEMON`, `SI86CCDEMON`, `SI86CACHE`
- testing/debug operations: `SI86DELMEM`, `SI86ADDMEM`
- v86/vm86 family: `SI86V86`, `SI86VM86`, `SI86VMENABLE`
- descriptor manipulation: `SI86DSCR`
- XENIX compatibility commands: `SI86SHFIL`, `SI86PCHRGN`, `SI86BADVISE`, `SI86SHRGN`, `SI86CHIDT`, `SI86EMULRDA`

For libc work, the correct strategy is usually not to expose this wholesale. Implement only the specific libc-visible functions that are known to route through it.

## `utssys` (`57`)

Implementation: `uts/i386/os/scalls.c`.

| Subcode | Operation |
|---:|---|
| 0 | obsolete `uname` |
| 2 | `ustat` |
| 3 | `fusers` |

This family is a good example of why syscall names alone are misleading: a single entry number mixes system-identity and filesystem-usage queries.

## `rfsys` (`78`)

Implementation: `uts/i386/fs/rfs/rf_sys.c`; constants in `uts/i386/sys/rf_sys.h`.

The first machine word of the user argument block is the operation code.

Named operations in this tree:

- `RF_FUMOUNT`
- `RF_SENDUMSG`
- `RF_GETUMSG`
- `RF_LASTUMSG`
- `RF_SETDNAME`
- `RF_GETDNAME`
- `RF_SETIDMAP`
- `RF_FWFD`
- `RF_VFLAG`
- `RF_VERSION`
- `RF_RUNSTATE`
- `RF_TUNEABLE`
- `RF_CLIENTS`
- `RF_RESOURCES`
- `RF_ADVFS`
- `RF_UNADVFS`
- `RF_START`
- `RF_STOP`
- `RF_DEBUG`

The optional `RFSUNMOUNTHACK` block adds more opcodes in the header, but the main dispatch table in `rf_sys.c` covers the core set above.

## `sysfs` (`84`)

Implementation: `uts/i386/fs/vfs.c`; constants in `uts/i386/sys/fstyp.h`.

| Opcode | Meaning |
|---:|---|
| `GETFSIND` | filesystem name to index |
| `GETFSTYP` | index to filesystem name |
| `GETNFSTYP` | number of configured filesystem types |

## `sigpending` (`99`) and `context` (`100`)

These are small multiplexors but still worth calling out because userland often assumes they are single-purpose syscalls.

### `sigpending`

| Subcode | Operation |
|---:|---|
| 1 | `sigpending(set)` |
| 2 | `sigfillset(set)` |

### `context`

| Subcode | Operation |
|---:|---|
| 0 | `getcontext(ucp)` |
| 1 | `setcontext(ucp)` |

## `nfssys` (`106`)

Implementation: `uts/i386/fs/nfs/nfssys.c`; argument definitions in `uts/i386/nfs/nfssys.h`.

| Opcode | Operation | Extra argument block |
|---:|---|---|
| `NFS_SVC` | enter NFS service path | `struct nfs_svc_args` |
| `ASYNC_DAEMON` | async NFS daemon operation | none |
| `EXPORTFS` | export filesystem | `struct exportfs_args` |
| `NFS_GETFH` | obtain file handle | `struct nfs_getfh_args` |
| `NFS_CNVT` | convert file handle to fd-like result | `struct nfs_cnvt_args` |

## `hrtsys` (`109`)

Implementation: `uts/i386/io/hrtimers.c`; command set in `uts/i386/sys/hrtcntl.h`.

Outer dispatch:

| Opcode | Operation |
|---:|---|
| 0 | `HRTCNTL` |
| 1 | `HRTALARM` |
| 2 | `HRTSLEEP` |
| 3 | `HRTCANCEL` |

Inner timer command vocabulary includes:

- `HRT_GETRES`
- `HRT_TOFD`
- `HRT_STARTIT`
- `HRT_GETIT`
- `HRT_ALARM`
- `HRT_RALARM`
- `HRT_TODALARM`
- `HRT_INT_RPT`
- `HRT_TOD_RPT`
- `HRT_PENDING`
- `HRT_INTSLP`
- `HRT_TODSLP`
- BSD compatibility variants: `HRT_BSD`, `HRT_BSD_PEND`, `HRT_RBSD`, `HRT_BSD_REP`, `HRT_BSD_CANCEL`

This is another family where libc generally wants narrow wrappers around named functions, not a generic raw escape hatch.

## `priocntlsys` (`112`) and `memcntl` (`131`)

These are not classic tiny opcode multiplexors, but they still branch internally on command fields and should be treated the same way during ABI analysis.

- `priocntlsys` takes `pc_version`, `procset_t *`, `cmd`, and `arg`, then dispatches on `cmd` inside `uts/i386/disp/priocntl.c`.
- `memcntl` takes six raw arguments and dispatches on `uap->cmd` inside `uts/i386/os/lock.c`.

## Conditional Families

The kernel tree also makes it clear that some families are optional package surfaces rather than guaranteed runtime features.

- `evsys` / `evtrapret` have declarations plus `master.d/events/stubs.c`.
- `async` / `acancel` have interface headers plus `master.d/async/stubs.c`.
- `rfsys` and `nfssys` have real implementations and also package stubs under `master.d`.

That distinction is important for libc work: ABI shape and runtime availability are separate questions.