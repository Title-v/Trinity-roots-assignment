import frontendConfig from '../../frontend/eslint.config.js'

export default [
  ...frontendConfig,
  { ignores: ['**/screenshots/**', '**/videos/**'] },
  {
    files: ['**/*.cy.ts'],
    languageOptions: {
      globals: { cy: 'readonly', Cypress: 'readonly', expect: 'readonly', describe: 'readonly', it: 'readonly', beforeEach: 'readonly' },
    },
  },
]
