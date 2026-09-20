"""Which source a generated item's passage came from."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "provenance.py")


def _load():
    spec = importlib.util.spec_from_file_location("provenance_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


prov = _load()

SOURCES = [
    (1, "Cells.\n\nThe mitochondrion is the powerhouse of the cell. It makes ATP."),
    (2, "Genetics.\n\nDNA is transcribed into RNA, which is translated into protein."),
]


def test_a_passage_is_attributed_to_the_source_that_contains_it():
    assert prov.source_of("The mitochondrion is the powerhouse of the cell.", SOURCES) == 1
    assert prov.source_of("DNA is transcribed into RNA", SOURCES) == 2


def test_whitespace_and_line_breaks_do_not_matter():
    assert prov.source_of("the  mitochondrion is\nthe powerhouse", SOURCES) == 1


def test_a_passage_in_no_source_is_unattributed():
    assert prov.source_of("Photosynthesis makes glucose.", SOURCES) is None


def test_a_passage_spanning_two_sources_is_unattributed():
    # A chunk cut across the document boundary belongs to neither cleanly.
    assert prov.source_of("It makes ATP. Genetics. DNA is transcribed", SOURCES) is None


def test_a_passage_found_in_two_sources_is_unattributed():
    dup = [(1, "Water boils at 100 degrees."), (2, "Water boils at 100 degrees.")]
    assert prov.source_of("Water boils at 100 degrees.", dup) is None


def test_empty_passage_is_unattributed():
    assert prov.source_of("   ", SOURCES) is None


def test_excerpt_is_capped_on_a_sentence_boundary():
    long = "First sentence here. " * 100
    out = prov.excerpt_of(long, limit=100)
    assert len(out) <= 100 and out.endswith(".")
