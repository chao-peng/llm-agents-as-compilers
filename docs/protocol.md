# Evaluation protocol

## Semantics and programs

The current kernel contract is C11 with 64-bit `uint64_t`/`size_t`, unsigned wraparound, read-only runtime inputs, and a scalar output. `a` is valid and nonnull even for `n=0`. Functions must not perform I/O, access beyond `n`, modify inputs, depend on hidden state, or change the test process. There is no floating-point relaxation, source pre-optimization, baseline fallback, or reference assembly in model prompts.

The original sources deliberately avoid undefined arithmetic. No compiler-based test establishes that an arbitrary imported C program is defined: audit bounds, initialization, aliasing, shifts, and integer rules when importing. `-O0` versus the optimized reference is a differential check, not an independent formal oracle. Reference disagreements are errors and remain visible.

One program is one denominator entry. Inputs, lengths, random seeds, and timed repetitions are not additional programs. Family membership must be disjoint between `dev` and `test`; the manifest validator rejects leakage and modified source hashes. Changing a source requires explicitly updating and reviewing its manifest hash before any experiment.

## Lifecycle and data access

1. **Search:** B receives one program at a time; C receives only the development set. Source and last candidate/search feedback are the entire model context. The orchestrator controls compilation and execution. The agent cannot edit the wrapper or evaluator through the artifact protocol.
2. **Selection:** after all generation has ended, candidates with at least one search pass are evaluated on a separately derived selection stream. Selection results never enter model requests. Rank candidates first by number of passing programs, then by geometric-mean speedup on that passing subset. This allows a partially working C compiler to be selected while retaining its failures. Selection is adaptive over the fixed candidates; it is not final evidence.
3. **Freeze:** one B artifact per program, or exactly one C compiler. Save artifact, manifest, and source hashes. If no candidate passed selection, final reports include `no_candidate` for every affected program.
4. **Final:** a different command accepts the final seed after freezing and never constructs a provider. It verifies hashes and recorded platform/compiler/driver settings. Each frozen run can evaluate each allowed split once. A marker is written before execution; interrupted finals must be retained and documented rather than silently restarted or replaced.

Search/selection/final use domain-separated random streams. Public boundary cases intentionally overlap. Public examples and seeds are not secret holdouts. Keep final seeds and artifacts on the evaluator side; an agent given general filesystem access to this repository can read the public test sources. For a formal blind study, keep held-out suites in an evaluator-only deployment and audit what the external provider can access. The current local manifest contains test sources to facilitate development, while the HTTP prompt construction excludes them.

The unseen-program track compares deployment strategies: B searches each new program, C compiles it with a frozen compiler. Their online costs differ by design. This comparison alone cannot isolate the causal effect of optimizing code versus optimizing a compiler.

## Budgets and cost

Calls are reserved before transmission. Returned input/output tokens are charged before parsing the artifact, so malformed responses still cost tokens. A transport error can have unknown billing; it stops the run without retrying. Unknown usage and over-token-budget responses are excluded from selection. A token cap is a post-response stopping threshold, with possible one-call overshoot recorded in the ledger, not a guarantee about billed tokens. Set per-request completion limits and provider-side spend limits as appropriate.

Wall time includes setup, generation, compilation, checking, timing, and selection. Child processes are limited by the remaining run time. If time runs out before independent selection finishes, no unselected artifact is promoted. `rounds`/`max_calls` limit generation only; selection consumes time but no model calls. Artifacts from a candidate whose evaluation was interrupted can remain on disk without being selected. Final evaluation cost is separate.

Raw provider latency, token counts, translation time, native build time, executable/object bytes, and search wall time are recorded. Dollar costs are not guessed: provider pricing, caching, reasoning tokens, and billing rules require an explicitly versioned pricing policy. The `compare` command exports **linear projections** of B search cost and C up-front plus deployment cost as program count increases. These are not measured crossover findings, and successful-compilation estimates must be read alongside coverage.

## Measurement

The fixed C driver is compiled once at `-O2`; source kernels use the configured baseline flags, default `-O3`. Generated assembly is assembled without preprocessing and linked against the same driver. Separate objects prevent the C compiler from removing the kernel call across the driver boundary. Normal builtins remain enabled. The current pilot forbids LTO because it would change this measurement boundary; LTO/PGO belong in separately implemented application controls.

Check edge cases, random cases, timing inputs, and selected varying-`x` boundaries before scoring. Each timed batch includes function-call/volatile-sink overhead; report this limitation for tiny functions. Warmups occur outside the timed interval. A common batch size is increased until both reference and candidate meet the minimum batch duration (default 5 ms). Calibration timings are discarded. Every scored pair randomly orders reference/candidate. Save all raw samples and the parent-observed process duration.

Compute median paired speedups for each input size and the geometric mean across sizes. A program is “correct and faster” only if all tested sizes have a bootstrap 95% speedup interval above 1 and at least five pairs. These intervals describe within-run noise, assume exchangeable pairs, and are not corrected for multiple comparisons. They do not cover agent variation, thermal drift, scheduler effects, or benchmark selection. Record/pin hardware, CPU affinity where supported, frequency/power policy, and competing workloads for research runs. Never run benchmark experiments concurrently on the same host.

Report the entire program denominator, correctness and failure categories, correctness-qualified faster fraction, and speedups on the passing subset. Keep failures visible and never substitute the baseline. A self-comparison in arm A only audits measurement stability.

## Execution boundaries

Generated native binaries and generated Python compilers are executable code. The default OS sandbox blocks network and access to project/home files outside the isolated job while allowing system runtime reads. Linux uses bubblewrap with isolated namespaces; macOS uses the system sandbox. Support depends on the host; nested sandboxes may be unavailable. The driver/assembler are trusted host tools, and assembler file-inclusion directives are rejected. Build invocations and child output have time/output/resource bounds; secrets are removed from child environments.

The generated compiler executes under a Python audit hook that rejects subprocesses, networking, `ctypes`, and file writes, and limits reads to the current job and Python standard library. Its protocol is `compiler.py input.c target-triple` with assembly on stdout. This is a deliberately constrained first compiler-synthesis backend. It supports neither arbitrary package dependencies nor compiled compiler implementations yet. Compiler architecture is otherwise unrestricted.

These layers are useful containment and protocol enforcement, **not a security proof** or a substitute for a dedicated disposable evaluator. Malicious Python may bypass language-level restrictions; malicious native code could tamper with its in-process timer or fabricate outputs. Review artifacts, audit no-delegation/no-benchmark-lookup behavior, and use a hardened independent runner before adversarial or publication-scale experiments. `execution=local` explicitly opts out of OS containment and is intended for trusted fixtures. It still applies timeouts, clean environments, and the Python audit policy.

## Artifact layout

```text
run/
  run.json                   # config, target, source hashes, budget, frozen selection
  freeze.json                # run manifest digest + selected artifact digests
  trace.jsonl                # every attempted call, failures included
  curve.csv                  # cost/performance progression and correctness regressions
  toolchain/                 # fixed wrapper + reference executables, never sent to model
  candidates/0001/
    request.json, response.json
    candidate.s | compiler.py
    search.json, selection.json
    search/, selection/      # assembly, commands, outcomes, timings
  frozen/                    # one assembly per B program or one shared C compiler
  final-dev/ | final-test/
    started.json             # one-shot evaluation marker
    results.json, report.md
    programs/, toolchain/
```

Source artifacts, inputs, and commands allow inspection and rerunning in a separately labeled reproduction. Run directories are gitignored because prompts, proprietary inputs, and provider metadata may be sensitive. Publish curated evidence with an explicit provenance record rather than committing a workspace wholesale.
