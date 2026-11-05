"""Building a map yourself: the concepts from memory, the links, and why.

From the document they are reading (its key points hidden meanwhile), the
student writes the concepts they remember as cards and links them with a reason.
One model request compares that with the document's key points: which card
stands for which point, and a verdict on each link. The document's own links
between recalled concepts the student did not join come from the notebook's
stored map, with no request. Nothing is stored until it is graded.

A graded link is evidence on the map (concept_events) for the concepts its
cards stand for: correct counts right, wrong counts wrong, partial neither.
"""
from django.utils import timezone
from django.utils.translation import gettext as _

from ml_pipeline.language import detect_language, language_name
from notebooks.models import MapBuild
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose

MIN_POINTS = 3
MIN_CARDS, MAX_CARDS, MAX_LABEL = 3, 20, 80
MAX_LINKS = 30
MIN_WHY, MAX_WHY = 3, 400
VERDICTS = ('correct', 'partial', 'wrong')


class BadMap(Exception):
    pass


class GradingUnavailable(Exception):
    pass


def _pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def clean_cards(raw) -> list[dict]:
    if not isinstance(raw, list) or len(raw) < MIN_CARDS:
        raise BadMap(_('Write at least %(n)d concepts you remember.') % {'n': MIN_CARDS})
    if len(raw) > MAX_CARDS:
        raise BadMap(_('At most %(n)d concepts in one map.') % {'n': MAX_CARDS})
    seen_ids, seen_labels, out = set(), set(), []
    for item in raw:
        card_id = str((item or {}).get('id') or '')[:40] if isinstance(item, dict) else ''
        label = ' '.join(str(item.get('label') or '').split()) if isinstance(item, dict) else ''
        if not card_id or card_id in seen_ids:
            raise BadMap(_('A concept is not readable.'))
        if not 1 <= len(label) <= MAX_LABEL:
            raise BadMap(_('Every concept needs a name (up to %(n)d characters).') % {'n': MAX_LABEL})
        if label.casefold() in seen_labels:
            raise BadMap(_('The concept “%(label)s” is written twice.') % {'label': label})
        seen_ids.add(card_id)
        seen_labels.add(label.casefold())
        out.append({'id': card_id, 'label': label})
    return out


def clean_links(raw, card_ids: set[str]) -> list[dict]:
    """The student's links: between two of their cards, each pair once, with a reason."""
    if not isinstance(raw, list) or not raw:
        raise BadMap(_('Link at least two concepts before sending.'))
    if len(raw) > MAX_LINKS:
        raise BadMap(_('At most %(n)d links in one map.') % {'n': MAX_LINKS})
    seen, out = set(), []
    for item in raw:
        if not isinstance(item, dict):
            raise BadMap(_('A link is not readable.'))
        a, b = str(item.get('from') or ''), str(item.get('to') or '')
        why = str(item.get('why') or '').strip()
        if a not in card_ids or b not in card_ids:
            raise BadMap(_('A link joins a concept that is not on the map.'))
        if a == b:
            raise BadMap(_('A concept cannot be linked to itself.'))
        if _pair(a, b) in seen:
            raise BadMap(_('The same two concepts are linked twice.'))
        if not MIN_WHY <= len(why) <= MAX_WHY:
            raise BadMap(_('Every link needs a short reason (up to %(n)d characters).') % {'n': MAX_WHY})
        seen.add(_pair(a, b))
        out.append({'from': a, 'to': b, 'why': why})
    return out


def _reference(notebook, source) -> list[dict]:
    """The document's key points, each with the map concept it belongs to."""
    from .knowledge_map import concepts_of
    concept_of = {member: c['key'] for c in concepts_of(notebook) for member in c.get('members', [c['key']])}
    return [{'key': concept_of.get(f'{source.id}:{i}'), 'label': kp.get('label') or kp.get('point', ''),
             'point': kp.get('point', '')}
            for i, kp in enumerate(source.key_points or [])]


