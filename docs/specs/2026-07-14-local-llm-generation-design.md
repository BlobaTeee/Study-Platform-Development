# Local Generative LLM for Flashcard/Quiz Generation — Design

**Date:** 2026-07-14
**Status:** Approved (design), pending implementation plan
**Author:** pairing session

## Problem

The local ML pipeline is *extractive*: it blanks a term out of a real source
sentence (cloze) or pairs "What is X?" with a source sentence. Users perceive
this as "copy-paste with a blank." Gemini produces synthesized, non-templated
questions but is a cloud dependency the project wants to reduce.

## Goal

Generate coherent, non-copy-paste flashcards and multiple-choice quizzes from a
source document using a **generative LLM running locally** (no cloud), on the
developer's MacBook Air (Apple M2, 8 GB RAM), for a final-year-project demo.

Non-goals: production/multi-user serving, fine-tuning, streaming output, changes
to the extractive pipeline or the Gemini path.

## Constraints

- **Hardware:** M2 / 8 GB unified memory shared with macOS, browser, Next.js,
  Django, Postgres. Feasible model size ≈ 3B params, 4-bit quantized (~2 GB).
- **Local only:** runs on the dev machine; not deployed to a server.
- **Offline / cloud-free:** the fallback when the local model fails must NOT be
  Gemini — it is the existing extractive ML.

## Approach (chosen)

**Ollama + provider adapter.** Ollama serves `llama3.2:3b` locally over HTTP.
A new `OllamaProvider` implements the backend's existing `AIProvider` interface
and is selected via `AI_PROVIDER=ollama`. The rest of the generation pipeline
(prompts, JSON parsing, DB save, fallback) is reused unchanged.

Rejected alternatives:
- **In-process (llama-cpp-python/transformers):** puts a ~2 GB model inside the
  Django process — memory pressure on 8 GB, slow reloads. Not viable here.
- **MLX (Apple-native):** fastest on M2 but weaker JSON-constraining/integration
  tooling. A possible future optimization, not the first build.

## Components

### Ollama (external dependency)
- Installed via `brew install ollama`; model pulled with `ollama pull llama3.2:3b`.
- Serves at `http://localhost:11434`. Runs as a background service alongside dev.

### `OllamaProvider` (new) — `backend/notebooks/services/ai_provider.py`
Implements `AIProvider`:
- `generate_json(prompt: str) -> dict` — POST `/api/generate` with
  `model`, `prompt`, `system` (JSON-only instruction), `format: "json"`,
  `stream: false`, `options: {temperature: 0.4}`. Parse and return a dict.
- `summarize(text: str, title: str = '') -> str` — plain-text call for the
  source overview at ingest time.
- `name -> 'ollama'`.
- HTTP via stdlib `urllib.request` (no new Python dependency).

### Config — `settings.py` / `.env`
- `AI_PROVIDER` (default `gemini`) — **add to settings.py** (currently only read
  via a getattr default in the factory). Values: `gemini` | `ollama` | `custom`.
- `OLLAMA_BASE_URL` (default `http://localhost:11434`).
- `OLLAMA_MODEL` (default `llama3.2:3b`).
- `OLLAMA_TIMEOUT` seconds (default `120`).
- To enable local generative mode: `AI_PROVIDER=ollama`, `USE_ML_PRIMARY=False`.

### Factory — `get_ai_provider()`
Add `ollama` → `OllamaProvider`. Keep `gemini` and `custom` behavior.

## Data flow (flashcards; quiz identical)

1. User clicks Generate → DRF view → `generate_flashcards_for_sources`.
2. Existing thin-input guard runs (`source_guard.check_source_text`).
3. `USE_ML_PRIMARY` is False → build the **existing** flashcard prompt.
4. `get_ai_provider()` → `OllamaProvider.generate_json(prompt)` → Ollama runs
   `llama3.2:3b` in JSON mode → `{"flashcards": [...]}`.
5. Existing `_save_flashcards_from_json` persists the cards.

The prompts and save logic are unchanged; only the provider differs.

## JSON reliability (3B model)

- `format: "json"` constrains Ollama to valid JSON.
- System prompt: output ONLY JSON matching the schema, no prose.
- Parse: `json.loads`; on failure, extract the first balanced `{...}` block; on
  failure, one stricter retry; then raise.
- `temperature ≈ 0.4` for consistency.

## Error handling / fallback (stays cloud-free)

Ollama unreachable, timeout, or unparseable JSON after retry → `OllamaProvider`
raises → caught by `generate.py`'s existing `except Exception → fallback` path →
**extractive ML** (cloze). Users always get output, never Gemini, fully offline.
Gemini remains available only if `AI_PROVIDER=gemini` is set explicitly.

## Testing

- **TDD unit tests** (HTTP mocked; no Ollama required):
  - valid JSON response → parsed dict
  - JSON wrapped in prose → extracted correctly
  - unparseable twice → raises (so fallback triggers)
  - request payload correct: model, `format:"json"`, prompt/system present
  - The parse/extract step is a pure function tested directly.
- **End-to-end verification** through Django against a real source (transaction
  rolled back), with Ollama running; then confirmed in the browser UI.

## Setup (one-time, guided)

```
brew install ollama
ollama serve            # background service
ollama pull llama3.2:3b # ~2 GB
```
Documented in `ml_pipeline`/backend README and `backend/.env.example`.

## Success criteria

Generating from a real source yields coherent, non-copy-paste flashcards and
MCQs as valid JSON, fully offline, in ~≤25 s, with graceful fallback to the
extractive ML on model failure — verified end-to-end and in the browser.
