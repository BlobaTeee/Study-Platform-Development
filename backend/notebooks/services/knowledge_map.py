"""The knowledge map of one notebook for one student.

Concepts are the documents' key points (merged across documents); each card,
question and practice problem is attached to one (ml_pipeline.concept_map).
Understanding is BKT over the student's answers and submits on a concept's
questions and problems, and the links they built by hand (map_building); memory is FSRS retrievability today of its cards.
The colour is the weaker of the two. No model call here: links are found
separately (find_links) and cached on the notebook.
"""
import hashlib

from django.core.cache import cache
from django.utils.translation import gettext as _

from ml_pipeline import bkt
from ml_pipeline.concept_map import attach, choose_action, clean_links, concept_state, merge_concepts, weaker
from ml_pipeline.language import detect_language, language_name
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose

ATTACH_TTL = 60 * 60


def concepts_of(notebook) -> list[dict]:
    points = []
    for src in notebook.sources.filter(status='ready').order_by('created_at', 'id').only('id', 'key_points'):
        for i, kp in enumerate(src.key_points or []):
            points.append({'key': f'{src.id}:{i}', 'source_id': src.id, 'label': kp.get('label') or kp.get('point', ''),
                           'point': kp.get('point', ''), 'passage': kp.get('passage', ''),
                           'importance': kp.get('importance', 'supporting')})
    concepts = merge_concepts(points)
    for n, c in enumerate(concepts, 1):
        c['index'] = n
    return concepts


def concepts_hash(concepts) -> str:
    return hashlib.sha1('|'.join(sorted(c['key'] for c in concepts)).encode()).hexdigest()[:16]


def _items(user, notebook):
    from exercises.models import Exercise
    from quizzes.models import Question
    from study_sessions.views import studiable_cards

    cards = list(studiable_cards(user).filter(notebook=notebook).prefetch_related('sources'))
    questions = list(Question.objects.filter(source__notebook=notebook).only('id', 'source_id', 'source_excerpt',
                                                                              'question_text', 'question_type'))
    exercises = list(Exercise.objects.filter(user=user, notebook=notebook))
    items = ([{'id': f'card:{c.id}', 'text': f'{c.question} {c.answer}', 'source_ids': [s.id for s in c.sources.all()]}
              for c in cards]
             + [{'id': f'q:{q.id}', 'text': q.source_excerpt or q.question_text,
                 'source_ids': [q.source_id] if q.source_id else []} for q in questions]
             + [{'id': f'ex:{e.id}', 'text': ' '.join(cp.get('basis', '') for cp in e.reference.get('checkpoints', []))
                 or e.prompt, 'source_ids': [e.source_id] if e.source_id else []} for e in exercises])
    return cards, questions, exercises, items


# A problem still to do comes before one already mastered.
EXERCISE_ORDER = {'revisit': 0, 'new': 1, 'mastered': 2}


def _review_counts(user, card_ids) -> dict[int, int]:
    """How many times each card was graded (seed rows are not reviews)."""
    from django.db.models import Count
    from study_sessions.models import CardReview
    return dict(CardReview.objects.grades().filter(user=user, flashcard_id__in=card_ids)
                .values('flashcard_id').annotate(n=Count('id')).order_by().values_list('flashcard_id', 'n'))


def _attached(notebook, concepts, items) -> dict:
    sig = hashlib.sha1((concepts_hash(concepts) + '|'.join(sorted(i['id'] for i in items))).encode()).hexdigest()
    key = f'map-attach:{notebook.id}:{sig}'
    got = cache.get(key)
    if got is None:
        got = attach(items, concepts)
        cache.set(key, got, ATTACH_TTL)
    return got


def _events(user, question_ids, exercise_ids) -> dict[str, list]:
    """Each item's answers in time order: {'q:7': [(when, correct, kind)], 'ex:3': [...]}"""
    from exercises.models import ExerciseAttempt
    from quizzes.models import Answer, MockTestQuestion
    out: dict[str, list] = {}
    for qid, ok, when, mode in Answer.objects.filter(quiz_attempt__user=user, question_id__in=question_ids) \
            .values_list('question_id', 'is_correct', 'answered_at', 'mode'):
        out.setdefault(f'q:{qid}', []).append((when, bool(ok), 'written' if mode == 'typed' else 'choice'))
    for qid, ok, when in MockTestQuestion.objects.filter(mock_test__user=user, question_id__in=question_ids,
                                                         is_correct__isnull=False, answered_at__isnull=False) \
            .values_list('question_id', 'is_correct', 'answered_at'):
        out.setdefault(f'q:{qid}', []).append((when, bool(ok), 'choice'))
    for eid, result, when in ExerciseAttempt.objects.filter(exercise_id__in=exercise_ids, kind='submit') \
            .values_list('exercise_id', 'result', 'created_at'):
        out.setdefault(f'ex:{eid}', []).append((when, result.get('verdict') == 'passed', 'written'))
    return out


