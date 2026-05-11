# MAP_NORESERVE Signal Follow-Up

This note captures the deferred signal-side work after the kernel gains
basic `MAP_NORESERVE` support.

## Current Behavior

- Late anonymous backing failure currently comes from `anon_alloc()` failing
  during `anon_zero()` or `anon_private()`.
- Those paths call `rm_outofanon()`, which posts `SIGKILL`.
- The VM fault path also returns `FC_OBJERR(ENOMEM)`, which the trap layer
  currently translates to `SIGBUS` with `BUS_OBJERR`.

## Desired Long-Term Behavior

- `MAP_NORESERVE` mappings should fail as a recoverable user fault when the
  kernel cannot obtain anonymous backing at first touch or copy-on-write.
- The process should not be killed outright by `rm_outofanon()`.
- If we decide to match the intended userspace contract more closely, the
  trap layer should deliver `SIGSEGV` rather than `SIGBUS` for this specific
  backing-allocation failure class.

## Planned Follow-Up

1. Remove the forced `SIGKILL` path from `rm_outofanon()` so late anon
   allocation failure stays in the normal VM fault path.
2. Decide whether to keep `FC_OBJERR(ENOMEM)` as `SIGBUS`, or introduce a
   more specific fault classification for anon-backing exhaustion.
3. If `SIGSEGV` is preferred, update fault translation so only the intended
   late-backing failures map to `SIGSEGV`, without collapsing unrelated
   object errors into the same signal.
4. Re-test allocator bringup under forced backing exhaustion and confirm the
   resulting signal and `siginfo` are stable and debuggable.