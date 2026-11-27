// ESLint 9 flat config. `eslint-config-next` brings the Next.js, React and
// react-hooks rules — rules-of-hooks is the one that would have caught the
// "rendered more hooks" bug on the quiz page before the browser did.
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'

const config = [
  ...nextVitals,
  ...nextTs,
  {
    ignores: ['.next/**', 'node_modules/**', 'backend/**', 'ml_pipeline/**', '.venv/**', 'datasets/**', 'docs/report/tools/**'],
  },
  {
    rules: {
      // Known debt, kept visible but not blocking. Both predate this config:
      // eleven effects that set state synchronously (reset-on-change and
      // read-localStorage-on-mount patterns) and `any` on API request bodies
      // in lib/api.ts. Work them down; do not add new ones.
      'react-hooks/set-state-in-effect': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
]

export default config