def build_map(user, notebook) -> dict:
    from study_sessions.forecast import retrievability_today

    concepts = concepts_of(notebook)
    cards, questions, exercises, items = _items(user, notebook)
    where = _attached(notebook, concepts, items)
    params, thresholds = bkt.load()
    events = _events(user, [q.id for q in questions], [e.id for e in exercises])
    from .map_building import concept_events
    built = concept_events(user, notebook)        # links the student made and had graded
    recall = retrievability_today(user, [c.id for c in cards])
    reviews = _review_counts(user, [c.id for c in cards])
    exercise_rank = {e.id: EXERCISE_ORDER.get(e.status, 1) for e in exercises}

    members: dict[str, dict] = {c['key']: {'cards': [], 'questions': [], 'exercises': []} for c in concepts}
    for item_id, concept in where.items():
        if concept is None:
            continue
        kind, pk = item_id.split(':')
        members[concept][{'card': 'cards', 'q': 'questions', 'ex': 'exercises'}[kind]].append(int(pk))

    out = []
    for c in concepts:
        m = members[c['key']]
        evs = sorted([e for i in [f'q:{q}' for q in m['questions']] + [f'ex:{x}' for x in m['exercises']]
                      for e in events.get(i, [])] + built.get(c['key'], []), key=lambda e: e[0])
        understanding = ({'p': round(bkt.trace([(ok, kind) for _, ok, kind in evs], params), 3),
                          'correct': sum(ok for _, ok, _ in evs), 'total': len(evs)} if evs else None)
        reviewed = [recall[i] for i in m['cards'] if i in recall]
        # p, remembered and total are over the cards reviewed; the rest are unseen.
        memory = ({'p': round(sum(reviewed) / len(reviewed), 3), 'remembered': round(sum(reviewed)),
                   'total': len(reviewed), 'unseen': len(m['cards']) - len(reviewed)} if reviewed else None)
        u, mem = (understanding or {}).get('p'), (memory or {}).get('p')
        state = concept_state(u, mem, thresholds)
        weakest_cards = sorted(m['cards'], key=lambda i: recall.get(i, 0.0))
        to_do = sorted(m['exercises'], key=lambda i: exercise_rank.get(i, 1))
        # A strong concept needs only its scheduled reviews, so no button.
        action = None if state == 'strong' else choose_action(weaker(u, mem), weakest_cards, to_do, m['questions'])
        out.append({'key': c['key'], 'label': c['label'], 'point': c['point'], 'source_ids': c['source_ids'],
                    # The key points it holds ('source:index'), so a document can show its own.
                    'members': c.get('members', [c['key']]),
                    'importance': c['importance'], 'state': state,
                    'understanding': understanding, 'memory': memory,
                    'events': len(evs) + sum(reviews.get(i, 0) for i in m['cards']),
                    'action': action, 'first': None})

    edges, status = [], 'none' if len(concepts) < 2 else 'missing'
    links = notebook.concept_links or {}
    if len(concepts) >= 2 and links.get('hash') == concepts_hash(concepts):
        status, edges = 'ready', links.get('edges', [])
    rank = {'weak': 0, 'shaky': 1}
    by_key = {c['key']: c for c in out}
    for c in out:
        prereqs = [by_key[e['from']] for e in edges if e['to'] == c['key'] and e['from'] in by_key]
        shaky = sorted((p for p in prereqs if p['state'] in rank), key=lambda p: rank[p['state']])
        c['first'] = shaky[0]['key'] if shaky and c['state'] != 'strong' else None

    missing = [{'source_id': s.id, 'title': s.title}
               for s in notebook.sources.filter(status='ready').order_by('created_at', 'id').only('id', 'title',
                                                                                                  'key_points')
               if not s.key_points]
    return {'concepts': out, 'edges': edges, 'edges_status': status, 'missing_key_points': missing,
            'unattached': sum(1 for v in where.values() if v is None)}


class LinksUnavailable(Exception):
    pass


def find_links(notebook) -> list[dict]:
    """One request: which concepts must be understood before which."""
    concepts = concepts_of(notebook)
    if len(concepts) < 2:
        return []
    cached = notebook.concept_links or {}
    if cached.get('hash') == concepts_hash(concepts):
        return cached.get('edges', [])
    listed = '\n'.join(f'{c["index"]}. {c["label"]}: {c["point"]}' for c in concepts)
    lang = language_name(detect_language(listed))
    prompt = f"""These are the concepts of one subject a student is studying. Say which must be
understood before which: a pair means the second concept cannot be understood without the
first. Only clear, direct dependencies; at most 3 per concept; none for unrelated concepts.
For each pair give one short reason in {lang}.

Concepts:
{listed}

{WRITING_STYLE}

Return ONLY valid JSON: {{"links": [{{"before": 1, "after": 2, "why": "..."}}]}}"""
    unavailable = _('The links between concepts could not be found just now. Try again later.')
    try:
        data = get_ai_provider().generate_json(prompt)
    except Exception as exc:  # noqa: BLE001
        raise LinksUnavailable(unavailable) from exc
    raw = data.get('links') if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise LinksUnavailable(unavailable)
    edges = [{'from': concepts[a]['key'], 'to': concepts[b]['key'], 'why': tidy_prose(why)}
             for a, b, why in clean_links(raw, len(concepts))]
    notebook.concept_links = {'hash': concepts_hash(concepts), 'edges': edges}
    notebook.save(update_fields=['concept_links'])
    return edges
