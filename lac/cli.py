"""Command-line entry point; every run writes inspectable artifacts."""

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

from .data import Suite, read_json, write_json
from .study import baseline, config_from, final_evaluate, report_markdown, search, summarize
from .toolchain import Toolchain


def parser():
    cli = argparse.ArgumentParser(prog="lac", description="Compare native compilation, direct LLM translation, and compiler synthesis")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="show native tools and platform")
    validate = commands.add_parser("validate", help="validate hashes and family-disjoint program splits")
    validate.add_argument("--suite", required=True)
    for name in ("baseline", "search"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--suite", required=True)
        cmd.add_argument("--config", required=True)
        cmd.add_argument("--output", required=True)
        cmd.add_argument("--split", choices=("dev", "test"), default="dev")
        cmd.add_argument("--seed", type=int, default=0, help="public search seed (baseline: evaluation seed)")
        cmd.add_argument("--execution", choices=("sandbox", "local"))
        if name == "search":
            cmd.add_argument("--group", choices=("direct", "compiler"), required=True)
    final = commands.add_parser("evaluate", help="one-shot evaluation of frozen artifacts; never calls a model")
    final.add_argument("--suite", required=True)
    final.add_argument("--run", required=True)
    final.add_argument("--split", choices=("dev", "test"), required=True)
    final.add_argument("--seed", type=int, required=True, help="private final seed; supply only after freezing")
    report = commands.add_parser("report")
    report.add_argument("results")
    report.add_argument("--output", help="optional Markdown output")
    demo = commands.add_parser("demo", help="exercise A/B/C offline with an explicitly handwritten fixture")
    demo.add_argument("--output", required=True)
    demo.add_argument("--suite", default="benchmarks/smoke/suite.json")
    demo.add_argument("--config", default="configs/smoke.json")
    compare = commands.add_parser("compare", help="compare B/C coverage and export a labeled linear cost projection")
    compare.add_argument("--direct", required=True)
    compare.add_argument("--compiler", required=True)
    compare.add_argument("--output", required=True)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            with tempfile.TemporaryDirectory(prefix="lac-doctor-") as directory:
                tc = Toolchain({"execution": "local"}, directory)
                info = tc.metadata()
                info["sandbox_tool"] = shutil.which("sandbox-exec") or shutil.which("bwrap")
                print(json.dumps(info, indent=2))
        elif args.command == "validate":
            suite = Suite(args.suite)
            print(json.dumps({"suite_sha256": suite.sha256, "programs": len(suite.tasks),
                              "dev": len(suite.select("dev")), "test": len(suite.select("test"))}, indent=2))
        elif args.command in ("search", "baseline"):
            suite, config = Suite(args.suite), config_from(args.config, args.execution)
            if args.command == "search":
                result = search(suite, config, args.output, args.group, args.split, args.seed)
                print(json.dumps({"state": result["state"], "selected": result["selected"], "budget": result["budget"]}, indent=2))
            else:
                result = baseline(suite, config, args.output, args.split, args.seed)
                Path(args.output, "report.md").write_text(report_markdown(result))
                print(json.dumps(summarize(result), indent=2))
        elif args.command == "evaluate":
            result = final_evaluate(Suite(args.suite), args.run, args.split, args.seed)
            Path(args.run, "final-" + args.split, "report.md").write_text(report_markdown(result))
            print(json.dumps(summarize(result), indent=2))
        elif args.command == "report":
            result = report_markdown(read_json(args.results))
            if args.output:
                Path(args.output).write_text(result)
            else:
                print(result, end="")
        elif args.command == "compare":
            from .analysis import save_comparison
            save_comparison(read_json(args.direct), read_json(args.compiler), args.output)
            print(str(Path(args.output).resolve()))
        elif args.command == "demo":
            root = Path(args.output).resolve()
            root.mkdir(parents=True, exist_ok=False)
            suite, config = Suite(args.suite), config_from(args.config)
            if config["provider"]["kind"] != "demo":
                raise ValueError("demo requires provider.kind=demo and never calls a paid model")
            reports = {"A": baseline(suite, config, root / "A", "dev", 9173)}
            for group, arm in (("direct", "B"), ("compiler", "C")):
                print(f"Running offline {arm}: {group}", flush=True)
                search(suite, config, root / arm, group)
                reports[arm] = final_evaluate(suite, root / arm, "dev", 9173)
                if group == "compiler":
                    reports["C-transfer"] = final_evaluate(suite, root / arm, "test", 9173)
            for name, result in reports.items():
                (root / (name + ".md")).write_text(report_markdown(result))
            summaries = {name: summarize(result) for name, result in reports.items()}
            write_json(root / "summary.json", summaries)
            print(json.dumps(summaries, indent=2))
            if any(value["passed"] != value["total"] for value in summaries.values()):
                return 1
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f"lac: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0
