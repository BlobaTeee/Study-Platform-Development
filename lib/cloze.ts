/** Fill-in-the-blank cards: checking what the student typed.
 *
 *  The check only suggests a grade; the student still presses Hard, Good or
 *  Easy, because they know better than a string compare whether "efficient"
 *  meant what the source meant by "effective". So it errs towards "close"
 *  for a missing accent or a slip of the finger, and towards "wrong" for a
 *  different word. */

export type ClozeVerdict = 'correct' | 'close' | 'wrong' | 'empty'

export const BLANK = '___'

export function checkTyped(typed: string, answer: string): ClozeVerdict {
  const said = normalize(typed)
  const meant = normalize(answer)
  if (!said) return 'empty'
  if (said === meant) return 'correct'
  // Vietnamese typed without its accents is the same word on a phone that
  // has no Telex; a different accent, though, can be a different word, and
  // that is exactly what "close" leaves for the student to judge.
  if (stripAccents(said) === stripAccents(meant)) return 'close'
  // One slip is a typo only in a word long enough to survive it: "cat" for
  // "car" is another word.
  if (meant.length >= 6 && editDistance(said, meant) <= 1) return 'close'
  return 'wrong'
}

export function suggestedGrade(verdict: ClozeVerdict): 'hard' | 'good' | null {
  if (verdict === 'empty') return null
  return verdict === 'wrong' ? 'hard' : 'good'
}

/** The text before and after the blank. */
export function splitAtBlank(sentence: string): [string, string] {
  const at = sentence.indexOf(BLANK)
  if (at < 0) return [sentence, '']
  return [sentence.slice(0, at), sentence.slice(at + BLANK.length)]
}

function normalize(text: string): string {
  return text
    .normalize('NFC')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function stripAccents(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/g, 'd')
}

function editDistance(a: string, b: string): number {
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j)
  for (let i = 1; i <= a.length; i++) {
    const row = [i]
    for (let j = 1; j <= b.length; j++) {
      row[j] = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
    }
    prev = row
  }
  return prev[b.length]
}
