// Prova "in bosco": scarica la zona pubblicata, stacca la rete, la mappa deve funzionare lo stesso.
// Uso: npm run build && npm run e2e:offline   (serve almeno una zona in public/mappe/)
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const root = fileURLToPath(new URL('..', import.meta.url))
const shots = process.env.SCREENSHOTS ?? fileURLToPath(new URL('./screenshots', import.meta.url))
mkdirSync(shots, { recursive: true })
if (!existsSync(`${root}/dist/mappe/index.json`)) {
  console.error('nessuna mappa pubblicata in dist/mappe: niente da provare offline')
  process.exit(1)
}

const PORT = 4174
const BASE = `http://localhost:${PORT}`
try {
  await fetch(`${BASE}/`)
  console.error(`porta ${PORT} già occupata`)
  process.exit(1)
} catch {
  /* porta libera */
}
const server = spawn(`${root}/node_modules/.bin/vite`, ['preview', '--port', String(PORT), '--strictPort'], {
  cwd: root,
  stdio: 'ignore',
  detached: true,
})
for (let i = 0; i < 50; i++) {
  try {
    if ((await fetch(`${BASE}/`)).ok) break
  } catch {
    /* non ancora su */
  }
  await new Promise((r) => setTimeout(r, 200))
}

const errors = []
let browser
try {
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  })
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    serviceWorkers: 'allow',
    locale: 'it-IT',
    timezoneId: 'Europe/Rome',
    geolocation: { latitude: 44.585, longitude: 10.105, accuracy: 8 },
    permissions: ['geolocation'],
  })
  const page = await context.newPage()
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource|tile\.|AJAXError|Failed to fetch/.test(m.text())) errors.push(`console: ${m.text()}`)
  })

  await page.goto(`${BASE}/impostazioni`)
  // L'app deve essere in cache nel service worker prima di staccare la rete.
  await page.evaluate(() => navigator.serviceWorker.ready)
  if (!(await page.evaluate(() => !!navigator.serviceWorker.controller))) await page.reload()
  await page.locator('[data-testid=download-area]').first().click()
  await page.getByText(/pronta per il campo, anche senza rete/).waitFor({ timeout: 60000 })

  await context.setOffline(true)
  await page.goto(`${BASE}/mappa?lon=10.105&lat=44.585&z=15`)
  await page.locator('[data-testid=map] canvas').waitFor()
  await page.waitForTimeout(5000)
  await page.screenshot({ path: `${shots}/offline-mappa.png` })
  // Toccando la mappa offline arriva lo score del punto.
  const box = await page.locator('[data-testid=map]').boundingBox()
  await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.6)
  await page.locator('[data-testid=sheet]').getByText(/parametri/).first().waitFor()
  await page.goto(`${BASE}/`)
  await page.getByText('Tartufo nero (T. aestivum / uncinatum)').waitFor()

  if (errors.length) throw new Error(`errori in pagina:\n${errors.join('\n')}`)
  console.log(`offline ok · schermate in ${shots}`)
} catch (e) {
  console.error(e.message)
  process.exitCode = 1
} finally {
  await browser?.close()
  try {
    process.kill(-server.pid)
  } catch {
    /* già chiuso */
  }
}
