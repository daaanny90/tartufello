// Copia un PMTiles della pipeline in public/mappe/ e aggiorna l'elenco che l'app mostra in Altro.
// Uso: node scripts/publish-map.mjs <file.pmtiles> <id> "<titolo>"
import { copyFile, mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import { FileSource, PMTiles } from 'pmtiles'

const [src, id, title] = process.argv.slice(2)
if (!src || !id || !title) {
  console.error('uso: node scripts/publish-map.mjs <file.pmtiles> <id> "<titolo>"')
  process.exit(1)
}
const dir = new URL('../public/mappe/', import.meta.url)
await mkdir(dir, { recursive: true })
const meta = await new PMTiles(new FileSource(new File([await readFile(src)], `${id}.pmtiles`))).getMetadata()
if (meta.synthetic) {
  console.error('questo file è SINTETICO: non si pubblica')
  process.exit(1)
}
const file = `${id}.pmtiles`
await copyFile(src, new URL(file, dir))
const indexUrl = new URL('index.json', dir)
let index = { maps: [] }
try {
  index = JSON.parse(await readFile(indexUrl, 'utf8'))
} catch {
  /* primo file */
}
const entry = {
  file,
  title,
  model: meta.model ?? '?',
  built: meta.built ?? '?',
  size: (await stat(new URL(file, dir))).size,
  ...(meta.warning ? { warning: meta.warning } : {}),
}
index.maps = [...index.maps.filter((m) => m.file !== file), entry]
await writeFile(indexUrl, JSON.stringify(index, null, 2) + '\n')
console.log(`pubblicata ${file} (${entry.size} byte, modello ${entry.model})`)
