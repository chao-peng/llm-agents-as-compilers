# Validation record

Local validation on 2026-10-24 used native ARM64 macOS and Apple Clang 21.0.0. Python was 3.9.6. No paid model was called.

| Check | Observed result |
|---|---|
| `LAC_TEST_SANDBOX=1 python3 -m unittest discover -s tests -v` | 15 tests passed; no skips |
| Offline A/B/C `demo` | A, B, C: 2/2 development programs passed each |
| Frozen C compiler on unseen source families | 2/2 test programs passed; no model invoked during deployment |
| Native pilot baseline | 6/6 development and 6/6 test programs passed |
| Cost comparison export | JSON summary and CSV projection generated |
| Prompt inspection | No test program sources or final seeds in development model requests |
| macOS sandbox | Native execution and compiler translation passed; outside sentinel reads and connection to a live local listener were blocked |
| Repository checks | Python syntax and Git whitespace checks passed; run logs and credential files ignored |

The test suite exercises source-hash and family-split validation, domain-separated input streams, malformed responses, token/time/call budget stopping, unknown usage, invalid assembly, wrong answers, process timeouts, compiler-delegation rejection, credential isolation, frozen-manifest tampering, paired statistics, independent correctness/timing accounting, and a local HTTP model-protocol mock.

The offline B/C artifacts come from a **handwritten expression compiler**. These runs establish infrastructure behavior only. The native pilot is also a functionality audit: baseline self-comparison can produce occasional nominally faster results because of noise. No speedup in these checks is an LLM research finding. Linux CI is configured separately; the local validation above does not establish Linux behavior.

The full `runs/` directories remain local and gitignored. Reproduce with a fresh output directory using the README commands. For publication, record multiple complete model runs, independent final inputs, hardware/power controls, audited upstream program versions, and the required stronger correctness checks.
