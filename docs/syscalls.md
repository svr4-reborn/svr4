# SVR4 Kernel Syscall Reference

This document is derived only from kernel sources under `uts/`, using the syscall dispatch table in `uts/i386/os/sysent.c`, public syscall numbers in `uts/i386/sys/syscall.h`, and the individual handler implementations or dispatch headers those entries point at.

## Using This Reference

This page is the flat, complete syscall inventory.

For follow-on work, the most useful companion pages are:

- [Syscall Porting Guide](syscall-porting-guide.md): how to turn the kernel view of the ABI into libc wrappers.
- [Multiplexed Syscall Families](syscall-families.md): deeper coverage of the syscall entries that dispatch multiple logical operations.

If you are implementing a wrapper, the usual path is:

1. Find the syscall number in `uts/i386/os/sysent.c`.
2. Confirm the exported number and any public comments in `uts/i386/sys/syscall.h`.
3. Read the owning handler file named in the `Handler` column.
4. If the handler is a family dispatcher, jump to the family-specific page before writing the wrapper.

## Conventions

- The raw syscall ABI is defined by `struct sysent sysent[]` in `uts/i386/os/sysent.c`.
- `Argc` below is the raw argument count from `sysent[]`.
- For most handlers, the kernel-side C function returns `0` on success or an `errno` value on failure, and scalar syscall results are written through `rval_t *rvp` (`r_val1` / `r_val2`).
- `Arguments` are named from local kernel argument structs where present; where the old K&R code does not expose a neat struct in the immediate handler, names come from comments, dispatch code, or the nearby exported headers in `uts/i386/sys`.
- `Source note` is intentionally brief: it points at the primary implementation file or the immediate dispatch file for that syscall.

## Kernel ABI Notes

- The syscall table includes entries that are present in the ABI even when the configured kernel may stub them out through `master.d/.../stubs.c`.
- Several important user-visible interfaces are multiplexed behind a single top-level syscall entry, especially System V IPC, signal control, remote filesystem support, and machine-specific control.
- For most handlers, the handler's C return value is not the user-visible syscall result. Success usually means `0` from the handler and the actual scalar result in `rval_t *rvp`.
- The trap-layer return convention is defined in `uts/i386/os/trap.c`, not in the individual syscall handlers. `systrap()` clears the saved carry flag before dispatch, writes successful results back through `rval_t`, and on failure stores a positive `errno` in `EAX` and sets carry. The current code does this as `r0ptr[EAX] = error & 0377; flags->fl_cf = 1;`, so the kernel source documents a positive error-code return with carry set and, in this tree, an 8-bit masked user-visible errno value.
- The errno namespace itself is declared in `uts/i386/sys/errno.h`. That header currently defines values ranging from `EPERM = 1` up to `EIORESID = 500`, but the syscall return path in `systrap()` is still the authoritative source for what the user-visible trap return ABI looks like.
- The `sysent[]` flags such as `SETJUMP`, `ASYNC`, and `IOSYS` are part of trap-layer behavior, not a direct user ABI, but they are still useful when understanding syscall entry semantics.

## Syscalls 0-39

