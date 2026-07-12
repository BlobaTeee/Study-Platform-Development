# Product

## Register

product

## Users

University students studying from their own materials — lecture notes, PDFs, textbook
excerpts. They typically work solo, often under time pressure in the run-up to exams,
switching between reading a source, drilling flashcards, taking quizzes, and checking how
prepared they are. Sessions are focused and goal-driven: "get through this material and
know whether it stuck." They value legibility, low friction, and trust in the AI-generated
study content built from their own sources.

## Product Purpose

StudyFlow turns a student's own study material into active-recall practice. A source
(notes, PDF, pasted text) is the spine of the app: from it, StudyFlow generates flashcards
and quizzes, organizes material into notebooks, and surfaces analytics on what's mastered
and what needs work. An ML pipeline powers the generation and difficulty/recommendation
features. Success looks like a student trusting the generated cards enough to study from
them, returning across a study period, and feeling measurably more prepared — not points
earned, but material learned.

## Brand Personality

Calm, focused, scholarly. The interface is a quiet study environment, not a game and not a
hype machine. Voice is clear, plain, and respectful of the student's attention — it
explains without condescending and gets out of the way of the material. Three words:
**composed, legible, purposeful.** The emotional goal is reduced anxiety and sustained
concentration: the app should feel like good paper and a well-lit desk, where the AI is a
quiet assistant rather than the main character.

## Anti-references

- **Gamified / childish (Duolingo-style):** no cartoon mascots, confetti bursts, loud
  badges, streak-shaming, or reward-casino mechanics. Motivation comes from real progress
  on real material, not dopamine loops.
- **Overloaded AI-tool UI:** no chatbot-everywhere layouts, glowing-gradient "AI"
  aesthetics, or sci-fi sparkle. The AI generates study content silently; it does not
  colonize the interface. The study workflow stays in the foreground.
- Secondary avoids: generic purple-gradient SaaS dashboard templates (hero-metric + endless
  identical card grids), and sterile institutional LMS heaviness (Blackboard/Moodle clutter).

## Design Principles

1. **The source is the spine.** Every study surface traces back to the student's own
   material. Generation, review, and analytics all reference the source that produced them;
   nothing floats context-free.
2. **Paper, not app-chrome.** Lean into the study-paper metaphor — real depth, index-card
   flips, a faint engineering grid — so the app reads as a calm material surface, not a
   busy SaaS console.
3. **Legibility is the feature.** Studying is reading. Type, contrast, and spacing are
   non-negotiable; when in doubt, make it easier to read, not denser.
4. **Mode color is meaning.** The four mode colors (library/blue, flashcards/amber,
   quizzes/violet, analytics/emerald) are wayfinding, not decoration — one consistent
   colorway per activity, never applied arbitrarily.
5. **The AI is quiet.** AI-generated content earns trust by being accurate and reviewable,
   not by announcing itself. Surface provenance and let the student correct it; skip the
   sparkle.

## Accessibility & Inclusion

Target WCAG 2.1 AA. Body text ≥4.5:1 against its background (watch the muted-gray-on-tinted
trap, and placeholders at full 4.5:1); large text ≥3:1. Mode colors carry meaning, so never
rely on color alone — pair with labels/icons for color-blind users. Honor
`prefers-reduced-motion` on every animation (the 3D card flip already degrades to a
cross-fade and entrance "rise" is suppressed). Full keyboard operability for the core
study loops (flashcard flip/advance, quiz answering), visible focus rings, and legible
minimum sizing for long reading sessions.
