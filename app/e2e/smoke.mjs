// Smoke test end-to-end sul build di produzione, con Chromium locale e GPS simulato.
// Uso: npm run build && npm run e2e   (SCREENSHOTS=dir per salvare le schermate altrove)
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const root = fileURLToPath(new URL('..', import.meta.url))
const fixture = fileURLToPath(new URL('./fixtures/synthetic-vth.pmtiles', import.meta.url))
const shots = process.env.SCREENSHOTS ?? fileURLToPath(new URL('./screenshots', import.meta.url))
mkdirSync(shots, { recursive: true })

const PORT = 4173
const BASE = `http://localhost:${PORT}`
const server = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], { cwd: root, stdio: 'ignore' })

async function waitForServer() {
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch(BASE)).ok) return
    } catch {
      /* non ancora su */
    }
    await new Promise((r) => setTimeout(r, 200))
  }
  throw new Error('vite preview non parte')
}

const errors = []
let step = ''
const check = (cond, msg) => {
  if (!cond) throw new Error(`[${step}] ${msg}`)
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  })
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    geolocation: { latitude: 44.6505, longitude: 10.0505, accuracy: 8 },
    permissions: ['geolocation'],
    acceptDownloads: true,
    serviceWorkers: 'block',
    locale: 'it-IT',
    timezoneId: 'Europe/Rome',
  })
  const page = await context.newPage()
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    const t = m.text()
    // Le tessere online non sono raggiungibili da qui: errori di rete attesi.
    if (m.type() === 'error' && !/Failed to load resource|tile\.|AJAXError|Failed to fetch/.test(t)) errors.push(`console: ${t}`)
  })
  const shot = (name) => page.screenshot({ path: `${shots}/${name}.png` })

  step = 'oggi'
  await page.goto(BASE)
  await page.getByText('Tartufo nero (T. aestivum / uncinatum)').waitFor()
  await shot('01-oggi')

  const hasFixture = existsSync(fixture)
  step = 'import mappa'
  if (hasFixture) {
    await page.goto(`${BASE}/impostazioni`)
    await page.setInputFiles('[data-testid=score-file]', fixture)
    await page.getByText(/^Importato /).waitFor()
    await shot('02-impostazioni')
  } else {
    console.warn('fixture sintetica assente: salto la parte mappa con dati')
  }

  step = 'mappa'
  await page.goto(`${BASE}/mappa?lon=10.05&lat=44.65&z=13`)
  await page.locator('[data-testid=map] canvas').waitFor()
  await page.waitForTimeout(2500)
  await shot('03-mappa')
  const box = await page.locator('[data-testid=map]').boundingBox()
  // Un po' sopra il centro: nella fixture il centro cade tra due poligoni.
  await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.35)
  await page.locator('[data-testid=sheet]').waitFor()
  if (hasFixture) await page.locator('[data-testid=sheet]').getByText(/parametri/).first().waitFor()
  await shot('04-mappa-punto')
  await page.getByPlaceholder('Nome (facoltativo)').fill('Fragno di prova')
  await page.getByRole('button', { name: 'Salva spot' }).click()
  await page.getByRole('button', { name: 'Valuta', exact: true }).click()

  step = 'campo'
  await page.locator('[data-testid=summary]').waitFor()
  await page.getByRole('button', { name: /Copertura aperta/ }).click()
  await page.getByRole('button', { name: /Latifoglie fresche/ }).click()
  await page.locator('tr', { hasText: 'Carpino nero' }).locator('input').first().check()
  await page.locator('tr', { hasText: 'Roverella' }).locator('input').first().check()
  await page.locator('tr', { hasText: 'Nocciolo' }).locator('input').nth(1).check()
  await page.getByRole('button', { name: 'Epipactis' }).click()
  await page.getByPlaceholder('es. 7,4').fill('7,6')
  await page.getByPlaceholder('es. 7,4').blur()
  const summary = await page.locator('[data-testid=summary]').innerText()
  check(/\/ 36/.test(summary), `punteggio non mostrato: ${summary}`)
  await shot('05-campo')
  await page.getByRole('button', { name: 'Salva valutazione' }).click()
  await page.getByRole('heading', { name: 'Fragno di prova' }).waitFor()
  await shot('06-spot')

  step = 'uscita'
  await page.goto(BASE)
  await page.getByRole('button', { name: 'Inizia uscita' }).click()
  await page.getByText('Uscita in corso').first().waitFor()
  for (let i = 1; i <= 6; i++) {
    await context.setGeolocation({ latitude: 44.6505 + i * 0.0003, longitude: 10.0505 + i * 0.0002, accuracy: 6 })
    await page.waitForTimeout(400)
  }
  await page.getByRole('button', { name: 'Ritrovamento' }).click()
  await page.getByText(/±\d+ m/).waitFor()
  await page.locator('label', { hasText: 'Grammi' }).locator('input').fill('38')
  await page.getByRole('button', { name: 'Salva' }).click()
  await page.getByText('38 g').first().waitFor()
  await shot('07-uscita')
  await page.getByRole('button', { name: 'Termina uscita' }).click()
  await page.getByText('1 trovati').first().waitFor()

  step = 'diario'
  await page.goto(`${BASE}/diario`)
  await page.getByText('1 trovati').waitFor()
  await shot('08-diario')

  step = 'backup'
  await page.goto(`${BASE}/impostazioni`)
  await page.locator('label', { hasText: 'Passphrase (almeno 8 caratteri)' }).locator('input').fill('lagotto-2027')
  await page.locator('label', { hasText: 'Ripeti' }).locator('input').fill('lagotto-2027')
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Esporta backup' }).click()])
  const file = `${shots}/backup.fiuto`
  await download.saveAs(file)
  await page.locator('label', { hasText: 'File .fiuto' }).locator('input').setInputFiles(file)
  await page.locator('label', { hasText: /^Passphrase$/ }).locator('input').fill('lagotto-2027')
  await page.getByRole('button', { name: 'Ripristina' }).click()
  await page.getByText(/Importati: 1 uscite, 1 ritrovamenti, 1 spot, 1 valutazioni/).waitFor()

  step = 'regole'
  await page.goto(`${BASE}/regole`)
  await page.getByText('Sospensione totale').waitFor()

  check(errors.length === 0, `errori in pagina:\n${errors.join('\n')}`)
  console.log(`smoke ok${hasFixture ? '' : ' (senza fixture)'} · schermate in ${shots}`)
} catch (e) {
  console.error(e.message)
  if (errors.length) console.error(errors.join('\n'))
  process.exitCode = 1
} finally {
  await browser?.close()
  server.kill()
}
