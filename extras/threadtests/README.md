# SVR4 Thread Tests

`svr4_threadtests` installs `/usr/bin/svr4-thread-tests` and the convenience
wrapper `/usr/bin/run-svr4-thread-tests` into the guest image.

The suite runs each test in a separate child process with an alarm timeout, so
hangs, aborts, and process-exit bugs are reported without wedging the rest of
the run.

Normal mode accepts known gaps as XFAILs:

```sh
run-svr4-thread-tests
```

Strict mode treats every selected failure as a hard failure:

```sh
run-svr4-thread-tests --strict
```

Useful filters:

```sh
run-svr4-thread-tests --list
run-svr4-thread-tests --only futex
run-svr4-thread-tests --strict --only timed_mutex_timeout
```

Coverage includes raw thread/futex syscall validation, futex wait/wake behavior,
pthread create/join, unique thread IDs, TLS isolation, mutexes, condition
variables, rwlocks, barriers, detached threads, process exit with live threads,
and worker-thread `exit()` behavior.