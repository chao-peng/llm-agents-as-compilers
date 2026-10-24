"""Budget curves, regressions, and explicitly extrapolated deployment costs."""

import csv
import json
from pathlib import Path
import statistics

from .data import write_json
from .stats import geomean


def export_search_curve(root):
    root = Path(root)
    if not (root / "trace.jsonl").exists():
        return
    previous = {}
    with (root / "curve.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["candidate", "calls", "tokens", "elapsed_seconds", "passed",
                                                   "evaluated", "geomean_speedup_correct_subset", "regressions"])
        writer.writeheader()
        for line in (root / "trace.jsonl").read_text().splitlines():
            event = json.loads(line)
            rows = event.get("results", [])
            passed = [r for r in rows if r["status"] == "pass"]
            regressions = [r["task"] for r in rows if previous.get(r["task"]) == "pass" and r["status"] != "pass"]
            previous.update({r["task"]: r["status"] for r in rows})
            budget = event["budget"]
            writer.writerow({"candidate": event["candidate"], "calls": budget["calls"],
                             "tokens": budget["input_tokens"] + budget["output_tokens"], "elapsed_seconds": budget["elapsed_seconds"],
                             "passed": len(passed), "evaluated": len(rows),
                             "geomean_speedup_correct_subset": geomean(r["speedup"] for r in passed),
                             "regressions": ";".join(regressions)})


def deployment_curve(direct, compiler, counts=(1, 2, 4, 8, 16, 32, 64, 128)):
    if direct["group"] != "direct" or compiler["group"] != "compiler":
        raise ValueError("cost comparison requires direct and compiler reports")
    if direct["suite_sha256"] != compiler["suite_sha256"] or direct["split"] != compiler["split"]:
        raise ValueError("compare the same suite and program split")
    if direct["environment"] != compiler["environment"]:
        raise ValueError("cost comparison requires the same recorded environment")
    b_budget, c_budget = direct["search_budget"], compiler["search_budget"]
    if b_budget["usage_unknown"] or c_budget["usage_unknown"]:
        raise ValueError("cost is unknown for at least one provider call")
    b_per_program = b_budget["elapsed_seconds"] / len(direct["results"])
    c_upfront = c_budget["elapsed_seconds"]
    compiles = [r["translation_seconds"] + r["build_seconds"] for r in compiler["results"] if r["status"] == "pass"]
    if not compiles:
        raise ValueError("no successful compiler deployments to estimate compilation time")
    c_compile = statistics.mean(compiles)
    # These projections assume the observed program mix; they are not measured crossover claims.
    return {"assumption": "Linear extrapolation from observed search wall time and successful compile times; compare coverage and performance separately.",
            "synthetic": direct.get("synthetic") or compiler.get("synthetic"),
            "rows": [{"programs": n, "direct_search_seconds": n * b_per_program,
                      "compiler_build_and_deploy_seconds": c_upfront + n * c_compile,
                      "direct_tokens": n * (b_budget["input_tokens"] + b_budget["output_tokens"]) / len(direct["results"]),
                      "compiler_tokens": c_budget["input_tokens"] + c_budget["output_tokens"]} for n in counts]}


def save_comparison(direct, compiler, output):
    from .study import summarize
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    curve = deployment_curve(direct, compiler)
    write_json(root / "comparison.json", {"direct": summarize(direct), "compiler": summarize(compiler), "cost_projection": curve})
    with (root / "cost_projection.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(curve["rows"][0]))
        writer.writeheader()
        writer.writerows(curve["rows"])
