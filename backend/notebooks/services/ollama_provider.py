"""Local generative provider backed by an Ollama server.

Fulfills the AIProvider contract used by generate.py (`generate_json`,
`summarize`, `name`) but runs a small instruct model locally instead of calling
a cloud API. Deliberately has NO Django or relative imports at module level so
the parsing logic can be unit-tested in isolation; configuration is injected by
the factory in ai_provider.py.
"""
from __future__ import annotations

import json
import re
import urllib.request

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"
DEFAULT_TIMEOUT = 120  # seconds; local generation is slow on modest hardware

_JSON_SYSTEM = (
    "You are a study-content generator. Respond with ONLY valid JSON matching "
    "the requested schema. No markdown, no prose, no code fences."
)


class OllamaError(RuntimeError):
    """Local model unreachable, timed out, or returned unusable output.

    generate.py treats any provider exception as a signal to fall back to the
    extractive ML pipeline, so this stays cloud-free.
    """


def extract_json(text: str) -> dict:
    """Recover a JSON object from model output, tolerating minor wrapping.

    Tries a direct parse, strips code fences, then falls back to the first
    balanced ``{...}`` span. Raises ValueError if nothing usable is found.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")
    if text.startswith("```"):
        text = text.strip("`").strip()
        text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = _first_json_object(text)
    if not isinstance(obj, dict):
        raise ValueError("model response is not a JSON object")
    return obj


def _first_json_object(text: str) -> dict:
    """Return the first balanced ``{...}`` object in text, respecting strings."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in model response")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON object in model response")


class OllamaProvider:
    """AIProvider (duck-typed) that calls a local Ollama server over HTTP."""

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 timeout: int | None = None):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout or DEFAULT_TIMEOUT

    @property
    def name(self) -> str:
        return "ollama"

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON to the Ollama server; raise OllamaError on any failure."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # transport, timeout, or decode error
            raise OllamaError(
                f"Ollama request to {path} failed ({exc}). Is `ollama serve` "
                f"running and `{self.model}` pulled?"
            ) from exc

    def _generate(self, prompt: str, *, system: str, json_mode: bool) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.4},
        }
        if json_mode:
            payload["format"] = "json"
        result = self._post("/api/generate", payload)
        return (result.get("response") or "").strip()

    def generate_json(self, prompt: str) -> dict:
        """Generate a JSON object, with one stricter retry before giving up."""
        text = self._generate(prompt, system=_JSON_SYSTEM, json_mode=True)
        try:
            return extract_json(text)
        except ValueError:
            pass  # fall through to a stricter retry
        strict = prompt + "\n\nReturn ONLY the JSON object and nothing else."
        text = self._generate(strict, system=_JSON_SYSTEM, json_mode=True)
        try:
            return extract_json(text)
        except ValueError as exc:
            raise OllamaError(f"model did not return valid JSON: {exc}") from exc

    def summarize(self, text: str, title: str = "") -> str:
        prompt = (
            f"Summarize the following document titled {title!r} in 2-3 sentences "
            f"as a study overview.\n\n{text[:8000]}"
        )
        return self._generate(
            prompt, system="You are a concise study assistant.", json_mode=False
        ).strip()
