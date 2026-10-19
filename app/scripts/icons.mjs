// Rasterizza public/icon.svg nelle icone PNG della PWA usando il Chromium locale.
import { readFile, writeFile } from 'node:fs/promises'
import { chromium } from 'playwright-core'

const svg = await readFile(new URL('../public/icon.svg', import.meta.url), 'utf8')
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH ?? '/opt/pw-browsers/chromium' })
for (const size of [192, 512]) {
  const page = await browser.newPage({ viewport: { width: size, height: size } })
  await page.setContent(`<html><body style="margin:0">${svg.replace('<svg ', `<svg width="${size}" height="${size}" `)}</body></html>`)
  await writeFile(new URL(`../public/icon-${size}.png`, import.meta.url), await page.screenshot({ omitBackground: false }))
  await page.close()
}
await browser.close()
console.log('icone generate')
