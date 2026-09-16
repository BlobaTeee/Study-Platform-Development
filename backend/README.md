# StudyFlow backend

Django + DRF API. Setup: copy `.env.example` to `.env`, then

```bash
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m spacy download en_core_web_sm   # extractive ML
venv/bin/python manage.py ensure_ml_model          # build the answer-scorer artifact
venv/bin/python manage.py compilemessages         # API messages in Vietnamese
venv/bin/python manage.py migrate
pnpm dev:backend                                   # or: venv/bin/python manage.py runserver 8000
```

## Tests

Two suites, two interpreters — on purpose:

```bash
# API and model tests: real Postgres (a throwaway test_studyflow database),
# Supabase bypassed, AI providers stubbed so nothing reaches the network.
cd backend && ./venv/bin/pytest            # add --create-db after a migration change

# Pure-function tests (ML pipeline, scheduling rules, timing): no Django.
.venv/bin/pytest                           # from the repo root
```

The app role needs `CREATEDB` on the Postgres server for the first suite
(`ALTER ROLE studyflow_user CREATEDB;` as a superuser, once).

## AI generation providers

Flashcard/quiz generation goes through a pluggable provider, chosen by
`AI_PROVIDER` in `.env`. On any provider error, generation falls back to the
extractive ML pipeline (spaCy + scikit-learn), so it always degrades gracefully
and never hard-fails.

| `AI_PROVIDER` | Generator | Notes |
|---|---|---|
| `gemini` | Google Gemini (cloud) | Needs `GEMINI_API_KEY`. Highest quality. |
| `ollama` | Local generative LLM | Fully offline, no cloud. See below. |
| (fallback) | Extractive ML | Cloze / definitional cards. Also the fallback for the above. |

Note: set `USE_ML_PRIMARY=False` for `gemini`/`ollama` to be used first;
`USE_ML_PRIMARY=True` makes the extractive ML the primary generator.

## Local generative LLM (Ollama)

Runs a small instruct model locally for synthesized (non-copy-paste) questions
with no cloud dependency.

```bash
brew install ollama            # https://ollama.com
ollama serve                   # start the local model server (keep running)
ollama pull llama3.2:3b         # ~2 GB, one time
```

Then in `.env`:

```
AI_PROVIDER=ollama
USE_ML_PRIMARY=False
OLLAMA_MODEL=llama3.2:3b        # swap models here
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT=120
```

Restart the backend after changing `.env`. `ollama serve` must be running
whenever `AI_PROVIDER=ollama`; if it isn't, generation falls back to the
extractive ML. Provider code: `notebooks/services/ollama_provider.py`
(unit-tested in `tests/test_ollama_provider.py`).

Model choice is memory-bound: `llama3.2:3b` (~2 GB) suits an 8 GB machine;
larger models improve quality at the cost of RAM and latency.
