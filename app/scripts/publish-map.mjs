// Copia un PMTiles della pipeline in public/mappe/ e aggiorna l'elenco che l'app mostra in Altro.
// Uso: node scripts/publish-map.mjs <file.pmtiles> <id> "<titolo>" ["<zona>"]
// Il tipo (idoneità, mappa di base, rilievo) si ricava dal file; i file della stessa zona si scaricano insieme.
import { copyFile, mkdir, readFile, stat, writeFile } from 'node:fs/promises'
import { FileSource, PMTiles, TileType } from 'pmtiles'

const [src, id, title, area] = process.argv.slice(2)
if (!src || !id || !title) {
  console.error('uso: node scripts/publish-map.mjs <file.pmtiles> <id> "<titolo>" ["<zona>"]')
  process.exit(1)
}
const dir = new URL('../public/mappe/', import.meta.url)
await mkdir(dir, { recursive: true })
const pm = new PMTiles(new FileSource(new File([await readFile(src)], `${id}.pmtiles`)))
const meta = await pm.getMetadata()
const header = await pm.getHeader()
const layers = (meta.vector_layers ?? []).map((l) => l.id)
const kind = header.tileType !== TileType.Mvt ? 'rilievo' : layers.includes('vth') ? 'score' : 'basemap'
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
  kind,
  ...(area ? { area } : {}),
  ...(meta.model ? { model: meta.model } : {}),
  built: meta.built ?? '?',
  size: (await stat(new URL(file, dir))).size,
  ...(meta.warning ? { warning: meta.warning } : {}),
}
index.maps = [...index.maps.filter((m) => m.file !== file), entry]
await writeFile(indexUrl, JSON.stringify(index, null, 2) + '\n')
console.log(`pubblicata ${file}: ${kind}, ${entry.size} byte${area ? `, zona ${area}` : ''}`)
