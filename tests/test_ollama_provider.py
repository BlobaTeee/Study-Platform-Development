"""Unit tests for the local Ollama generative provider (HTTP mocked).

The provider module has no Django/relative imports at module level, so we load
it directly from its file path and test it in isolation.
"""
import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "ollama_provider.py")


def _load():
    spec = importlib.util.spec_from_file_location("ollama_provider_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


op = _load()


# ---- extract_json (pure) ---------------------------------------------------

def test_extract_json_direct():
    assert op.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_from_surrounding_prose():
    assert op.extract_json('Sure! {"flashcards": []} — done') == {"flashcards": []}


def test_extract_json_strips_code_fence():
    assert op.extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_handles_nested_braces():
    assert op.extract_json('{"a": {"b": 2}} trailing junk') == {"a": {"b": 2}}


def test_extract_json_braces_inside_strings():
    assert op.extract_json('{"q": "what is {x}?"} tail') == {"q": "what is {x}?"}


def test_extract_json_empty_raises():
    with pytest.raises(ValueError):
        op.extract_json("")


def test_extract_json_no_object_raises():
    with pytest.raises(ValueError):
        op.extract_json("no json here at all")


# ---- OllamaProvider.generate_json (HTTP mocked) ----------------------------

def _provider_with_responses(responses):
    """Return (provider, calls) where _post yields responses in order."""
    prov = op.OllamaProvider(base_url="http://x", model="m", timeout=1)
    calls = []

    def fake_post(path, payload):
        calls.append((path, payload))
        return {"response": responses[len(calls) - 1]}

    prov._post = fake_post
    return prov, calls


def test_generate_json_parses_first_response():
    prov, calls = _provider_with_responses(['{"flashcards": [{"question": "q"}]}'])
    assert prov.generate_json("prompt") == {"flashcards": [{"question": "q"}]}
    assert len(calls) == 1


def test_generate_json_retries_then_succeeds():
    prov, calls = _provider_with_responses(["not json", '{"ok": true}'])
    assert prov.generate_json("prompt") == {"ok": True}
    assert len(calls) == 2  # first failed parse, retried


def test_generate_json_raises_after_two_failures():
    prov, calls = _provider_with_responses(["nope", "still nope"])
    with pytest.raises(op.OllamaError):
        prov.generate_json("prompt")
    assert len(calls) == 2


def test_generate_json_payload_requests_json_mode():
    prov, calls = _provider_with_responses(['{"ok": 1}'])
    prov.generate_json("my prompt")
    path, payload = calls[0]
    assert path == "/api/generate"
    assert payload["model"] == "m"
    assert payload["format"] == "json"
    assert payload["stream"] is False
    assert "my prompt" in payload["prompt"]


def test_post_transport_error_becomes_ollama_error():
    prov = op.OllamaProvider(base_url="http://x", model="m", timeout=1)

    def boom(path, payload):
        raise op.OllamaError("connection refused")

    prov._post = boom
    with pytest.raises(op.OllamaError):
        prov.generate_json("prompt")


def test_name_is_ollama():
    assert op.OllamaProvider().name == "ollama"
