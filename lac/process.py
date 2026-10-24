"""Bounded child processes with explicit execution isolation policy."""

import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import sys
import time


class ProcessError(RuntimeError):
    def __init__(self, kind, message):
        self.kind = kind
        super().__init__(message)


def clean_env(directory):
    return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(directory),
            "TMPDIR": str(directory), "LANG": "C", "LC_ALL": "C"}


def sandbox_command(command, directory):
    directory = Path(directory).resolve()
    command = [str(Path(command[0]).resolve()), *command[1:]]
    python_runtime = str(Path(sys.base_prefix).resolve())
    if platform.system() == "Darwin" and Path("/usr/bin/sandbox-exec").exists():
        # No project, home-directory, or network access. Only this isolated job and OS runtimes.
        roots = [str(directory), "/usr", "/bin", "/System", "/Library/Apple",
                 "/Applications/Xcode.app", "/Library/Developer/CommandLineTools", python_runtime]
        profile = '(version 1) (deny default) (import "system.sb") (deny network*) (allow process*) (allow sysctl-read) '
        profile += '(allow mach-lookup) (allow file-read-metadata) '
        profile += '(allow file-read* file-map-executable ' + " ".join(f'(subpath {json.dumps(p)})' for p in roots) + ') '
        profile += '(allow file-read* (literal "/dev/urandom") (literal "/dev/null")) '
        profile += f'(allow file-write* (subpath {json.dumps(str(directory))}) (literal "/dev/null"))'
        return ["/usr/bin/sandbox-exec", "-p", profile, *command]
    if platform.system() == "Linux" and shutil.which("bwrap"):
        args = [shutil.which("bwrap"), "--unshare-all", "--die-with-parent", "--new-session"]
        for root in dict.fromkeys(("/usr", "/bin", "/lib", "/lib64", python_runtime)):
            if Path(root).exists():
                args += ["--ro-bind", root, root]
        args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                 "--bind", str(directory), str(directory), "--chdir", str(directory)]
        return [*args, *command]
    raise ProcessError("sandbox_unavailable", "Install bubblewrap on Linux, or use --execution local only for trusted artifacts")


def run(command, directory, timeout=10, stdin="", execution="local", env=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if execution == "sandbox":
        command = sandbox_command(command, directory)
    elif execution != "local":
        raise ValueError("execution must be sandbox or local")

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, math.ceil(timeout)),) * 2)
        if platform.system() == "Linux":
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3,) * 2)

    start = time.monotonic()
    # Files bound output size via RLIMIT_FSIZE; communicate() cannot allocate unbounded output.
    with (directory / "stdout.log").open("w+") as out, (directory / "stderr.log").open("w+") as err:
        try:
            child = subprocess.Popen(command, cwd=directory, env=env or clean_env(directory),
                                     stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
                                     start_new_session=True, preexec_fn=limits)
        except OSError as exc:
            raise ProcessError("launch_error", str(exc)) from exc
        try:
            child.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
            raise ProcessError("timeout", f"process exceeded {timeout:.3f}s") from exc
        finally:
            # Also clean up descendants that survived a normally exiting parent.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        out.seek(0)
        err.seek(0)
        stdout, stderr = out.read(2 * 1024 * 1024), err.read(16384)
    if child.returncode:
        raise ProcessError("process_error", f"exit {child.returncode}: {stderr[-8000:]}")
    return {"stdout": stdout, "stderr": stderr, "seconds": time.monotonic() - start,
            "command": [str(arg) for arg in command]}
