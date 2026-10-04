"""Dump generated question sets for the quality notebook to score.

The notebooks run on the pure-Python env (`.venv`), which has no Django, so
they cannot reach the database or an AI provider. This command does the
Django-side work — pick excerpts, ask each provider for questions on the very
same excerpts, collect the questions already stored — and writes one JSON file
for `ml_pipeline/notebooks/06_question_quality.ipynb` to read.

Nothing is written back to the database: the generated sets exist only in the
dump, so measuring never pollutes a learner's quizzes.

    python manage.py dump_question_sets --providers ollama gemini --count 5
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from notebooks.models import Source
from notebooks.services import ai_provider
from notebooks.services.generate import _document_chunks, _sources_text, quiz_prompt
from ml_pipeline.language import detect_language
from quizzes.models import Question

DEFAULT_OUT = Path(settings.BASE_DIR).parent / 'ml_pipeline' / 'outputs' / 'question_sets.json'


class Command(BaseCommand):
    help = 'Dump stored and freshly generated question sets for the quality notebook.'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=int, nargs='*', default=[],
                            help='Source ids to generate from; default: the longest few.')
        parser.add_argument('--excerpts', type=int, default=3,
                            help='How many excerpts to generate from (default 3).')
        parser.add_argument('--providers', nargs='*', default=['ollama', 'gemini'],
                            help='Provider names; "gemini:gemini-3.8-flash" pins one model.')
        parser.add_argument('--count', type=int, default=5,
                            help='Questions per excerpt (default 5).')
        parser.add_argument('--out', default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        excerpts = self._excerpts(options['source'], options['excerpts'])
        if not excerpts:
            raise CommandError('No source has enough text to generate from.')
        self.stdout.write(f'{len(excerpts)} excerpts: '
                          + ', '.join(f"#{e['source_id']} {e['title'][:28]}" for e in excerpts))

        dump = {
            'count_requested': options['count'],
            'stored': self._stored(),
            'generated': {},
        }
        for provider_name in options['providers']:
            dump['generated'][provider_name] = self._generate(
                provider_name, excerpts, options['count'])

        out = Path(options['out'])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(dump, ensure_ascii=False, indent=1))
        self.stdout.write(self.style.SUCCESS(f'wrote {out}'))

    def _excerpts(self, source_ids: list[int], limit: int) -> list[dict]:
        """One chunk per source, the way generation itself would cut it."""
        sources = (Source.objects.filter(id__in=source_ids) if source_ids
                   else Source.objects.exclude(extracted_text='').order_by('-id')[:limit * 3])
        out = []
        for source in sources:
            chunks = _document_chunks([source])
            if not chunks:
                continue
            text = _sources_text([source])
            out.append({
                'source_id': source.id,
                'title': source.title,
                'lang': detect_language(text),
                'excerpt': chunks[0],
            })
            if len(out) >= limit:
                break
        return out

    def _stored(self) -> list[dict]:
        """Questions the platform already served, for the before/after picture."""
        rows = []
        for q in (Question.objects.exclude(source_excerpt='')
                  .filter(question_type='multiple_choice').select_related('quiz')):
            distractors = [o for o in (q.options or []) if o != q.correct_answer]
            rows.append({
                'question_text': q.question_text,
                'correct_answer': q.correct_answer,
                'distractors': distractors,
                'excerpt': q.source_excerpt,
                'quiz_id': q.quiz_id,
            })
        return rows

    def _generate(self, spec: str, excerpts: list[dict], count: int) -> list[dict]:
        """`spec` is a provider name, optionally `name:model` to pin one model."""
        provider_name, _, model = spec.partition(':')
        settings.AI_PROVIDER = provider_name
        if model:
            # No fallbacks while measuring: a silent switch to another model
            # would put its score under this model's name.
            settings.GEMINI_MODEL = model
            settings.GEMINI_MODEL_FALLBACKS = ''
        try:
            provider = ai_provider.get_ai_provider()
        except Exception as exc:
            self.stderr.write(f'{spec}: unavailable ({exc})')
            return []

        sets = []
        for excerpt in excerpts:
            prompt = quiz_prompt(excerpt['excerpt'], count, excerpt['lang'], excerpt['title'])
            started = time.time()
            try:
                data = provider.generate_json(prompt)
            except Exception as exc:
                self.stderr.write(f'{spec} on #{excerpt["source_id"]}: '
                                  f'{type(exc).__name__}: {exc}')
                continue
            sets.append({
                'source_id': excerpt['source_id'],
                'excerpt': excerpt['excerpt'],
                'seconds': round(time.time() - started, 1),
                'items': data.get('questions') or [],
            })
            self.stdout.write(f'  {spec} #{excerpt["source_id"]}: '
                              f'{len(sets[-1]["items"])} questions in {sets[-1]["seconds"]}s')
        return sets
