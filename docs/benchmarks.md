# Benchmark selection and adaptation

The checked-in `pilot` suite contains **12 original kernels** in six development and six held-out programs. It covers reductions, pairwise arithmetic, hashing, bit counting, predicates, extrema, GCD, bounded sorting, and small applications using `memcpy`, `memset`, and `memcmp`. The four scalar expressions in `smoke` exist only to exercise offline A/B/C pipelines. Neither suite is an upstream benchmark release or sufficient evidence about general C compilation.

The study's intended expansion is approximately 19 Embench programs, 10 LLVM C applications, 20 TSVC loops, and three memory implementations. These counts remain **selection candidates**, not implemented or audited coverage. Select programs before observing model success.

| Source | Planned role | Required work before inclusion |
|---|---|---|
| [Embench-IoT](https://github.com/embench/embench-iot/tree/embench-1.0) | Embedded/application core | Pin commit; inspect each license/dependency; replace fixed inputs with explicit runtime inputs; preserve original and adapted variants |
| [LLVM test-suite](https://llvm.org/docs/TestSuiteGuide.html) | C applications (MiBench/Olden/Ptrdist/FreeBench candidates) | Audit language, dependencies, source families, and expected outputs; add a multi-file/application runner |
| [TSVC-2](https://github.com/UoB-HPC/TSVC_2) | Dependence/vectorization mechanisms | Stratify by loop features; fix initialization/checking/timing boundary; define floating-point policy before using float loops |
| [PolyBench/C](https://www.cs.colostate.edu/~pouchet/software/polybench/polybench.html) | Optional numerical extension | Pin version; add shaped/mutable array outputs and declared floating-point semantics |
| [LLVM libc benchmarks](https://github.com/llvm/llvm-project/tree/main/libc/benchmarks) | Memory-function diagnostics | Provide identical implementation source to all arms; vary length, alignment, overlap where legal; label system libc as an extra reference |
| [ExeBench](https://github.com/jordiae/exebench) | Correctness/translation coverage | Resolve dependencies and executable inputs; exclude serialization from compute timing |
| [Csmith](https://github.com/csmith-project/csmith) | Correctness stress tests | Restrict to declared supported C features; keep generated tests separate from performance denominators |

This list preserves the research plan; no upstream code is silently downloaded, relicensed, or counted as a completed experiment. Cross-repository copies of MiBench/TSVC must be deduplicated by family.

## Adding a kernel

1. Pin an upstream commit/release and retain the original source, its hash, and applicable license notices outside the benchmark candidate artifact. Record provenance and adaptation in the manifest.
2. Create one self-contained C translation unit exporting the pilot `kernel` ABI. All source relevant to semantic translation, including internal helpers, belongs in this file; B and C receive it in full. Do not hide computation in a conventionally compiled support object.
3. Define runtime inputs and observable outputs, audit undefined behavior, and create a source-specific oracle where generic scalar differential checks are insufficient. Do not discard mutable outputs into a single unchecked checksum.
4. Add a manifest entry with unique `id`, `source`, SHA-256, `family`, `split`, `category`, and `provenance`. Use a new source hash whenever adapting source. Family-disjoint split validation is automatic.
5. Run `validate`, native baseline audit, and timing-stability checks **before** any LLM run. Record excluded objects and reasons. Freeze the manifest and evaluator settings.

Example manifest entry:

```json
{
  "id": "audited_kernel",
  "source": "audited_kernel.c",
  "sha256": "SHA256_OF_ADAPTED_SOURCE",
  "family": "upstream_program_family",
  "split": "dev",
  "category": "application",
  "provenance": {
    "origin": "https://github.com/OWNER/REPOSITORY",
    "commit": "FULL_UPSTREAM_COMMIT_SHA",
    "original_path": "path/to/original.c",
    "original_sha256": "SHA256_OF_ORIGINAL_SOURCE",
    "license": "audited upstream license identifier and notice path",
    "adaptation": "Describe the ABI/input/output changes precisely"
  }
}
```

A kernel adaptation's result must be labeled as such; it is not the original suite's standard score. Entire applications, self-contained executables, library-boundary ablations, strict/relaxed floating point, and LTO/PGO controls require additional runners and validation. They are not represented by the existing smoke results.
