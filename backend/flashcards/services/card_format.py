"""What a flashcard's two sides should hold, shared by every prompt that
writes one.

The answer is what a student has to recall, so it stays a short phrase; a
whole sentence on the back cannot be remembered word for word, and a student
grading themselves on it never knows whether "roughly" counts. The reasoning
goes in the explanation, read once the answer is out.
"""

ANSWER_RULES = """The "answer" is what the student must recall: a short phrase of at most
12 words, holding only the key words. No full sentences, and do not repeat
the question. Put the reasoning or extra detail in "explanation" (one or two
sentences), which the student reads after answering.
If a question would need a list of more than three items, write
separate flashcards instead, each asking for one part."""
