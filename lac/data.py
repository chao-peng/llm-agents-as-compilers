"""Validated manifests, independent input streams, and immutable run records."""

import hashlib
import json
import random
import re
from pathlib import Path

MASK = (1 << 64) - 1
CONTRACT = (
    "C11; uint64_t kernel(const uint64_t *a, size_t n, uint64_t x). "
    "a points to n readable uint64_t elements (nonnull even for n=0). "
    "Do not modify inputs, access out of bounds, perform I/O, or use global state. "
    "All unsigned arithmetic is modulo 2^64. Preserve the native C ABI. "
    "No reference compiler output is available."
)


def digest(data):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def append_json(path, value):
    with Path(path).open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")


def positive_int(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


class Suite:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.data = read_json(self.path)
        if self.data.get("schema_version") != 1:
            raise ValueError("suite schema_version must be 1")
        self.tasks = self.data.get("tasks", [])
        if not self.tasks:
            raise ValueError("suite needs at least one task")
        ids, families = set(), {}
        for task in self.tasks:
            name = task["id"]
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in ids:
                raise ValueError(f"invalid or duplicate task id: {name}")
            ids.add(name)
            if task["split"] not in ("dev", "test"):
                raise ValueError("program split must be dev or test")
            family = task["family"]
            if families.setdefault(family, task["split"]) != task["split"]:
                raise ValueError(f"program family leaks across splits: {family}")
            source = (self.path.parent / task["source"]).resolve()
            if self.path.parent not in source.parents:
                raise ValueError("sources must be inside the suite directory")
            task["code"] = source.read_text()
            task["source_sha256"] = digest(task["code"])
            if task.get("sha256") != task["source_sha256"]:
                raise ValueError(f"source hash mismatch for {name}; explicitly refreeze the manifest")
            if not task.get("provenance") or not task.get("category"):
                raise ValueError(f"missing provenance/category for {name}")
        self.sha256 = digest(json.dumps(self.data, sort_keys=True))

    def select(self, split):
        tasks = [task for task in self.tasks if task["split"] == split]
        if not tasks:
            raise ValueError(f"no programs in split {split}")
        return tasks


def cases(task_id, phase, seed, random_count=16):
    """Phase-separated deterministic streams; final seed is supplied only at evaluation."""
    if phase not in ("search", "selection", "final"):
        raise ValueError("unknown input phase")
    rng = random.Random(int(digest(f"{task_id}:{phase}:{seed}"), 16))
    result = []
    # Boundary cases intentionally overlap: they define the public semantic contract.
    for n in (0, 1, 2, 3, 7, 8, 15, 16, 31, 64, 257):
        for pattern in (0, MASK):
            result.append({"a": [pattern] * n, "x": pattern})
    for _ in range(random_count):
        n = rng.choice((1, 5, 17, 33, 65, 129, 511))
        result.append({"a": [rng.getrandbits(64) for _ in range(n)], "x": rng.getrandbits(64)})
    return result


def workload(task_id, phase, seed, n):
    rng = random.Random(int(digest(f"performance:{task_id}:{phase}:{seed}:{n}"), 16))
    return {"a": [rng.getrandbits(64) for _ in range(n)], "x": rng.getrandbits(64)}


def encode_case(case):
    return " ".join(str(v) for v in [len(case["a"]), case["x"], *case["a"]]) + "\n"
