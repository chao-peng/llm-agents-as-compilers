"""Fixed native reference compiler, shared assembler/linker, and independent evaluator."""

import math
import os
import platform
import random
import re
import shutil
import sys
import time
from pathlib import Path

from .data import cases, digest, encode_case, workload, write_json
from .process import ProcessError, run
from .stats import geomean, paired_summary


def validate_assembly(code):
    if not isinstance(code, str) or not code.strip() or len(code.encode()) > 1024 * 1024:
        raise ValueError("assembly must be nonempty and at most 1 MiB")
    # The assembler must not read evaluator files or produce additional files.
    if re.search(r"(?i)(?:\.(?:include|incbin)|#\s*include)\b", code):
        raise ValueError("assembly file inclusion is forbidden")


class Toolchain:
    def __init__(self, config, root):
        self.config = config
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cc = shutil.which(config.get("cc", "clang"))
        if not self.cc:
            raise ValueError("C compiler not found")
        self.flags = config.get("cflags", ["-O3"])
        if not isinstance(self.flags, list) or any(not isinstance(f, str) for f in self.flags):
            raise ValueError("cflags must be a list of strings")
        if any(f.startswith(("-flto", "-o", "@")) for f in self.flags):
            raise ValueError("pilot track uses separate objects; LTO and output overrides are not supported")
        self.execution = config.get("execution", "sandbox")
        self.timeout = config.get("timeout_seconds", 10)
        self.deadline = None
        if self.execution == "sandbox":
            # Fail before model spending if the OS cannot establish the requested sandbox.
            run(["/usr/bin/true"], self.root, self.timeout, execution="sandbox")
        self.driver = self.root / "driver.c"
        self.driver.write_text(Path(__file__).with_name("driver.c").read_text())
        self.driver_object = self.root / "driver.o"
        result = run([self.cc, "-std=c11", "-O2", "-c", str(self.driver), "-o", str(self.driver_object)], self.root, 60)
        write_json(self.root / "driver-build.json", result)

    def metadata(self):
        package = Path(__file__).parent
        implementation = b"".join(p.name.encode() + p.read_bytes() for p in sorted(package.iterdir()) if p.suffix in (".py", ".c"))
        cpu = platform.processor()
        if platform.system() == "Darwin":
            try:
                cpu = run(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], self.root)["stdout"].strip()
            except ProcessError:
                cpu = "unavailable (host denies CPU introspection)"
        elif Path("/proc/cpuinfo").exists():
            cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                        if line.startswith(("model name", "Hardware"))), cpu)
        return {"system": platform.system(), "machine": platform.machine(),
                "cpu": cpu, "logical_cpus": os.cpu_count(),
                "platform": platform.platform(), "python": sys.version,
                "compiler": run([self.cc, "--version"], self.root)["stdout"],
                "target": run([self.cc, "-dumpmachine"], self.root)["stdout"].strip(),
                "cc": self.cc, "cflags": self.flags, "driver_cflags": ["-std=c11", "-O2"],
                "driver_sha256": digest(self.driver.read_bytes()), "harness_sha256": digest(implementation),
                "execution": self.execution}

    def remaining_timeout(self, limit):
        if self.deadline is None:
            return limit
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProcessError("budget_exhausted", "wall-clock budget exhausted")
        return min(limit, remaining)

    def build(self, code, directory, assembly=False, reference=False):
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / ("candidate.s" if assembly else "source.c")
        source.write_text(code)
        obj, executable = directory / "kernel.o", directory / "program"
        if assembly:
            validate_assembly(code)
            command = [self.cc, "-x", "assembler", "-c", str(source), "-o", str(obj)]
        else:
            flags = ["-O0"] if reference else self.flags
            command = [self.cc, "-std=c11", *flags, "-c", str(source), "-o", str(obj)]
        build = run(command, directory, self.remaining_timeout(60))
        # No baseline IR or assembly ever enters model requests.
        link = run([self.cc, str(self.driver_object), str(obj), "-o", str(executable)], directory, self.remaining_timeout(60))
        write_json(directory / "build.json", {"compile": build, "link": link})
        return {"path": str(executable), "seconds": build["seconds"] + link["seconds"],
                "binary_bytes": executable.stat().st_size, "object_bytes": obj.stat().st_size}

    def invoke(self, executable, case, iterations=0):
        path = Path(executable)
        result = run([str(path), str(iterations)], path.parent, self.remaining_timeout(self.timeout),
                     encode_case(case), execution=self.execution)
        fields = result["stdout"].strip().split()
        if len(fields) != 3:
            raise ProcessError("invalid_output", "expected value, mutation flag, and elapsed nanoseconds")
        try:
            value, mutated, elapsed = (int(v) for v in fields)
        except ValueError as exc:
            raise ProcessError("invalid_output", "non-integer output") from exc
        if not 0 <= value < 2**64 or mutated not in (0, 1) or elapsed < 0:
            raise ProcessError("invalid_output", "output outside protocol range")
        if mutated:
            raise ProcessError("input_mutation", "candidate changed input or guard words")
        return value, elapsed, result["seconds"]


