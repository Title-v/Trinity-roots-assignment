import { defineConfig } from 'cypress'

export default defineConfig({
  video: false,
  screenshotOnRunFailure: true,
  screenshotsFolder: 'screenshots',
  videosFolder: 'videos',
  viewportWidth: 1440,
  viewportHeight: 1000,
  retries: 0,
  defaultCommandTimeout: 6000,
  e2e: {
    supportFile: false,
    specPattern: 'e2e/**/*.cy.ts',
  },
})
