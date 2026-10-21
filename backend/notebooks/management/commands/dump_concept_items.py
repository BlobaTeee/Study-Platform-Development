"""Dump one account's concepts and items for the knowledge map notebook.

The notebooks run on `.venv`, which has no Django, so this writes what
`10_knowledge_map.ipynb` needs to one JSON file: per notebook, the key points
as they are before merging, the merged concepts, the cards, questions and
problems to attach, and the links already found. Read-only.

    python manage.py dump_concept_items --email studyflow.demo@gmail.com
"""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from notebooks.models import Notebook
from notebooks.services.knowledge_map import _items, concepts_of

DEFAULT_OUT = Path(settings.BASE_DIR).parent / 'ml_pipeline' / 'outputs' / 'concept_items.json'


def _points(notebook) -> list[dict]:
    return [{'key': f'{src.id}:{i}', 'source_id': src.id, 'label': kp.get('label') or kp.get('point', ''),
             'point': kp.get('point', ''), 'passage': kp.get('passage', ''),
             'importance': kp.get('importance', 'supporting')}
            for src in notebook.sources.filter(status='ready').order_by('created_at', 'id')
            for i, kp in enumerate(src.key_points or [])]


class Command(BaseCommand):
    help = "Dump an account's concepts and items for the knowledge map notebook."

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--out', default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email=options['email']).first()
        if user is None:
            raise CommandError(f'No user {options["email"]}.')
        notebooks = []
        for nb in Notebook.objects.filter(user=user).order_by('id'):
            items = _items(user, nb)[3]
            concepts = concepts_of(nb)
            notebooks.append({'id': nb.id, 'title': nb.title, 'points': _points(nb), 'concepts': concepts,
                              'items': items, 'links': nb.concept_links or {}})
            self.stdout.write(f'#{nb.id} {nb.title}: {len(concepts)} concepts, {len(items)} items, '
                              f'{len((nb.concept_links or {}).get("edges", []))} links')
        out = Path(options['out'])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({'email': options['email'], 'notebooks': notebooks}, ensure_ascii=False, indent=1))
        self.stdout.write(self.style.SUCCESS(f'wrote {out}'))