class Evaluator:
    def __init__(self, toolchain):
        self.tc = toolchain
        self.references = {}

    def references_for(self, task):
        key = task["source_sha256"]
        if key not in self.references:
            root = self.tc.root / "references" / task["id"]
            self.references[key] = (
                self.tc.build(task["code"], root / "O0", reference=True),
                self.tc.build(task["code"], root / "baseline"),
            )
        return self.references[key]

    def evaluate(self, task, assembly, directory, phase, seed, baseline_only=False):
        result = {"task": task["id"], "category": task["category"], "phase": phase, "status": "pending",
                  "compiled": False, "correctness_passed": False}
        try:
            oracle, baseline = self.references_for(task)
        except (ProcessError, ValueError) as exc:
            return dict(result, status="reference_build_error", detail=str(exc))
        try:
            candidate = baseline if baseline_only else self.tc.build(assembly, directory, assembly=True)
            result.update({"compiled": True, "build_seconds": candidate["seconds"], "binary_bytes": candidate["binary_bytes"],
                           "object_bytes": candidate["object_bytes"]})
        except (ProcessError, ValueError) as exc:
            return dict(result, status="build_error", detail=str(exc))
        try:
            inputs = cases(task["id"], phase, seed, self.tc.config.get("random_cases", 16))
            sizes = self.tc.config.get("sizes", [64, 1024])
            workloads = [workload(task["id"], phase, seed, n) for n in sizes]
            # Check timing inputs too, including varied x values used by the timed loop.
            iterations = self.tc.config.get("iterations", 2000)
            for w in workloads:
                for offset in (0, 1, 31, iterations - 1):
                    inputs.append({"a": w["a"], "x": (w["x"] + offset) % 2**64})
            for index, case in enumerate(inputs):
                expected = self.tc.invoke(oracle["path"], case)[0]
                if self.tc.invoke(baseline["path"], case)[0] != expected:
                    return dict(result, status="oracle_disagreement", case_index=index)
                actual = self.tc.invoke(candidate["path"], case)[0]
                if actual != expected:
                    failure = dict(result, status="wrong_answer", case_index=index, expected=expected, actual=actual)
                    if phase == "search":
                        failure["input"] = case
                    return failure
            result["checked_cases"] = len(inputs)
            result["correctness_passed"] = True
            timings = []
            rng = random.Random(int(digest(f"order:{phase}:{seed}:{task['id']}"), 16))
            for w in workloads:
                # Increase a shared batch length until BOTH programs clear timer resolution.
                # Calibration is not a scored sample and never changes the candidate.
                batch = iterations
                minimum = self.tc.config.get("min_batch_ns", 5000000)
                maximum = self.tc.config.get("max_iterations", 100000000)
                while True:
                    observed = [self.tc.invoke(p["path"], w, batch)[1] for p in (baseline, candidate)]
                    if min(observed) >= minimum:
                        break
                    if batch >= maximum:
                        raise ProcessError("unstable_timing", "could not reach minimum timing duration")
                    factor = min(10, max(2, math.ceil(minimum / max(1, min(observed)))))
                    batch = min(maximum, batch * factor)
                last_case = {"a": w["a"], "x": (w["x"] + batch - 1) % 2**64}
                expected = self.tc.invoke(oracle["path"], last_case)[0]
                if self.tc.invoke(baseline["path"], last_case)[0] != expected:
                    return dict(result, status="oracle_disagreement", correctness_passed=False)
                if self.tc.invoke(candidate["path"], last_case)[0] != expected:
                    return dict(result, status="wrong_answer", correctness_passed=False, detail="calibrated workload boundary failed")
                pairs = []
                for _ in range(self.tc.config.get("repeats", 7)):
                    order = ["baseline", "candidate"]
                    rng.shuffle(order)
                    sample = {"order": order}
                    for name in order:
                        executable = baseline["path"] if name == "baseline" else candidate["path"]
                        _, ns, wall = self.tc.invoke(executable, w, batch)
                        if ns <= 0:
                            raise ProcessError("invalid_timing", "nonpositive elapsed time")
                        sample[name + "_ns"] = ns / batch
                        sample[name + "_process_seconds"] = wall
                    pairs.append(sample)
                timings.append({"n": len(w["a"]), "iterations": batch, **paired_summary(pairs, seed=seed)})
            result.update(status="pass", speedup=geomean(t["speedup"] for t in timings),
                          faster=all(t["faster"] for t in timings), workloads=timings)
        except ProcessError as exc:
            result.update(status=exc.kind, detail=str(exc))
        return result
