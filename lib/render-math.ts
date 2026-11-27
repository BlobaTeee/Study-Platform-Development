// One formula typeset by KaTeX, with mhchem loaded so a chemical formula
// written \ce{H2SO4} comes out upright, as chemistry prints it; $H_2SO_4$
// would set each letter in maths italics.
import katex from 'katex'
import 'katex/contrib/mhchem'

/** HTML for `tex`; a formula KaTeX cannot read is its source in red. */
export function renderMath(tex: string, display: boolean): string {
  return katex.renderToString(tex, {
    displayMode: display,
    throwOnError: false,
    errorColor: '#b91c1c',
    trust: false,
  })
}
