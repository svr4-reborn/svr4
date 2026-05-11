# MAP_NORESERVE Plan

This note scopes a bringup-grade implementation of `MAP_NORESERVE` for the
SVR4 VM and the mlibc changes needed to exercise it.

## Goal

Allow private anonymous mappings to reserve virtual address space without
requiring full swap reservation at `mmap()` time, while preserving late
`ENOMEM` failure if the kernel cannot allocate backing pages on first write or
 copy-on-write.

## Expected Benefit

- Unblock modern userspace bringup that relies on large sparse mappings.
- Reduce pressure from allocator guard pages and arena reservations.
- Preserve the current strict reservation model for mappings that do not opt in.

## Constraints

- This is not a full VM overcommit redesign.
- Late allocation failure is acceptable for `MAP_NORESERVE` mappings.
- Existing reservation behavior for non-`MAP_NORESERVE` mappings should remain unchanged.

## Kernel Work

1. Add a per-segment `MAP_NORESERVE` state to `seg_vn`.
2. Teach `segvn_create()` to skip `anon_resv(seg->s_size)` for private mappings created with `MAP_NORESERVE`.
3. Preserve `swresv == 0` for no-reserve segments instead of treating it as an implicit "reserve later" case.
4. Teach `segvn_setprot()` not to reserve the full segment when write access is enabled on an explicit no-reserve mapping.
5. Audit `segvn_dup()`, `segvn_unmap()`, segment splitting, and segment free paths so zero reservation is treated as a first-class case.
6. Keep fault-time allocation behavior unchanged: `anon_zero()` and `anon_private()` remain the late failure points.

## Validation

1. Build the kernel and verify no new compile or link failures.
2. Reproduce the current allocator workload and confirm that initial anonymous `mmap()` calls no longer fail in `anon_resv()`.
3. Confirm that first-touch or copy-on-write can still fail with `ENOMEM` under real backing-store exhaustion.
4. Exercise `fork()` on a process with `MAP_NORESERVE` private anonymous mappings.
5. Exercise `mprotect(PROT_WRITE)` on a `MAP_NORESERVE` mapping.

## mlibc Work

1. Ensure `Sysdeps<AnonAllocate>` on SVR4 passes `MAP_NORESERVE`.
2. Ensure the debug allocator's direct anonymous `VmMap` calls on SVR4 also pass `MAP_NORESERVE`.
3. Keep the userland side opt-in local to the SVR4 sysdeps and allocator call sites.

## Deferred Work

- Real commit accounting distinct from address-space accounting.
- A stronger policy for `fork()` under no-reserve mappings.
- A full overcommit strategy for anonymous memory.