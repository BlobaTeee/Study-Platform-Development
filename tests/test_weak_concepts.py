"""Grouping missed questions into the concepts they are about."""
from ml_pipeline.weak_concepts import cluster_questions, top_terms

PHONES = [
    "What role do mobile phones play in the personal safety of homeless young people?",
    "What does a mobile phone serve as for homeless young people?",
    "How does phone theft affect the safety benefit of mobile phones for homeless youth?",
]
# Questions generated from one passage share its key terms — that is what
# the grouping leans on; a pure paraphrase with no shared term is out of scope.
CARS = [
    "What is one of the ethical issues that self-driving cars must address?",
    "Why must self-driving cars decide whom to protect in an unavoidable accident?",
]
POLICY = [
    "What was the final sample size of national AI policy strategies after screening?",
]


def test_questions_about_the_same_thing_land_in_one_cluster():
    clusters = cluster_questions(PHONES + CARS + POLICY)
    groups = sorted(sorted(c.indices) for c in clusters)
    assert [0, 1, 2] in groups          # the three phone questions
    assert [3, 4] in groups             # the two car questions


def test_a_lone_question_is_not_a_concept():
    clusters = cluster_questions(PHONES + POLICY)
    assert all(5 not in c.indices for c in clusters)
    assert len(clusters) == 1


def test_clusters_come_biggest_first():
    clusters = cluster_questions(CARS + PHONES)
    assert [len(c.indices) for c in clusters] == [3, 2]


def test_too_few_questions_means_no_clusters():
    assert cluster_questions([]) == []
    assert cluster_questions(["Only one?"]) == []


def test_top_terms_name_a_cluster_by_what_sets_it_apart():
    clusters = cluster_questions(PHONES + CARS)
    phones = next(c for c in clusters if 0 in c.indices)
    terms = top_terms(PHONES + CARS, phones.indices, k=3)
    assert terms and all(any(w in t for w in ("phone", "mobile", "homeless", "young", "safety")) for t in terms)
    assert not any("car" in t or "driving" in t for t in terms)


def test_vietnamese_works_without_a_language_model():
    vi = [
        "Quang hợp diễn ra ở bào quan nào của tế bào thực vật?",
        "Sắc tố nào hấp thụ ánh sáng trong quá trình quang hợp?",
        "Sản phẩm của pha sáng trong quang hợp là gì?",
        "Hô hấp kỵ khí tạo ra sản phẩm gì ở tế bào cơ?",
        "Hô hấp kỵ khí khác hô hấp hiếu khí ở điểm nào?",
    ]
    groups = sorted(sorted(c.indices) for c in cluster_questions(vi))
    assert groups == [[0, 1, 2], [3, 4]]
