# Kernel Modernization Plan

This document lays out a staged path for modernizing the kernel sources under `uts/` without depending on `compile_commands.json` or the Jinx container's compiler path resolution.

## Constraints

- The current Jinx-driven build can describe compiler invocations that only exist inside the container, so the modernization workflow should not require a live compile database.
- `clang-format` is not enough on its own because the tree still contains old K&R function definitions, implicit `int`, and many non-prototype declarations.
- Header declarations and callback tables must be handled separately from `.c` function definitions. A blanket `foo()` to `foo(void)` rewrite would be wrong in many places.

## Baseline

- Likely old-style definition heads in `uts/**/*.c`: about `4845` across `388` files.
- Core kernel slices `uts/i386/{fs,io,os,vm}`: about `2896` definition heads across `207` files.
- Simple non-prototype header declarations: about `1105` across `134` headers.
- Header function-pointer declarations using empty parameter lists: about `295` across `57` headers.

Representative examples:

- K&R definition plus implicit local types: `uts/i386/os/scalls.c`
- Old-style architecture driver entry points: `uts/arch/at/i386/io/rtc.c`
- Header callback tables with empty parameter lists: `uts/i386/sys/conf.h`

## Target End State

The intended end state is:

- ANSI-style function definitions in `.c` files.
- Explicit return types and explicit local variable types.
- Prototype-bearing declarations in headers, with callback signatures fixed deliberately rather than guessed.
- A formatter pass driven by a repo-local `.clang-format`, applied only after the syntax migration is largely complete.

## Phase Order

### Phase 1: ANSI-fy `.c` definitions

Scope:

- Convert K&R function definitions to ANSI definitions.
- Add explicit `int` where old code relied on implicit `int` in local declarations.
- Leave header declarations and callback tables alone for now.

Tooling:

- Use the pilot rewriter at `uts/tools/ansi_c_rewrite.py`.
- Run it slice-by-slice, writing to a temporary file first.

Gate for each touched file:

- `clang -fsyntax-only` succeeds with the slice's legacy flags.
- `-Wimplicit-int` does not increase.
- `-Wdeprecated-non-prototype` drops for the touched translation unit.
- Any new parse failure blocks the batch.

Recommended pilot command for the `uts/i386/os` slice:

```bash
python uts/tools/ansi_c_rewrite.py uts/i386/os/scalls.c --output /tmp/scalls.ansi.c
cd uts/i386/os
clang -std=gnu89 -fcommon -fno-builtin -O2 -m32 -I.. -D_KERNEL -DAT386 -DWEITEK \
  -Wold-style-definition -Wstrict-prototypes -Wimplicit-int -fsyntax-only /tmp/scalls.ansi.c
```

Pilot result on `scalls.c`:

- `-Wdeprecated-non-prototype`: `61` down to `23`
- `-Wimplicit-int`: `6` down to `1`
- Remaining warnings are mostly header non-prototype declarations plus pre-existing semantic issues.

### Phase 2: Header prototype pass

Scope:

- Convert plain declarations such as `extern int foo();` once the actual signature is known.
- Fix function-pointer tables and ops vectors after the owning implementation signatures are explicit.

Rules:

- Do not rewrite header declarations mechanically from `()` to `(void)` unless the signature is proven to be zero-argument.
- Prefer working from the owning implementation and exported ops tables.
- Expect this phase to be partly semantic rather than purely textual.

Gate:

- No increase in `-Wstrict-prototypes` for the headers and translation units touched in the batch.
- No callback signature drift in ops tables.

### Phase 3: Semantic cleanup

Scope:

- Fix real warnings that become visible after the syntax cleanup, such as return-path mismatches and suspicious conditionals.
- Keep this separate from bulk syntax conversion so the review surface stays readable.

Representative cases already visible in `scalls.c`:

- `return;` in a non-void function.
- Non-void control paths with no return.
- Assignment-in-condition warnings.

### Phase 4: Formatting

Scope:

- Apply `clang-format` after the previous phases have removed most of the old syntax.
- Start with touched files only, not the whole tree.

Rules:

- Preserve include ordering initially.
- Avoid tree-wide formatting until the header and syntax migration is stable.
- Treat formatting as the last step in each slice, not the first.

## Slice Order

Recommended rollout order:

1. `uts/i386/os`
2. `uts/i386/io`
3. `uts/i386/vm`
4. `uts/i386/fs`
5. `uts/arch/at`
6. `uts/add-ons/*`

Reasoning:

- The core slices cover most of the old syntax and expose the hard cases early.
- The add-on drivers are numerous and should come after the main kernel style is settled.

## Validation Without `compile_commands.json`

The modernization loop should use hand-written per-slice syntax-check commands that mirror the old build profiles rather than relying on a live compile database.

For the core `os` slice, the validation command above is enough to prove that the rewriter output still parses in `gnu89` mode.

If this grows into a larger workflow, the next incremental step should be a small checked-in table of slice validation commands derived from the build spec profiles, not a dependency on container-only compiler paths.

## Formatter Profile

The initial formatter profile lives at the repo root in `.clang-format`.

Its intent is conservative:

- LLVM-like brace and wrapping behavior.
- No include sorting.
- Right-aligned pointer declarators for C code such as `char *ptr`.
- No requirement to run it on the raw tree before the ANSI pass.

## Near-Term Follow-Up

- Extend `uts/tools/ansi_c_rewrite.py` only for clearly mechanical cases.
- Add slice-specific validation command helpers if repeated manual invocation becomes noisy.
- Keep semantic fixes and formatting in separate commits from large K&R conversion batches.