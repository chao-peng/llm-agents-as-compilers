"""Trusted launcher for generated pure-Python compilers. Invoked with python -I -S.

The audit policy blocks delegation and networking; OS isolation is a separate layer.
This is not a proof that arbitrary Python or assembly is benign.
"""

import os
from pathlib import Path
import runpy
import sys

program, source, target = sys.argv[1:4]
job = Path(program).resolve().parent
runtime = Path(os.__file__).resolve().parent


def audit(event, args):
    if event.startswith(("subprocess", "socket", "ctypes", "os.exec", "os.spawn", "os.fork")) or event in (
        "os.system", "os.posix_spawn", "os.posix_spawnp", "os.chdir", "os.putenv", "os.unsetenv",
    ):
        raise PermissionError(f"compiler policy forbids {event}")
    if event == "open" and isinstance(args[0], (str, bytes)):
        p = Path(os.fsdecode(args[0])).resolve()
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            raise PermissionError("compiler must emit assembly on stdout; file writes are forbidden")
        if job not in p.parents and runtime not in p.parents:
            raise PermissionError("compiler can only read the current source and Python standard library")


sys.addaudithook(audit)
sys.argv = [program, source, target]
runpy.run_path(program, run_name="__main__")