| No. | Public name | Argc | Handler | Arguments | Returns | What it does | Source note |
|---:|---|---:|---|---|---|---|---|
| 0 | `indir` | 0 | `nosys` | none | `ENOSYS` path | Reserved indirect syscall slot; not implemented here. | Dispatch entry only in `uts/i386/os/sysent.c`. |
| 1 | `exit` | 1 | `rexit` | `int rval` | no user return | Terminates the calling process and records its exit status. | `uts/i386/os/exit.c`, old-style exit entry. |
| 2 | `fork` | 0 | `fork` | none | parent gets child PID, child gets `0` | Duplicates the calling process. | `uts/i386/os/fork.c`. |
| 3 | `read` | 3 | `read` | `int fd, void *buf, unsigned count` | bytes read in `rvp->r_val1` | Reads data from a file descriptor into a user buffer. | `uts/i386/fs/vncalls.c`, shared read/write path. |
| 4 | `write` | 3 | `write` | `int fd, const void *buf, unsigned count` | bytes written in `rvp->r_val1` | Writes data from a user buffer to a file descriptor. | `uts/i386/fs/vncalls.c`, shared read/write path. |
| 5 | `open` | 3 | `open` | `char *path, int flags, int mode` | new fd in `rvp->r_val1` | Opens or creates a file and allocates a descriptor. | `uts/i386/fs/vncalls.c`, `open()` / `copen()`. |
| 6 | `close` | 1 | `close` | `int fd` | status only | Closes a file descriptor. | `uts/i386/fs/vncalls.c`. |
| 7 | `wait` | 0 | `wait` | none | child status / pid via legacy wait path | Waits for child state change using the old `wait` interface. | `uts/i386/os/exit.c`, older wait entry above `waitsys()`. |
| 8 | `creat` | 2 | `creat` | `char *path, int mode` | new fd in `rvp->r_val1` | Creates/truncates a file using the historical `creat` ABI. | `uts/i386/fs/vncalls.c`. |
| 9 | `link` | 2 | `link` | `char *from, char *to` | status only | Creates a hard link. | `uts/i386/fs/vncalls.c`. |
| 10 | `unlink` | 1 | `unlink` | `char *path` | status only | Removes a directory entry. | `uts/i386/fs/vncalls.c`. |
| 11 | `exec` | 2 | `exec` | `char *fname, char **argv` | no normal return on success | Replaces the process image using the older two-argument exec ABI. | `uts/i386/os/exec.c`. |
| 12 | `chdir` | 1 | `chdir` | `char *path` | status only | Changes the current working directory. | `uts/i386/fs/vncalls.c`. |
| 13 | `time` | 0 | `gtime` | none | seconds in `rvp->r_time` | Returns the current time. | `uts/i386/os/scalls.c`, `gtime()`. |
| 14 | `mknod` | 3 | `mknod` | `char *path, int mode, dev_t dev` | status only | Creates a filesystem node, including special files. | `uts/i386/fs/vncalls.c`. |
| 15 | `chmod` | 2 | `chmod` | `char *path, int mode` | status only | Changes file mode bits by pathname. | `uts/i386/fs/vncalls.c`. |
| 16 | `chown` | 3 | `chown` | `char *path, uid_t uid, gid_t gid` | status only | Changes file owner/group by pathname. | `uts/i386/fs/vncalls.c`. |
| 17 | `brk` | 1 | `brk` | `void *nva` | status only | Moves the process data-segment break. | `uts/i386/os/grow.c`. |
| 18 | `stat` | 2 | `stat` | `char *path, struct stat *buf` | status + copyout | Returns file status by pathname. | `uts/i386/fs/vncalls.c`. |
| 19 | `lseek` | 3 | `lseek` | `int fd, off_t off, int whence` | new offset in `rvp->r_off` | Repositions a file offset. | `uts/i386/fs/vncalls.c`. |
| 20 | `getpid` | 0 | `getpid` | none | PID in `rvp->r_val1` | Returns the calling process ID. | `uts/i386/os/pid.c` / `scalls` support. |
| 21 | `mount` | 6 | `mount` | path/type/data/flags/options style mount args | status only | Mounts a filesystem through the VFS layer. | `uts/i386/fs/vfs.c`. |
| 22 | `umount` | 1 | `umount` | `char *path` | status only | Unmounts a filesystem. | `uts/i386/fs/vfs.c`. |
| 23 | `setuid` | 1 | `setuid` | `uid_t uid` | status only | Sets process user IDs subject to permission checks. | `uts/i386/os/scalls.c`. |
| 24 | `getuid` | 0 | `getuid` | none | real UID in `rvp->r_val1` | Returns the real user ID. | `uts/i386/os/scalls.c`. |
| 25 | `stime` | 1 | `stime` | `time_t time` | status only | Sets the system time; privileged. | `uts/i386/os/scalls.c`. |
| 26 | `ptrace` | 4 | `ptrace` | request/pid/addr/data style tracing args | request-specific | Process tracing/debugging interface. | `uts/i386/os/sig.c`, `ptrace()`. |
| 27 | `alarm` | 1 | `alarm` | `unsigned seconds` | prior alarm state / status | Arms the per-process alarm timer. | `uts/i386/os/scalls.c`. |
| 28 | `fstat` | 2 | `fstat` | `int fd, struct stat *buf` | status + copyout | Returns file status by open descriptor. | `uts/i386/fs/vncalls.c`. |
| 29 | `pause` | 0 | `pause` | none | interrupted wait | Suspends the process until signal delivery. | `uts/i386/os/scalls.c`. |
| 30 | `utime` | 2 | `utime` | `char *path, time_t *times` | status only | Updates file access/modification times. | `uts/i386/fs/vncalls.c`. |
| 31 | `stty` | 2 | `stty` | `int fd, void *arg` | status only | Historical terminal-setting syscall; implemented through ioctl-style terminal control. | `uts/i386/fs/vncalls.c`. |
| 32 | `gtty` | 2 | `gtty` | `int fd, void *arg` | status + copyout | Historical terminal-query syscall. | `uts/i386/fs/vncalls.c`. |
| 33 | `access` | 2 | `access` | `char *path, int mode` | status only | Checks pathname accessibility using caller credentials. | `uts/i386/fs/vncalls.c`. |
| 34 | `nice` | 1 | `nice` | priority increment | resulting priority / status | Adjusts scheduling niceness. | `uts/i386/os/scalls.c`. |
| 35 | `statfs` | 4 | `statfs` | `char *path, struct statfs *buf, int len, int fstyp` | status + copyout | Returns filesystem statistics by pathname. | `uts/i386/fs/vfs.c`. |
| 36 | `sync` | 0 | `syssync` | none | status only | Flushes dirty filesystem state. | `uts/i386/fs/vfs.c`. |
| 37 | `kill` | 2 | `kill` | `pid_t pid, int sig` | status only | Sends a signal to a process or process set selected by pid semantics. | `uts/i386/os/scalls.c`. |
| 38 | `fstatfs` | 4 | `fstatfs` | `int fd, struct statfs *buf, int len, int fstyp` | status + copyout | Returns filesystem statistics by descriptor. | `uts/i386/fs/vfs.c`. |
| 39 | `pgrpsys` | 3 | `setpgrp` | multiplexed process-group/session args | subcode-specific | Process-group and session control multiplexor. | `uts/i386/os/scalls.c`, see subcode section below. |

## Syscalls 40-79

