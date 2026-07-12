from ml_pipeline.services.content_extractor import (
    Candidate, ContentExtractor, blank_term, difficulty_for, NOUN_CHUNK_LABEL,
)


def test_extract_pulls_named_entity_as_term():
    ext = ContentExtractor()
    cands = ext.extract_candidates(
        "Albert Einstein developed the theory of relativity in 1905.", max_candidates=5)
    assert cands
    einstein = [c for c in cands if c.term == "Albert Einstein"]
    assert einstein and einstein[0].label == "PERSON"
    # the term is a contiguous span of its support sentence
    assert einstein[0].term in einstein[0].sentence


def test_extract_falls_back_to_noun_chunk_when_no_entity():
    ext = ContentExtractor()
    cands = ext.extract_candidates(
        "Photosynthesis converts sunlight into chemical energy in plants.", max_candidates=5)
    assert cands
    c = cands[0]
    assert c.term and c.term in c.sentence
    assert c.label == NOUN_CHUNK_LABEL


def test_extract_dedupes_and_respects_max():
    ext = ContentExtractor()
    text = ("The cell contains a nucleus. The cell contains a nucleus. "
            "Ribosomes build proteins inside the cell.")
    cands = ext.extract_candidates(text, max_candidates=2)
    assert len(cands) <= 2
    terms = [c.term.lower() for c in cands]
    assert len(terms) == len(set(terms))  # no duplicate terms


def test_extract_empty_or_thin_text_returns_empty():
    ext = ContentExtractor()
    assert ext.extract_candidates("", max_candidates=5) == []
    assert ext.extract_candidates("Yes.", max_candidates=5) == []  # too short
    assert ext.extract_candidates("x y z", max_candidates=0) == []


def _cand(sentence):
    return Candidate(sentence=sentence, term="x", label=NOUN_CHUNK_LABEL, score=1.0)


def test_difficulty_buckets_by_reading_ease():
    # ease values verified with textstat.flesch_reading_ease
    assert difficulty_for(_cand("The cat sat on the mat.")) == "easy"  # ease ~116
    assert difficulty_for(_cand(
        "The utilization of heterogeneous methodologies necessitates comprehensive "
        "interdisciplinary collaboration among numerous institutional stakeholders."
    )) == "hard"  # ease ~-132
    assert difficulty_for(_cand(
        "Mitochondria are the powerhouse of the cell.")) == "medium"  # ease ~42.6


def test_extract_handles_possessive_terms():
    ext = ContentExtractor()
    cands = ext.extract_candidates(
        "The cell's nucleus contains genetic material essential for life.", max_candidates=5)
    assert cands, "a possessive sentence must not be silently dropped"
    assert all(c.term in c.sentence for c in cands)


def test_blank_term_respects_word_boundary():
    # "cell" must NOT be blanked inside the earlier "Cellular"; the standalone
    # "cell" is the one replaced, so the real term is not left visible.
    out = blank_term("Cellular structures surround the cell membrane.", "cell", "___")
    assert out == "Cellular structures surround the ___ membrane."


def test_blank_term_falls_back_when_no_boundary_match():
    # No standalone "cat" (only inside "category") -> plain replace.
    out = blank_term("The category matters.", "cat", "___")
    assert out == "The ___egory matters."


def test_blank_term_blanks_all_occurrences_so_answer_is_not_leaked():
    # A term repeated in its sentence must be fully removed, or the stem leaks
    # the answer (and lets the scorer trivially pass the question).
    out = blank_term("The cell membrane surrounds the cell.", "cell", "___")
    assert out == "The ___ membrane surrounds the ___."
    assert "cell" not in out
