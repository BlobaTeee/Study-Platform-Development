"""Building a notebook's map by hand: the student links concepts and says why.

A round is about six concepts around the weakest (concept_map.pick_round),
shown without their links. The student's links are graded in one model
request. The document's links they did not make come from the notebook's
stored map, with no request. Graded links count on the map (concept_events):
a correct link is evidence of understanding both concepts, a wrong one
against, a partial one neither.
"""
from django.utils import timezone
from django.utils.translation import gettext as _

from ml_pipeline.concept_map import pick_round
from ml_pipeline.language import detect_language, language_name
from notebooks.models import MapBuild
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose

ROUND_SIZE = 6
MIN_CONCEPTS = 3
MAX_LINKS = 15
MIN_WHY, MAX_WHY = 3, 400
VERDICTS = ('correct', 'partial', 'wrong')


class TooFewConcepts(Exception):
    pass


class BadLinks(Exception):
    pass


class AlreadyGraded(Exception):
    pass


class GradingUnavailable(Exception):
    pass


def start_round(user, notebook) -> tuple[MapBuild, list[dict]]:
    """A new round: the concepts to link, chosen around the weakest."""
    from .knowledge_map import build_map, find_links
    the_map = build_map(user, notebook)
    concepts = the_map['concepts']
    if len(concepts) < MIN_CONCEPTS:
        raise TooFewConcepts(_('The map needs at least three concepts. Read the key points of more documents first.'))
    edges = the_map['edges'] if the_map['edges_status'] == 'ready' else find_links(notebook)
    keys = pick_round(concepts, edges, size=ROUND_SIZE)
    by_key = {c['key']: c for c in concepts}
    build = MapBuild.objects.create(user=user, notebook=notebook, concept_keys=keys)
    return build, [{'key': k, 'label': by_key[k]['label'], 'point': by_key[k]['point']} for k in keys]


def _pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def clean_links(raw, keys: list[str]) -> list[dict]:
    """The student's links, checked: in the round, not to itself, each pair once, with a reason."""
    if not isinstance(raw, list) or not raw:
        raise BadLinks(_('Link at least two concepts before sending.'))
    if len(raw) > MAX_LINKS:
        raise BadLinks(_('At most %(n)d links in one round.') % {'n': MAX_LINKS})
    seen, out = set(), []
    for item in raw:
        if not isinstance(item, dict):
            raise BadLinks(_('A link is not readable.'))
        a, b = str(item.get('from') or ''), str(item.get('to') or '')
        why = str(item.get('why') or '').strip()
        if a not in keys or b not in keys:
            raise BadLinks(_('A link joins a concept that is not in this round.'))
        if a == b:
            raise BadLinks(_('A concept cannot be linked to itself.'))
        if _pair(a, b) in seen:
            raise BadLinks(_('The same two concepts are linked twice.'))
        if not MIN_WHY <= len(why) <= MAX_WHY:
            raise BadLinks(_('Every link needs a short reason (up to %(n)d characters).') % {'n': MAX_WHY})
        seen.add(_pair(a, b))
        out.append({'from': a, 'to': b, 'why': why})
    return out


def grade(build: MapBuild, raw_links) -> MapBuild:
    """Grade the student's links in one request, and list the document's links they missed."""
    from .knowledge_map import concepts_of
    if build.graded_at:
        raise AlreadyGraded(_('This round has been graded already. Start another one.'))
    links = clean_links(raw_links, build.concept_keys)
    concepts = {c['key']: c for c in concepts_of(build.notebook)}
    names = {k: (concepts.get(k) or {}).get('label', k) for k in build.concept_keys}

    listed = '\n'.join(f'- {names[k]}: {(concepts.get(k) or {}).get("point", "")}' for k in build.concept_keys)
    asked = '\n'.join(f'{i}. {names[link["from"]]} — {names[link["to"]]}: "{link["why"]}"'
                      for i, link in enumerate(links, 1))
    lang = language_name(detect_language(listed + ' ' + asked))
    prompt = f"""A student is building a map of these concepts from their course:
{listed}

They linked pairs of concepts and wrote why each pair is related:
{asked}

For each numbered link, judge the student's reason against what the concepts mean:
- "correct": the relation is real and the reason states it accurately;
- "partial": the concepts are related but the reason is vague, incomplete or slightly off;
- "wrong": the reason is false, or the two concepts are not related in the way claimed.
Give one short sentence of feedback in {lang}, addressed to the student, saying what is right or what to fix.

{WRITING_STYLE}

Return ONLY valid JSON: {{"links": [{{"n": 1, "verdict": "correct", "feedback": "..."}}]}}"""
    try:
        data = get_ai_provider().generate_json(prompt)
    except Exception as exc:  # noqa: BLE001
        raise GradingUnavailable(_('The links could not be graded just now. Try again in a minute; your links are kept.')) from exc
    judged = {}
    for row in (data.get('links') if isinstance(data, dict) else None) or []:
        if isinstance(row, dict) and isinstance(row.get('n'), int):
            judged[row['n']] = row
    for i, link in enumerate(links, 1):
        row = judged.get(i) or {}
        verdict = row.get('verdict') if row.get('verdict') in VERDICTS else 'unjudged'
        link['verdict'] = verdict
        link['feedback'] = tidy_prose(str(row.get('feedback') or ''))[:400] if verdict != 'unjudged' else ''

    made = {_pair(link['from'], link['to']) for link in links}
    stored = (build.notebook.concept_links or {}).get('edges', [])
    in_round = set(build.concept_keys)
    build.missed = [{'from': e['from'], 'to': e['to'], 'why': e.get('why', '')} for e in stored
                    if e.get('from') in in_round and e.get('to') in in_round and _pair(e['from'], e['to']) not in made]
    build.links = links
    build.graded_at = timezone.now()
    build.save(update_fields=['links', 'missed', 'graded_at'])
    return build


def concept_events(user, notebook) -> dict[str, list]:
    """Graded links as evidence per concept: {key: [(when, correct, 'written')]}."""
    out: dict[str, list] = {}
    for build in MapBuild.objects.filter(user=user, notebook=notebook, graded_at__isnull=False):
        for link in build.links:
            if link.get('verdict') not in ('correct', 'wrong'):
                continue
            ok = link['verdict'] == 'correct'
            for key in (link['from'], link['to']):
                out.setdefault(key, []).append((build.graded_at, ok, 'written'))
    return out


def payload(build: MapBuild) -> dict:
    return {'id': build.id, 'links': build.links, 'missed': build.missed,
            'graded_at': build.graded_at.isoformat() if build.graded_at else None}