| No. | Public name | Argc | Handler | Arguments | Returns | What it does | Source note |
|---:|---|---:|---|---|---|---|---|
| 40 | `xenix` | 0 | `cxenix` | subcode-dependent XENIX compatibility args | subcode-specific | XENIX compatibility multiplexor. | `uts/i386/os/cxenix.c`. |
| 41 | `dup` | 1 | `dup` | `int fdes` | new fd in `rvp->r_val1` | Duplicates a file descriptor. | `uts/i386/fs/vncalls.c`. |
| 42 | `pipe` | 0 | `pipe` | none | new fds in `rvp->r_val1/r_val2` | Creates a pipe. | `uts/i386/os/pipe.c`. |
| 43 | `times` | 1 | `times` | `struct tms *buf` | elapsed ticks + copyout | Returns process and child CPU accounting times. | `uts/i386/os/scalls.c`. |
| 44 | `profil` | 4 | `profil` | profiling buffer/base/scale args | status only | Enables execution-time profiling into a user buffer. | `uts/i386/os/scalls.c`. |
| 45 | `plock` | 1 | `lock_mem` | `int op` | status only | Locks process text/data or future memory against swapping. | `uts/i386/os/lock.c`. |
| 46 | `setgid` | 1 | `setgid` | `gid_t gid` | status only | Sets group IDs subject to privilege checks. | `uts/i386/os/scalls.c`. |
| 47 | `getgid` | 0 | `getgid` | none | real GID in `rvp->r_val1` | Returns the real group ID. | `uts/i386/os/scalls.c`. |
| 48 | `signal` | 2 | `ssig` | legacy signal opcode in `sig`, optional handler | subcode-specific | Historical signal control multiplexor used for `signal()`, `sigset()`, `sighold()`, `sigrelse()`, `sigignore()`, `sigpause()`. | `uts/i386/os/scalls.c`, see subcode section below. |
| 49 | `msgsys` | 6 | `msgsys` | `opcode` + message-queue-specific args | subcode-specific | System V message queue multiplexor. | `uts/i386/os/msg.c`, see subcode section below. |
| 50 | `sysi86` | 4 | `sysi86` | `int cmd, int arg1, int arg2, int arg3` | cmd-specific | i386-specific system interface multiplexor. | `uts/i386/os/sysi86.c`, `uts/i386/sys/sysi86.h`. |
| 51 | `acct` | 1 | `sysacct` | `char *file` | status only | Enables, changes, or disables process accounting. | `uts/i386/os/acct.c`. |
| 52 | `shmsys` | 4 | `shmsys` | `opcode` + shared-memory-specific args | subcode-specific | System V shared memory multiplexor. | `uts/i386/os/shm.c`, see subcode section below. |
| 53 | `semsys` | 5 | `semsys` | `opcode` + semaphore-specific args | subcode-specific | System V semaphore multiplexor. | `uts/i386/os/sem.c`, see subcode section below. |
| 54 | `ioctl` | 3 | `ioctl` | `int fd, int cmd, void *arg` | request-specific | Device and stream control entry. | `uts/i386/fs/vncalls.c`. |
| 55 | `uadmin` | 3 | `uadmin` | command/function/mdep args | command-specific | System administration entry for reboot/halt-like operations. | `uts/i386/os/scalls.c`. |
| 56 | `uexch` / reserved | 3 or 0 | `uexch` or `nosys` | MEGA-only exchange args if built | build-dependent | Reserved for `uexch`; this tree dispatches it only under `#ifdef MEGA`, otherwise `nosys`. | Conditional in `uts/i386/os/sysent.c`. |
| 57 | `utssys` | 4 | `utssys` | `char *buf, int mv, int type, void *outbuf` style by subcode | subcode-specific | UTS/uname/ustat/fusers multiplexor. | `uts/i386/os/scalls.c`, see subcode section below. |
| 58 | `fsync` | 1 | `fsync` | `int fd` | status only | Forces a file's dirty state to stable storage. | `uts/i386/fs/vncalls.c`. |
| 59 | `execve` | 3 | `exece` | `char *fname, char **argv, char **envp` | no normal return on success | Replaces the process image with argv/envp support. | `uts/i386/os/exec.c`. |
| 60 | `umask` | 1 | `umask` | `mode_t mask` | old mask in `rvp->r_val1` | Sets the process file-creation mask. | `uts/i386/os/scalls.c`. |
| 61 | `chroot` | 1 | `chroot` | `char *path` | status only | Changes the process root directory; privileged. | `uts/i386/os/scalls.c`. |
| 62 | `fcntl` | 3 | `fcntl` | `int fd, int cmd, void *arg` | command-specific | File-control and advisory-locking interface. | `uts/i386/fs/vncalls.c`. |
| 63 | `ulimit` | 2 | `ulimit` | command/value style old resource-limit args | command-specific | Historical resource-limit interface. | `uts/i386/os/scalls.c`. |
| 64 | reserved | 0 | `nosys` | none | `ENOSYS` path | Reserved for UNIX PC. | Reserved slot in `uts/i386/os/sysent.c`. |
| 65 | reserved | 0 | `nosys` | none | `ENOSYS` path | Reserved for UNIX PC. | Reserved slot in `uts/i386/os/sysent.c`. |
| 66 | reserved | 0 | `nosys` | none | `ENOSYS` path | Reserved for UNIX PC. | Reserved slot in `uts/i386/os/sysent.c`. |
| 67 | reserved | 0 | `nosys` | none | `ENOSYS` path | Reserved slot once associated with file locking. | Reserved slot in `uts/i386/os/sysent.c`. |
| 68 | reserved | 0 | `nosys` | none | `ENOSYS` path | Reserved slot for local system calls. | Reserved slot in `uts/i386/os/sysent.c`. |
| 69 | reserved | 0 | `nosys` | none | `ENOSYS` path | Reserved slot once documented as inode-open. | Reserved slot in `uts/i386/os/sysent.c`. |
| 70 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused; comment says “was advfs”. | `uts/i386/os/sysent.c`. |
| 71 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused; comment says “was unadvfs”. | `uts/i386/os/sysent.c`. |
| 72 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused reserved slot. | `uts/i386/os/sysent.c`. |
| 73 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused reserved slot. | `uts/i386/os/sysent.c`. |
| 74 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused; comment says “was rfstart”. | `uts/i386/os/sysent.c`. |
| 75 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused reserved slot. | `uts/i386/os/sysent.c`. |
| 76 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused; comment says “was rdebug”. | `uts/i386/os/sysent.c`. |
| 77 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused; comment says “was rfstop”. | `uts/i386/os/sysent.c`. |
| 78 | `rfsys` | 6 | `rfsys` | first word is `opcode`, remaining args opcode-specific | subcode-specific | Remote File Sharing control/administration multiplexor. | `uts/i386/fs/rfs/rf_sys.c`, `uts/i386/sys/rf_sys.h`. |
| 79 | `rmdir` | 1 | `rmdir` | `char *path` | status only | Removes an empty directory. | `uts/i386/fs/vncalls.c`. |

