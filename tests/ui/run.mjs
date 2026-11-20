// Run Cypress against an isolated frontend, without forwarding requests to FastAPI.
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import cypress from 'cypress'

const project = fileURLToPath(new URL('./', import.meta.url))
const frontend = fileURLToPath(new URL('../../frontend/', import.meta.url))
const testRequire = createRequire(import.meta.url)
const frontendRequire = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { createServer } = await import(pathToFileURL(frontendRequire.resolve('vite')).href)
const { default: react } = await import(pathToFileURL(frontendRequire.resolve('@vitejs/plugin-react')).href)

execFileSync(process.execPath, [testRequire.resolve('typescript/bin/tsc'), '-p', `${project}tsconfig.json`], { stdio: 'inherit' })
const server = await createServer({
  root: frontend,
  configFile: false,
  plugins: [react()],
  server: { host: '127.0.0.1', port: 0 },
})
try {
  await server.listen()
  const address = server.httpServer.address()
  if (!address || typeof address === 'string') throw new Error('UI test server has no TCP port')
  const baseUrl = `http://127.0.0.1:${address.port}`
  console.log(`Isolated UI test server: ${baseUrl} (no backend proxy)`)
  const result = await cypress.run({ project, browser: 'electron', config: { baseUrl } })
  if ('failures' in result) {
    console.error(result.message)
    process.exitCode = 1
  } else {
    process.exitCode = result.totalFailed > 0 ? 1 : 0
  }
} finally {
  await server.close()
}