def grade(user, notebook, source_id, raw_cards, raw_links) -> MapBuild:
    """Compare the student's map with the document in one request, and keep it."""
    source = notebook.sources.filter(pk=source_id, status='ready').first()
    if source is None or len(source.key_points or []) < MIN_POINTS:
        raise BadMap(_('Choose a document whose key points have been read.'))
    cards = clean_cards(raw_cards)
    links = clean_links(raw_links, {c['id'] for c in cards})
    points = _reference(notebook, source)
    number = {c['id']: i for i, c in enumerate(cards, 1)}

    listed_points = '\n'.join(f'{i}. {p["label"]}: {p["point"]}' for i, p in enumerate(points, 1))
    listed_cards = '\n'.join(f'{i}. {c["label"]}' for i, c in enumerate(cards, 1))
    asked = '\n'.join(f'{i}. card {number[link["from"]]} — card {number[link["to"]]}: "{link["why"]}"'
                      for i, link in enumerate(links, 1))
    # The feedback is for the student: their own words decide the language, the
    # cards and then the document only when theirs do not tell.
    said = detect_language(' '.join(link['why'] for link in links))
    if said == 'other':
        said = detect_language(listed_cards)
    lang = language_name(said if said != 'other' else detect_language(listed_points))
    prompt = f"""A student drew a concept map of a document from memory.

The document's key points:
{listed_points}

The student's concepts (cards), in their own words:
{listed_cards}

The links they drew, each with their reason:
{asked}

1. For each card, give the number of the key point it stands for (same idea, even if worded
   differently or in another language), or null if it matches none.
2. For each numbered link, judge the student's reason:
   - "correct": the relation is real and the reason states it accurately;
   - "partial": the concepts are related but the reason is vague, incomplete or slightly off;
   - "wrong": the reason is false, or the two concepts are not related in the way claimed.
   Give one short sentence of feedback in {lang}, addressed to the student, saying what is right or what to fix.

{WRITING_STYLE}

Return ONLY valid JSON: {{"cards": [{{"n": 1, "matches": 2}}],
"links": [{{"n": 1, "verdict": "correct", "feedback": "..."}}]}}"""
    try:
        data = get_ai_provider().generate_json(prompt)
    except Exception as exc:  # noqa: BLE001
        raise GradingUnavailable(_('The map could not be compared just now. Try again in a minute; your map is kept.')) from exc
    data = data if isinstance(data, dict) else {}

    matched = {}
    for row in data.get('cards') or []:
        if isinstance(row, dict) and isinstance(row.get('n'), int) and isinstance(row.get('matches'), int):
            if 1 <= row['matches'] <= len(points):
                matched[row['n']] = points[row['matches'] - 1]
    for i, card in enumerate(cards, 1):
        point = matched.get(i)
        card['match_key'] = point['key'] if point else None
        card['match_label'] = point['label'] if point else None

    judged = {row['n']: row for row in data.get('links') or [] if isinstance(row, dict) and isinstance(row.get('n'), int)}
    for i, link in enumerate(links, 1):
        row = judged.get(i) or {}
        verdict = row.get('verdict') if row.get('verdict') in VERDICTS else 'unjudged'
        link['verdict'] = verdict
        link['feedback'] = tidy_prose(str(row.get('feedback') or ''))[:400] if verdict != 'unjudged' else ''

    recalled = {p['label'] for p in matched.values()}
    missed_points = [{'label': p['label'], 'point': p['point']} for p in points if p['label'] not in recalled]

    # The document's links between two recalled concepts that the student did not join.
    card_for = {}
    for card in cards:
        if card['match_key'] and card['match_key'] not in card_for:
            card_for[card['match_key']] = card['id']
    joined = {_pair(link['from'], link['to']) for link in links}
    missed = []
    for edge in (notebook.concept_links or {}).get('edges', []):
        a, b = card_for.get(edge.get('from')), card_for.get(edge.get('to'))
        if a and b and a != b and _pair(a, b) not in joined:
            missed.append({'from': a, 'to': b, 'why': edge.get('why', '')})

    return MapBuild.objects.create(user=user, notebook=notebook, source=source, cards=cards, links=links,
                                   missed=missed, missed_points=missed_points, graded_at=timezone.now())


def concept_events(user, notebook) -> dict[str, list]:
    """Graded links as evidence per map concept: {key: [(when, correct, 'written')]}."""
    out: dict[str, list] = {}
    for build in MapBuild.objects.filter(user=user, notebook=notebook, graded_at__isnull=False):
        stands_for = {c['id']: c.get('match_key') for c in build.cards}
        for link in build.links:
            if link.get('verdict') not in ('correct', 'wrong'):
                continue
            ok = link['verdict'] == 'correct'
            for key in {stands_for.get(link['from']), stands_for.get(link['to'])} - {None}:
                out.setdefault(key, []).append((build.graded_at, ok, 'written'))
    return out


def payload(build: MapBuild) -> dict:
    total = len(build.source.key_points or []) if build.source else len(build.missed_points)
    return {'id': build.id, 'cards': build.cards, 'links': build.links, 'missed': build.missed,
            'missed_points': build.missed_points, 'recalled': total - len(build.missed_points), 'total': total}