## Syscalls 80-119

| No. | Public name | Argc | Handler | Arguments | Returns | What it does | Source note |
|---:|---|---:|---|---|---|---|---|
| 80 | `mkdir` | 2 | `mkdir` | `char *path, int mode` | status only | Creates a directory. | `uts/i386/fs/vncalls.c`. |
| 81 | `getdents` | 3 | `getdents` | `int fd, struct dirent *buf, unsigned nbyte` | bytes copied in `rvp->r_val1` | Reads directory entries from an open directory descriptor. | `uts/i386/fs/vncalls.c`. |
| 82 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused; comment says “was libattach”. | `uts/i386/os/sysent.c`. |
| 83 | unused | 0 | `nosys` | none | `ENOSYS` path | Unused; comment says “was libdetach”. | `uts/i386/os/sysent.c`. |
| 84 | `sysfs` | 3 | `sysfs` | `int opcode, ...` | subcode-specific | Filesystem-type/name translation multiplexor. | `uts/i386/fs/vfs.c`, `uts/i386/sys/fstyp.h`. |
| 85 | `getmsg` | 4 | `getmsg` | `int fd, struct strbuf *ctl, struct strbuf *data, int *flags` | status / message state | Retrieves a STREAMS message. | `uts/i386/fs/strcalls.c`. |
| 86 | `putmsg` | 4 | `putmsg` | `int fd, struct strbuf *ctl, struct strbuf *data, int flags` | status only | Sends a STREAMS message. | `uts/i386/fs/strcalls.c`. |
| 87 | `poll` | 3 | `poll` | `struct pollfd *fds, unsigned nfds, int timeout` | ready count in `rvp->r_val1` | Polls descriptors for events. | `uts/i386/fs/vncalls.c`. |
| 88 | `lstat` | 2 | `lstat` | `char *path, struct stat *buf` | status + copyout | Stats a pathname without following the terminal symlink. | `uts/i386/fs/vncalls.c`. |
| 89 | `symlink` | 2 | `symlink` | `char *target, char *linkpath` | status only | Creates a symbolic link. | `uts/i386/fs/vncalls.c`. |
| 90 | `readlink` | 3 | `readlink` | `char *path, char *buf, int bufsz` | bytes copied in `rvp->r_val1` | Reads a symlink target into a user buffer. | `uts/i386/fs/vncalls.c`. |
| 91 | `setgroups` | 2 | `setgroups` | `int gidsetsize, gid_t *gidset` | status only | Sets supplementary groups. | `uts/i386/os/scalls.c`. |
| 92 | `getgroups` | 2 | `getgroups` | `int gidsetsize, gid_t *gidset` | count in `rvp->r_val1` + copyout | Returns supplementary group IDs. | `uts/i386/os/scalls.c`. |
| 93 | `fchmod` | 2 | `fchmod` | `int fd, int mode` | status only | Changes mode bits through an open descriptor. | `uts/i386/fs/vncalls.c`. |
| 94 | `fchown` | 3 | `fchown` | `int fd, uid_t uid, gid_t gid` | status only | Changes owner/group through an open descriptor. | `uts/i386/fs/vncalls.c`. |
| 95 | `sigprocmask` | 3 | `sigprocmask` | `int how, sigset_t *set, sigset_t *oset` | status + optional copyout | Modifies and/or queries the blocked signal mask. | `uts/i386/os/scalls.c`. |
| 96 | `sigsuspend` | 1 | `sigsuspend` | `sigset_t *set` | interrupted wait | Replaces the mask and sleeps atomically until signal delivery. | `uts/i386/os/scalls.c`. |
| 97 | `sigaltstack` | 2 | `sigaltstack` | `stack_t *ss, stack_t *oss` | status + optional copyout | Gets or sets the alternate signal stack. | `uts/i386/os/scalls.c`. |
| 98 | `sigaction` | 3 | `sigaction` | `int sig, struct sigaction *act, struct sigaction *oact` | status + optional copyout | Installs and queries signal dispositions. | `uts/i386/os/scalls.c`. |
| 99 | `sigpending` | 2 | `sigpending` | `int cmd, sigset_t *set` | status + copyout | Signal-pending-related multiplexor. | `uts/i386/os/scalls.c`, see subcode section below. |
| 100 | `context` | 2 | `setcontext` | `int cmd, ucontext_t *ucp` | command-specific | User-context get/set multiplexor. | `uts/i386/os/scalls.c`, see subcode section below. |
| 101 | `evsys` | 3 | `ev_evsys` | event-subsystem args | package-specific | Event-subsystem syscall; declarations exist in event headers. | Declared in `uts/i386/sys/evsys.h`; this tree also has `uts/i386/master.d/events/stubs.c`. |
| 102 | `evtrapret` | 0 | `ev_evtrapret` | none | package-specific | Event trap-return entry. | Declared in `uts/i386/sys/evsys.h`; stub exists in `uts/i386/master.d/events/stubs.c`. |
| 103 | `statvfs` | 2 | `statvfs` | `char *path, struct statvfs *buf` | status + copyout | Returns POSIX/VFS filesystem statistics by pathname. | `uts/i386/fs/vfs.c`. |
| 104 | `fstatvfs` | 2 | `fstatvfs` | `int fd, struct statvfs *buf` | status + copyout | Returns POSIX/VFS filesystem statistics by descriptor. | `uts/i386/fs/vfs.c`. |
| 105 | reserved | 0 | `nosys` | none | `ENOSYS` path | Reserved slot. | `uts/i386/os/sysent.c`. |
| 106 | `nfssys` | 2 | `nfssys` | `enum nfssys_op opcode, union nfssysargs arg` | subcode-specific | NFS control/utility multiplexor. | `uts/i386/fs/nfs/nfssys.c`, `uts/i386/nfs/nfssys.h`. |
| 107 | `waitsys` | 4 | `waitsys` | `idtype_t idtype, id_t id, siginfo_t *info, int options` | child state via `siginfo_t` | Enhanced wait interface (`waitid`-style semantics). | `uts/i386/os/exit.c`. |
| 108 | `sigsendsys` | 2 | `sigsendsys` | `procset_t *psp, int sig` | status only | Sends a signal to a procset. | `uts/i386/os/scalls.c`. |
| 109 | `hrtsys` | 5 | `hrtsys` | first word `opcode`, rest selected by sub-op | subcode-specific | High-resolution timer/sleep/alarm/cancel multiplexor. | `uts/i386/io/hrtimers.c`, `uts/i386/sys/hrtcntl.h`. |
| 110 | `acancel` | 3 | `async_cancel` | async-cancel args not further documented in this tree | status only | Cancels async I/O requests; only stubbed implementation is present here. | `uts/i386/master.d/async/stubs.c`. |
| 111 | `async` | 3 | `async` | async request wrapper, see `asyncop_t` | status only | Queues an asynchronous syscall request; only stubbed implementation is present here. | Interface in `uts/i386/sys/asyncsys.h`, stub in `uts/i386/master.d/async/stubs.c`. |
| 112 | `priocntlsys` | 4 | `priocntlsys` | `int pc_version, procset_t *psp, int cmd, caddr_t arg` | command-specific | Scheduling-class and process-priority control entry. | `uts/i386/disp/priocntl.c`. |
| 113 | `pathconf` | 2 | `pathconf` | `char *path, int name` | queried value in `rvp->r_val1` | Queries per-path configuration limits. | `uts/i386/fs/vncalls.c`. |
| 114 | `mincore` | 3 | `mincore` | `caddr_t addr, size_t len, char *vec` | status + copyout | Reports residency state of mapped pages. | `uts/i386/os/grow.c`. |
| 115 | `mmap` | 6 | `mmap` | `addr, len, prot, flags, fd, off` | mapped address in `rvp->r_val1` | Maps a file or anonymous memory into the address space. | `uts/i386/os/grow.c`. |
| 116 | `mprotect` | 3 | `mprotect` | `addr, len, prot` | status only | Changes protection on an address range. | `uts/i386/os/grow.c`. |
| 117 | `munmap` | 2 | `munmap` | `addr, len` | status only | Unmaps an address range. | `uts/i386/os/grow.c`. |
| 118 | `fpathconf` | 2 | `fpathconf` | `int fd, int name` | queried value in `rvp->r_val1` | Queries per-descriptor path configuration limits. | `uts/i386/fs/vncalls.c`. |
| 119 | `vfork` | 0 | `vfork` | none | parent/child split like fork variant | Creates a child with `vfork` semantics. | `uts/i386/os/fork.c`. |

