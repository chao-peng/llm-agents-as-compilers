"""Handwritten smoke fixture, NOT an LLM-generated or general C compiler.

Translates one uint64_t return expression over x/n/constants using +,-,*,&,|,^,<<,>>.
This tiny compiler provides a genuine reusable source-to-assembly path for offline tests.
"""

import ast
import re
import sys


def compile_source(source, target):
    match = re.search(r"\{\s*return\s+(.+?);\s*\}\s*$", source, re.S)
    if not match:
        raise ValueError("fixture only supports one return expression")
    expression = ast.parse(match.group(1), mode="eval").body
    arm = target.startswith(("arm64", "aarch64"))
    if not arm and not target.startswith("x86_64"):
        raise ValueError("fixture supports arm64 and x86_64 only")
    symbol = "_kernel" if "apple" in target else "kernel"
    lines = [".text", ".globl " + symbol, ".p2align 2" if arm else ".p2align 4", symbol + ":"]

    def emit(node):
        if isinstance(node, ast.Name) and node.id in ("x", "n"):
            lines.append(("mov x9, " + ("x2" if node.id == "x" else "x1")) if arm
                         else ("movq " + ("%rdx" if node.id == "x" else "%rsi") + ", %rax"))
        elif isinstance(node, ast.Constant) and type(node.value) is int and 0 <= node.value <= 65535:
            lines.append(f"mov x9, #{node.value}" if arm else f"movq ${node.value}, %rax")
        elif isinstance(node, ast.BinOp):
            emit(node.left)
            lines.extend(["sub sp, sp, #16", "str x9, [sp]"] if arm else ["pushq %rax"])
            emit(node.right)
            lines.extend(["mov x10, x9", "ldr x9, [sp]", "add sp, sp, #16"] if arm
                         else ["movq %rax, %r10", "popq %rax"])
            ops = {ast.Add: ("add", "addq"), ast.Sub: ("sub", "subq"), ast.Mult: ("mul", "imulq"),
                   ast.BitAnd: ("and", "andq"), ast.BitOr: ("orr", "orq"), ast.BitXor: ("eor", "xorq"),
                   ast.LShift: ("lsl", "shlq"), ast.RShift: ("lsr", "shrq")}
            if type(node.op) not in ops:
                raise ValueError("unsupported operator")
            op = ops[type(node.op)][0 if arm else 1]
            if arm:
                lines.append(f"{op} x9, x9, x10")
            elif isinstance(node.op, (ast.LShift, ast.RShift)):
                lines.extend(["movq %r10, %rcx", f"{op} %cl, %rax"])
            else:
                lines.append(f"{op} %r10, %rax")
        else:
            raise ValueError("unsupported expression")

    emit(expression)
    if arm:
        lines.append("mov x0, x9")
    lines.append("ret")
    if "linux" in target:
        lines.append('.section .note.GNU-stack,"",%progbits' if arm else '.section .note.GNU-stack,"",@progbits')
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    with open(sys.argv[1]) as source_file:
        print(compile_source(source_file.read(), sys.argv[2]), end="")
