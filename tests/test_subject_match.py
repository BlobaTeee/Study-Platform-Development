"""A new upload joins the notebook of its subject, or starts a new one."""
from ml_pipeline.subject_match import best_notebook, score_notebooks

# The second part of a chemistry lecture shares its vocabulary; the others share
# none of it. How often lectures on *different* topics of one subject are
# recognised is measured in notebooks/07_subject_matching.ipynb, not here.
CHEM = """Atoms are made of protons, neutrons and electrons. The periodic table orders the elements by
atomic number, and electrons fill shells around the nucleus. Covalent bonds form when atoms share electron
pairs; ionic bonds form when electrons transfer from a metal to a non-metal, giving ions held together by
electrostatic attraction. Molecules such as water are polar because oxygen pulls the shared electrons
towards itself. Chemical bonds store energy, and breaking bonds in a reaction absorbs energy."""
CHEM_NEW = """Chemical bonding, part two. Covalent bonds share electron pairs between atoms, and the
shared electrons sit between the two nuclei. Ionic bonds form when electrons transfer from a metal atom to a
non-metal atom, so the ions are held by electrostatic attraction. Polar molecules such as water have shared
electrons pulled towards the more electronegative atom. Breaking chemical bonds absorbs energy and forming
bonds releases energy, which decides whether a reaction gives out heat."""
BIO = """Cells are the basic unit of life. Mitochondria produce ATP through cellular respiration: glucose
is broken down in glycolysis, then the Krebs cycle and oxidative phosphorylation release energy. Plants
capture light in chloroplasts during photosynthesis. DNA in the nucleus carries the genes that code for
proteins, and ribosomes translate messenger RNA into chains of amino acids."""
HISTORY = """The treaty ended the war in 1648 and redrew the borders of the empire. Envoys negotiated for
years over territory, religion and the rights of the princes, and the settlement shaped European diplomacy
for a century. Historians still debate whether it created the modern idea of state sovereignty or simply
recorded a balance of power that the fighting had already produced."""


def test_a_document_joins_the_notebook_of_its_subject():
    assert best_notebook(CHEM_NEW, {'chem': [CHEM], 'bio': [BIO]}) == 'chem'


def test_a_subject_with_no_notebook_starts_a_new_one():
    assert best_notebook(HISTORY, {'chem': [CHEM], 'bio': [BIO]}) is None


def test_a_notebook_scores_as_its_closest_document():
    # A subject's notebook holds several topics; one close document is enough.
    ranked = score_notebooks(CHEM_NEW, {'science': [BIO, CHEM], 'other': [HISTORY]})
    assert ranked[0][0] == 'science'
    assert ranked[0][1] > ranked[1][1]


def test_no_notebooks_or_no_text_means_a_new_notebook():
    assert best_notebook(CHEM, {}) is None
    assert best_notebook(CHEM, {'empty': ['', '  ']}) is None
    assert best_notebook('   ', {'chem': [CHEM]}) is None


def test_the_threshold_can_be_set_per_call():
    assert best_notebook(CHEM_NEW, {'chem': [CHEM]}, threshold=0.999) is None
