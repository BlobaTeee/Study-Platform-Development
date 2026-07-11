from ml_pipeline.services.content_extractor import (
    Candidate, ContentExtractor, difficulty_for, DEFINITIONAL_LABELS,
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
    assert c.label  # some label assigned


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


def test_difficulty_for_returns_valid_bucket():
    c = Candidate(sentence="The cat sat on the mat.", term="cat",
                  label="NOUN_CHUNK", score=1.0)
    assert difficulty_for(c) in {"easy", "medium", "hard"}