## Syscalls 120-144

| No. | Public name | Argc | Handler | Arguments | Returns | What it does | Source note |
|---:|---|---:|---|---|---|---|---|
| 120 | `fchdir` | 1 | `fchdir` | `int fd` | status only | Changes current directory using an open descriptor. | `uts/i386/fs/vncalls.c`. |
| 121 | `readv` | 3 | `readv` | `int fd, struct iovec *iov, int iovcnt` | bytes read in `rvp->r_val1` | Performs a vectored read. | `uts/i386/fs/vncalls.c`. |
| 122 | `writev` | 3 | `writev` | `int fd, struct iovec *iov, int iovcnt` | bytes written in `rvp->r_val1` | Performs a vectored write. | `uts/i386/fs/vncalls.c`. |
| 123 | `xstat` | 3 | `xstat` | `int version, char *path, struct stat *buf` | status + copyout | Versioned pathname `stat` interface. | `uts/i386/fs/vncalls.c`. |
| 124 | `lxstat` | 3 | `lxstat` | `int version, char *path, struct stat *buf` | status + copyout | Versioned pathname `lstat` interface. | `uts/i386/fs/vncalls.c`. |
| 125 | `fxstat` | 3 | `fxstat` | `int version, int fd, struct stat *buf` | status + copyout | Versioned descriptor `stat` interface. | `uts/i386/fs/vncalls.c`. |
| 126 | `xmknod` | 4 | `xmknod` | `char *path, int mode, dev_t dev, void *xdev` | status only | Extended `mknod` variant. | `uts/i386/fs/vncalls.c`. |
| 127 | `clocal` | 5 | `clocal` | XENIX/local-compatibility args | subcode-specific | XENIX local-compatibility syscall family. | `uts/i386/os/cxenix.c`. |
| 128 | `setrlimit` | 2 | `setrlimit` | `int resource, struct rlimit *rlim` | status only | Sets a resource limit. | `uts/i386/os/scalls.c`. |
| 129 | `getrlimit` | 2 | `getrlimit` | `int resource, struct rlimit *rlim` | status + copyout | Returns a resource limit. | `uts/i386/os/scalls.c`. |
| 130 | `lchown` | 3 | `lchown` | `char *path, uid_t uid, gid_t gid` | status only | Changes symlink owner/group without following the final symlink. | `uts/i386/fs/vncalls.c`. |
| 131 | `memcntl` | 6 | `memcntl` | `addr, len, cmd, arg, attrp, mask` | command-specific | Memory-control multiplexor for memory locking/advice/attribute changes. | `uts/i386/os/lock.c`. |
| 132 | `getpmsg` | 5 | `getpmsg` | STREAMS priority-message receive args | status / message state | Retrieves a priority STREAMS message. | `uts/i386/fs/strcalls.c`. |
| 133 | `putpmsg` | 5 | `putpmsg` | STREAMS priority-message send args | status only | Sends a priority STREAMS message. | `uts/i386/fs/strcalls.c`. |
| 134 | `rename` | 2 | `rename` | `char *from, char *to` | status only | Renames a filesystem object. | `uts/i386/fs/vncalls.c`. |
| 135 | `uname` | 1 | `nuname` | `struct utsname *buf` | status + copyout | Returns the newer uname structure. | `uts/i386/os/scalls.c`. |
| 136 | `setegid` | 1 | `setegid` | `gid_t egid` | status only | Sets the effective group ID. | `uts/i386/os/scalls.c`. |
| 137 | `sysconfig` | 1 | `sysconfig` | `int which` | queried value in `rvp->r_val1` | Returns system-configuration constants and limits. | `uts/i386/os/scalls.c`. |
| 138 | `adjtime` | 2 | `adjtime` | `struct timeval *delta, struct timeval *olddelta` | status + optional copyout | Slews the system clock. | `uts/i386/os/scalls.c`. |
| 139 | `systeminfo` | 3 | `systeminfo` | `int cmd, char *buf, long count` | copied length / status | Gets system information strings or values selected by command. | `uts/i386/os/scalls.c`. |
| 140 | reserved | 0 | `nosys` | none | `ENOSYS` path | Reserved slot. | `uts/i386/os/sysent.c`. |
| 141 | `seteuid` | 1 | `seteuid` | `uid_t euid` | status only | Sets the effective user ID. | `uts/i386/os/scalls.c`. |
| 142 | `getresuid` | 3 | `getresuid` | `uid_t *ruid, uid_t *euid, uid_t *suid` | status + copyout | Returns the real, effective, and saved user IDs through three user pointers. | `uts/i386/os/scalls.c`. |
| 143 | `getresgid` | 3 | `getresgid` | `gid_t *rgid, gid_t *egid, gid_t *sgid` | status + copyout | Returns the real, effective, and saved group IDs through three user pointers. | `uts/i386/os/scalls.c`. |
| 144 | `ppoll` | 4 | `ppoll` | `struct pollfd *fds, unsigned long nfds, timestruc_t *tsp, sigset_t *sigmask` | ready count in `rvp->r_val1` | Polls descriptors with an optional temporary signal mask and a `timestruc_t` timeout. | `uts/i386/fs/vncalls.c`. |

