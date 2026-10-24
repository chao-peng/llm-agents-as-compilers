# LLM Agents as Compilers

**An Empirical Study of LLM Agents as Compilers for High-Performance Code Generation**

A runnable experiment harness for three compilation strategies:

| Arm | Optimized artifact | Deployment |
|---|---|---|
| A — conventional compiler | Fixed C compiler configuration, default `clang -O3` | Compile each program |
| B — direct translation | Assembly generated and revised from C source | Search separately for each program |
| C — compiler synthesis | One reusable Python compiler generated and revised against development programs | Freeze it, then compile new programs without an LLM |

The main experiment gives B/C source code and the target ABI, **never baseline IR or assembly**. All arms share a fixed native harness, assembler, and linker. No IR architecture is prescribed for C.

**Status:** functional first implementation for a native, integer, function-level pilot. Includes 12 original kernels, a four-program offline smoke suite, A/B/C orchestration, isolated subprocess support, budget records, independent selection, frozen evaluation, and JSON/Markdown/CSV reporting. The smoke provider is a handwritten fixture, not an LLM. This repository contains no evidence that LLMs outperform conventional compilers. Embench/LLVM/TSVC integration and full application experiments are tracked in [the benchmark plan](docs/benchmarks.md).

中文实验说明：[研究方案与实现范围](docs/design.zh-CN.md)。

## Quick start

Requirements: Python 3.9+, Clang with a working system SDK/linker, and a native 64-bit macOS or Linux host. Runtime Python dependencies: **none**. The bundled smoke translator supports ARM64 (macOS/Linux) and x86-64 (Linux). Run from the repository root:

```sh
python3 -m lac doctor
python3 -m lac validate --suite benchmarks/pilot/suite.json
python3 -m unittest discover -s tests -v
python3 -m lac demo --output runs/demo-01
```

`demo` makes no network/model calls and explicitly uses local execution for the trusted fixture. It runs A, searches B and C, freezes selected artifacts, evaluates both on new inputs, and evaluates the frozen C compiler on held-out program families. Results go into `runs/demo-01/summary.json` and individual Markdown reports. All output paths must be new; runs are never silently overwritten.

Optional installation: `python3 -m pip install -e .` exposes the `lac` command. Suite/config paths are explicit; the repository fixtures are not installed as global package data.

## Run an experiment

Copy `configs/study.json` to a local config. Set `provider.model` to an explicitly chosen model ID; configure the endpoint, completion cap, and budget. Set the named API key environment variable through your normal secret manager. Do not put credentials into JSON files.

The default execution policy is `sandbox`: macOS uses `sandbox-exec`, Linux requires `bubblewrap`. Startup fails before model spending if isolation cannot be established. `--execution local` is for reviewed, trusted artifacts or an already isolated disposable machine. See [execution boundaries](docs/protocol.md#execution-boundaries).

```sh
# A: audit the pilot with a fixed native compiler configuration.
python3 -m lac baseline --suite benchmarks/pilot/suite.json \
  --config configs/study.json --output runs/A-dev --split dev --seed 928347

# B: a shared run budget is distributed round-robin across development programs.
python3 -m lac search --group direct --suite benchmarks/pilot/suite.json \
  --config configs/study.json --output runs/B-dev --seed 17

# C: one shared compiler; only development source programs are exposed.
python3 -m lac search --group compiler --suite benchmarks/pilot/suite.json \
  --config configs/study.json --output runs/C-dev --seed 17

# Supply an independent final seed only AFTER search/selection have finished.
# These example seeds are public: use new private seeds for a real study.
python3 -m lac evaluate --suite benchmarks/pilot/suite.json \
  --run runs/B-dev --split dev --seed 928347
python3 -m lac evaluate --suite benchmarks/pilot/suite.json \
  --run runs/C-dev --split dev --seed 928347
python3 -m lac evaluate --suite benchmarks/pilot/suite.json \
  --run runs/C-dev --split test --seed 928347

python3 -m lac report runs/C-dev/final-test/results.json
python3 -m lac compare --direct runs/B-dev/final-dev/results.json \
  --compiler runs/C-dev/final-dev/results.json --output runs/comparison
```

For B on unseen programs, start a **new** direct search with `--split test`, then evaluate its frozen artifacts on final inputs. Its per-program search cost remains part of the comparison. C cannot run synthesis on the test split. Repeat complete searches with separate directories/seeds; repeating binary timing alone does not estimate agent-run variation.

`rounds` limits proposals per B program or per shared C compiler; `budget.max_calls` is a **total run cap**, not a per-program cap. Equal rounds therefore do not imply equal costs. Fix matched total budgets before experiments. The current token cap is an observed-usage stopping threshold: one request can cross it, and an over-budget artifact is excluded. The per-request completion limit bounds output. Unknown usage stops the run and excludes that response. See [the full protocol](docs/protocol.md).

## Providers and artifacts

`chat` uses a configurable Chat Completions HTTP endpoint, with `max_completion_tokens` and returned prompt/completion usage. No model or temperature is silently chosen, no paid retries occur, and API keys are not passed into generated-code processes. Schema reference: [official Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

`command` accepts an operator-controlled argv list. It receives a JSON object containing `messages` and public `context` on stdin, and returns:

```json
{
  "content": "{\"artifact\":\"complete assembly or Python compiler source\",\"rationale\":\"brief explanation\"}",
  "usage": {"input_tokens": 100, "output_tokens": 200}
}
```

Use absolute paths; `pass_env` explicitly names credentials the provider needs. Provider commands are trusted model clients, not generated programs. They must enforce the same no-test-access policy as the built-in HTTP provider.

`replay` reads an ordered JSON array in that format for deterministic debugging. `demo` uses the small handwritten expression compiler in `lac/demo_compiler.py`. Both are marked synthetic in reports.

Each search saves requests, responses, candidate sources, compilation commands, per-input outcomes, raw paired timings, `trace.jsonl`, a budget/regression `curve.csv`, and a hash-checked `freeze.json`. Final evaluation has a separate directory and a one-shot start marker. See [artifact layout](docs/protocol.md#artifact-layout).

## Scope and evidence

The pilot ABI is `uint64_t kernel(const uint64_t *a, size_t n, uint64_t x)`. It supports original C translation units with internal helpers and standard-library calls. It does not yet evaluate arbitrary command-line applications, mutable array outputs, floating point, multiple translation units, or a complete libc. The scalar/array/branch/hash/sorting/library-application fixtures are infrastructure and pilot inputs, not substitutes for the planned upstream benchmark suite.

The evaluator checks exact uint64 outputs against `-O0`, cross-checks `-O3`, detects input mutation, and tests boundary/random/timing inputs. These finite checks do not establish semantic equivalence or absence of undefined behavior. Timing separates the repeated kernel interval from a parent-observed whole-process duration; whole-process duration also includes input parsing and sandbox launch. Both reference and candidate use the same fixed wrapper. See [limitations and controls](docs/protocol.md).
