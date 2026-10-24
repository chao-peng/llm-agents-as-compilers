"""Model transport: JSON-only artifacts, explicit usage, no implicit paid retries."""

import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from .data import positive_int
from .process import run


class BudgetExhausted(RuntimeError):
    pass


class Budget:
    def __init__(self, config):
        self.max_calls = positive_int(config.get("max_calls", 8), "max_calls")
        self.max_tokens = positive_int(config.get("max_tokens", 100000), "max_tokens")
        self.max_seconds = positive_int(config.get("max_seconds", 1800), "max_seconds")
        self.calls = self.input_tokens = self.output_tokens = 0
        self.started = time.monotonic()
        self.usage_unknown = False

    def remaining_seconds(self):
        return max(0.0, self.max_seconds - (time.monotonic() - self.started))

    def reserve(self):
        if self.calls >= self.max_calls or self.input_tokens + self.output_tokens >= self.max_tokens or self.remaining_seconds() <= 0 or self.usage_unknown:
            raise BudgetExhausted("call, token, time, or unknown-usage stopping condition reached")
        self.calls += 1

    def charge(self, usage):
        # Missing usage must never look like a zero-cost call.
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
            self.usage_unknown = True
            return
        self.input_tokens += usage["input_tokens"]
        self.output_tokens += usage["output_tokens"]

    def snapshot(self):
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "usage_unknown": self.usage_unknown, "elapsed_seconds": time.monotonic() - self.started,
                "limits": {"max_calls": self.max_calls, "max_tokens": self.max_tokens, "max_seconds": self.max_seconds}}


def parse_artifact(content):
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    value = json.loads(text)
    if not isinstance(value, dict) or not isinstance(value.get("artifact"), str) or not value["artifact"].strip():
        raise ValueError('model must return {"artifact": "complete assembly or compiler source", "rationale": "..."}')
    if len(value["artifact"].encode()) > 1024 * 1024:
        raise ValueError("artifact exceeds 1 MiB")
    return value


class Provider:
    def __init__(self, config):
        self.config = config
        self.kind = config["kind"]
        if self.kind not in ("chat", "command", "replay", "demo"):
            raise ValueError("provider kind must be chat, command, replay, or demo")
        self.position = 0

    def generate(self, messages, context, timeout, directory):
        start = time.monotonic()
        if self.kind == "demo":
            from .demo_compiler import compile_source
            code = (compile_source(context["tasks"][0]["code"], context["target"])
                    if context["group"] == "direct" else Path(__file__).with_name("demo_compiler.py").read_text())
            response = {"content": json.dumps({"artifact": code, "rationale": "Handwritten offline fixture; not an LLM result"}),
                        "usage": {"input_tokens": 0, "output_tokens": 0}, "synthetic": True}
        elif self.kind == "replay":
            records = json.loads(Path(self.config["path"]).read_text())
            if self.position >= len(records):
                raise ValueError("replay exhausted")
            response = records[self.position]
            self.position += 1
        elif self.kind == "command":
            command = self.config["command"]
            if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
                raise ValueError("provider command must be an argv list, never a shell string")
            # Operator-controlled provider, not generated code. Explicit env names allow API authentication.
            from .process import clean_env
            env = clean_env(directory)
            for name in self.config.get("pass_env", []):
                if name in os.environ:
                    env[name] = os.environ[name]
            response = json.loads(run(command, directory, timeout, json.dumps({"messages": messages, "context": context}), env=env)["stdout"])
        else:
            base = self.config.get("base_url", "https://api.openai.com/v1").rstrip("/")
            parsed = urllib.parse.urlsplit(base)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("base_url must not embed credentials, query, or fragment")
            if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
                raise ValueError("use HTTPS except for a local model server")
            key_name = self.config.get("api_key_env", "OPENAI_API_KEY")
            key = os.environ.get(key_name)
            if not key and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                raise ValueError(f"missing environment variable {key_name}")
            payload = {"model": self.config["model"], "messages": messages,
                       "max_completion_tokens": self.config.get("max_completion_tokens", 8192)}
            extra = self.config.get("parameters", {})
            if set(extra) & {"messages", "model", "stream", "n", "max_completion_tokens"}:
                raise ValueError("parameters cannot override messages, model, stream, n, or token cap")
            payload.update(extra)
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = "Bearer " + key
            request = urllib.request.Request(base + "/chat/completions", json.dumps(payload).encode(), headers)
            # Do not forward a bearer token to a redirect target.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            try:
                with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as handle:
                    raw = json.loads(handle.read(4 * 1024 * 1024))
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"model HTTP {exc.code}; no automatic retry; usage may be unknown") from None
            usage = raw.get("usage", {})
            response = {"content": raw["choices"][0]["message"].get("content") or "",
                        "usage": {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")},
                        "model": raw.get("model"), "finish_reason": raw["choices"][0].get("finish_reason"),
                        "id": raw.get("id")}
        response["seconds"] = time.monotonic() - start
        return response