## Multiplexed and Family Syscalls

These syscalls expose a single outer syscall number but then branch on a first argument or command field inside the handler.

### `pgrpsys` (`39`)

Kernel comment source: `uts/i386/sys/syscall.h`.

| Subcode | User-visible operation | Notes |
|---:|---|---|
| 0 | `getpgrp()` | Query current process group. |
| 1 | `setpgrp()` | Historical process-group creation API. |
| 2 | `getsid(pid)` | Query session ID. |
| 3 | `setsid()` | Create a new session. |
| 4 | `getpgid(pid)` | Query a target process's process group. |
| 5 | `setpgid(pid, pgid)` | Set process-group membership. |

Implementation note: `uts/i386/os/scalls.c`, handler named `setpgrp()` in the syscall table even though it dispatches the full family.

### `signal` (`48`)

Kernel comment source: `uts/i386/sys/syscall.h`; handler logic in `uts/i386/os/scalls.c`.

| Encoded command | User-visible operation | Notes |
|---|---|---|
| plain signal number | `signal(sig, func)` | Installs a simple handler. |
| `sig | SIGDEFER` | `sigset(sig, func)` | Installs handler with defer semantics. |
| `sig | SIGHOLD` | `sighold(sig)` | Blocks the signal. |
| `sig | SIGRELSE` | `sigrelse(sig)` | Unblocks the signal. |
| `sig | SIGIGNORE` | `sigignore(sig)` | Sets ignore disposition. |
| `sig | SIGPAUSE` | `sigpause(sig)` | Waits with temporary mask semantics. |

