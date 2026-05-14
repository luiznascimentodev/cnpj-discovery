import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import boundaries from 'eslint-plugin-boundaries'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'playwright-report', '.superpowers', 'coverage']),
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { boundaries, 'jsx-a11y': jsxA11y },
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      jsxA11y.flatConfigs.recommended,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    settings: {
      'boundaries/elements': [
        { type: 'app',      pattern: 'src/app/**'      },
        { type: 'pages',    pattern: 'src/pages/**'    },
        { type: 'widgets',  pattern: 'src/widgets/**'  },
        { type: 'features', pattern: 'src/features/**' },
        { type: 'entities', pattern: 'src/entities/**' },
        { type: 'shared',   pattern: 'src/shared/**'   },
      ],
    },
    rules: {
      'boundaries/element-types': ['error', {
        default: 'disallow',
        rules: [
          { from: 'app',      allow: ['app', 'pages', 'widgets', 'features', 'entities', 'shared'] },
          { from: 'pages',    allow: ['widgets', 'features', 'entities', 'shared'] },
          { from: 'widgets',  allow: ['features', 'entities', 'shared'] },
          { from: 'features', allow: ['entities', 'shared'] },
          { from: 'entities', allow: ['shared'] },
          { from: 'shared',   allow: [] },
        ],
      }],
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'dangerouslySetInnerHTML é proibido. Use texto ou DOMPurify se for absolutamente necessário.',
        },
      ],
      'no-restricted-imports': ['error', {
        patterns: [
          { group: ['*/internal/*', '*/_*'], message: 'Importe via Public API do slice (index.ts).' },
        ],
        paths: [
          { name: 'lucide-react', message: 'Importe ícones de @/shared/ui/icons (barrel curado).' },
        ],
      }],
    },
  },
])