### `msgsys` (`49`)

Dispatch source: `uts/i386/os/msg.c`; public comments in `uts/i386/sys/syscall.h`.

| Opcode | Operation | Arguments |
|---:|---|---|
| 0 | `msgget` | `key_t key, int msgflg` |
| 1 | `msgctl` | `int msqid, int cmd, struct msqid_ds *buf` |
| 2 | `msgrcv` | `int msqid, struct msgbuf *msgp, size_t msgsz, long msgtyp, int msgflg` |
| 3 | `msgsnd` | `int msqid, struct msgbuf *msgp, size_t msgsz, int msgflg` |

### `shmsys` (`52`)

Dispatch source: `uts/i386/os/shm.c`; public comments in `uts/i386/sys/syscall.h`.

| Opcode | Operation | Arguments |
|---:|---|---|
| 0 | `shmat` | `int shmid, void *shmaddr, int shmflg` |
| 1 | `shmctl` | `int shmid, int cmd, struct shmid_ds *buf` |
| 2 | `shmdt` | `void *shmaddr` |
| 3 | `shmget` | `key_t key, size_t size, int shmflg` |

### `semsys` (`53`)

Dispatch source: `uts/i386/os/sem.c`; public comments in `uts/i386/sys/syscall.h`.

| Opcode | Operation | Arguments |
|---:|---|---|
| 0 | `semctl` | `int semid, int semnum, int cmd, union semun arg` |
| 1 | `semget` | `key_t key, int nsems, int semflg` |
| 2 | `semop` | `int semid, struct sembuf *sops, size_t nsops` |

### `sysi86` (`50`)

Command constants are declared in `uts/i386/sys/sysi86.h`, and the main dispatch switch is in `uts/i386/os/sysi86.c`.

The outer ABI is four raw arguments: `cmd`, `arg1`, `arg2`, `arg3`. The handler branches on `cmd`.

Visible command definitions in this tree include:

- `SI86SWPI`: general swap interface.
- `SI86SYM`: copy out boot-built symbol table metadata.
- `SI86CONF`: copy out boot-built configuration table.
- `SI86BOOT`: return boot-program name/timestamp information.
- `SI86AUTO`: query whether auto-config boot was done.
- `SI86EDT`: copy out EDT contents.
- `SI86SWAP`: legacy swap declaration interface.
- `SI86FPHW`: query floating-point hardware.
- `STIME`: set internal time.
- `SETNAME`: rename the system.
- `RTODC`: read time-of-day clock.
- `SI86KSTR`: copy a kernel string to user memory.
- `SI86MEM`: return memory size.
- `SI86TODEMON`, `SI86CCDEMON`, `SI86CACHE`, `SI86DELMEM`, `SI86ADDMEM`.
- `SI86V86`, `SI86VM86`, `SI86VMENABLE`: virtual-8086 related operations.
- `SI86SLTIME`: set local time correction.
- `SI86DSCR`: set a segment or gate descriptor, using `struct ssd` from `sysi86.h`.
- `SI86NFA`, `SI86LIMUSER`, `SI86RDID`, `SI86RDBOOT`.
- XENIX support commands: `SI86SHFIL`, `SI86PCHRGN`, `SI86BADVISE`, `SI86SHRGN`, `SI86CHIDT`, `SI86EMULRDA`.

Implementation note: the tree contains a large command switch in `uts/i386/os/sysi86.c`; this document lists the commands explicitly named in the kernel headers and in the visible dispatch switch, rather than inferring undocumented behavior.

### `utssys` (`57`)

Public comments come from `uts/i386/sys/syscall.h`; dispatch logic lives in `uts/i386/os/scalls.c`.

| Subcode | Operation | Arguments |
|---:|---|---|
| 0 | obsolete `uname` | `struct utsname *obuf` |
| 2 | `ustat` | `dev_t dev, struct ustat *obuf` |
| 3 | `fusers` | `char *path, int flags, void *obuf` |

### `rfsys` (`78`)

The main dispatch table is explicit in `uts/i386/fs/rfs/rf_sys.c`; command constants are in `uts/i386/sys/rf_sys.h`.

| Opcode | Operation |
|---:|---|
| 1 | `RF_FUMOUNT` |
| 2 | `RF_SENDUMSG` |
| 3 | `RF_GETUMSG` |
| 4 | `RF_LASTUMSG` |
| 5 | `RF_SETDNAME` |
| 6 | `RF_GETDNAME` |
| 7 | `RF_SETIDMAP` |
| 8 | `RF_FWFD` |
| 9 | `RF_VFLAG` |
| 10 | `RF_VERSION` |
| 11 | `RF_RUNSTATE` |
| 12 | `RF_TUNEABLE` |
| 13 | `RF_CLIENTS` |
| 14 | `RF_RESOURCES` |
| 15 | `RF_ADVFS` |
| 16 | `RF_UNADVFS` |
| 17 | `RF_START` |
| 18 | `RF_STOP` |
| 19 | `RF_DEBUG` |

Additional optional `RFSUNMOUNTHACK` opcodes are also defined in `rf_sys.h`: `RF_GETCAP`, `RF_PUTCAP`, `RF_SUBMNTS`, `RF_FUSERS`, `RF_UNMOUNT`.

### `sysfs` (`84`)

Dispatch source: `uts/i386/fs/vfs.c`; opcode constants from `uts/i386/sys/fstyp.h`.

| Opcode | Operation |
|---:|---|
| 1 | `GETFSIND`: translate filesystem name to `vfssw` index |
| 2 | `GETFSTYP`: translate `vfssw` index to filesystem name |
| 3 | `GETNFSTYP`: return configured filesystem-type count |

### `sigpending` family (`99`)

Public comments in `uts/i386/sys/syscall.h`; handler dispatch in `uts/i386/os/scalls.c`.

| Subcode | Operation |
|---:|---|
| 1 | `sigpending(set)` |
| 2 | `sigfillset(set)` |

### `context` (`100`)

Public comments in `uts/i386/sys/syscall.h`; handler dispatch in `uts/i386/os/scalls.c`.

| Subcode | Operation |
|---:|---|
| 0 | `getcontext(ucp)` |
| 1 | `setcontext(ucp)` |

### `nfssys` (`106`)

Opcode enum and argument union are defined in `uts/i386/nfs/nfssys.h`; dispatch is in `uts/i386/fs/nfs/nfssys.c`.

| Opcode | Operation | Argument carrier |
|---:|---|---|
| 0 | `NFS_SVC` | `struct nfs_svc_args { int fd; }` |
| 1 | `ASYNC_DAEMON` | no extra args |
| 2 | `EXPORTFS` | `struct exportfs_args { char *dname; struct export *uex; }` |
| 3 | `NFS_GETFH` | `struct nfs_getfh_args { char *fname; fhandle_t *fhp; }` |
| 4 | `NFS_CNVT` | `struct nfs_cnvt_args { fhandle_t *fh; int filemode; int *fd; }` |

### `hrtsys` (`109`)

Outer dispatch is in `uts/i386/io/hrtimers.c`.

Outer opcodes:

| Opcode | Operation |
|---:|---|
| 0 | `HRTCNTL` |
| 1 | `HRTALARM` |
| 2 | `HRTSLEEP` |
| 3 | `HRTCANCEL` |

Timer command values are declared in `uts/i386/sys/hrtcntl.h` and include:

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
- BSD-style timer variants `HRT_BSD`, `HRT_BSD_PEND`, `HRT_RBSD`, `HRT_BSD_REP`, `HRT_BSD_CANCEL`

### `priocntlsys` (`112`)

The raw argument block is explicitly documented in `uts/i386/disp/priocntl.c`:

- `int pc_version`
- `procset_t *psp`
- `int cmd`
- `caddr_t arg`

The handler validates `pc_version == PC_VERSION` and then branches on `cmd` to perform scheduling-class administration and per-process/class parameter operations.

### `memcntl` (`131`)

The syscall table exposes six raw arguments and dispatches to `uts/i386/os/lock.c`. The handler branches on `uap->cmd`, so this is also a command family even though it has its own top-level syscall number.

### `async` / `acancel` (`111`, `110`)

The user request wrapper for async I/O is documented in `uts/i386/sys/asyncsys.h` as:

- `struct asyncop { int a_syscall; int a_sysarg[MAXSYSARGS]; ushort a_flags; int a_error; off_t a_offset; pcparms_t a_pri; ecb_t a_ecb; }`

In this tree, the syscall entry points themselves are only present as stubs in `uts/i386/master.d/async/stubs.c`, so this document does not claim additional runtime behavior beyond the interface shape exposed in kernel headers.

## Conditional or Package-Stubbed Entries

- `56` (`uexch`) is only active under `#ifdef MEGA`; otherwise the syscall table points at `nosys`.
- `101` / `102` (`evsys`, `evtrapret`) are declared in the event headers, but this tree also contains `uts/i386/master.d/events/stubs.c` with stub entry points.
- `110` / `111` (`acancel`, `async`) are stubbed in `uts/i386/master.d/async/stubs.c` even though async-related kernel headers are present.
- `106` (`nfssys`) also has a stub in `uts/i386/master.d/nfs/stubs.c`; the full implementation is under `uts/i386/fs/nfs/`.
- `78` (`rfsys`) also has a stub entry in `uts/i386/master.d/RFS/stubs.c`; the full implementation is under `uts/i386/fs/rfs/`.

## Handler Groupings

These files own most of the ABI surface that userland sees first:

- `uts/i386/fs/vncalls.c`: pathname and descriptor I/O, `stat`, `fcntl`, tty, polling, vectored I/O, and several extended stat variants.
- `uts/i386/os/scalls.c`: credentials, process-group/session control, signal operations, system identity, resource limits, and several miscellaneous compatibility calls.
- `uts/i386/os/grow.c`: `brk`, `mmap`, `mprotect`, `munmap`, `mincore`.
- `uts/i386/os/exit.c`, `uts/i386/os/fork.c`, `uts/i386/os/exec.c`: lifecycle control.
- `uts/i386/os/msg.c`, `uts/i386/os/sem.c`, `uts/i386/os/shm.c`: System V IPC multiplexors.
- `uts/i386/fs/strcalls.c`: STREAMS message syscalls.

## Coverage Notes

This file is intended to be a practical porting reference, not a re-specification of every internal helper. Where a syscall fans out through a large internal command switch (`sysi86`, `rfsys`, `hrtsys`, `priocntlsys`, `memcntl`), the document records the command surface that is named directly in kernel headers or explicit dispatch tables, and points at the owning file for deeper implementation details.