import { FileSource, PMTiles, Protocol, TileType, type Header } from 'pmtiles'
import { reactive } from 'vue'
import { db, nowIso, type FileKey, type StoredFile } from '../diary/db'

/**
 * I file mappa (score VTH e basemap offline) stanno in IndexedDB come Blob
 * e si leggono a pezzi con FileSource: niente server, funziona offline.
 */

export const protocol = new Protocol({ metadata: true })

const instances = new Map<FileKey, PMTiles>()

export interface FileInfo {
  name: string
  size: number
  importedAt: string
  header: Header
  meta: Record<string, unknown>
}

export const mapFiles = reactive<Record<FileKey, FileInfo | null>>({ score: null, basemap: null, rilievo: null })

/** Basemap regionale costruita dalla pipeline (curve di livello, sentieri...) invece che Protomaps. */
export const isFiutoBasemap = (info: FileInfo | null) =>
  !!info && (info.meta.fiuto_basemap === true || (info.meta.vector_layers as { id: string }[] | undefined)?.some((l) => l.id === 'contours') === true)

const isRaster = (h: Header) => h.tileType !== TileType.Mvt && h.tileType !== TileType.Unknown

export const sourceUrl = (key: FileKey) => `pmtiles://fiuto-${key}`

async function read(file: StoredFile): Promise<{ pm: PMTiles; info: FileInfo }> {
  const pm = new PMTiles(new FileSource(new File([file.blob], `fiuto-${file.key}`)))
  const header = await pm.getHeader()
  const meta = ((await pm.getMetadata()) ?? {}) as Record<string, unknown>
  return { pm, info: { name: file.name, size: file.size, importedAt: file.importedAt, header, meta } }
}

function register(key: FileKey, pm: PMTiles) {
  instances.set(key, pm)
  protocol.add(pm)
}

async function open(file: StoredFile): Promise<FileInfo> {
  const { pm, info } = await read(file)
  register(file.key, pm)
  return info
}

export function pmtiles(key: FileKey): PMTiles | undefined {
  return instances.get(key)
}

/** Carica all'avvio i file già importati. */
export async function loadMapFiles(): Promise<void> {
  for (const f of await db.files.toArray()) {
    try {
      mapFiles[f.key] = await open(f)
    } catch (e) {
      console.error(`File mappa ${f.key} illeggibile`, e)
      mapFiles[f.key] = null
    }
  }
}

const MAGIC = 'PMTiles'

async function checkPmtiles(blob: Blob): Promise<void> {
  const head = new Uint8Array(await blob.slice(0, 8).arrayBuffer())
  const magic = new TextDecoder().decode(head.subarray(0, 7))
  if (magic !== MAGIC) throw new Error('Non è un file PMTiles.')
  if (head[7] !== 3) throw new Error(`PMTiles versione ${head[7]} non supportata (serve la 3).`)
}

export async function importMapFile(key: FileKey, blob: Blob, name: string): Promise<FileInfo> {
  await checkPmtiles(blob)
  const stored: StoredFile = { key, name, blob, size: blob.size, importedAt: nowIso() }
  // Prima si controlla, poi si registra: un file sbagliato non deve rimpiazzare quello buono.
  const { pm, info } = await read(stored)
  if (key === 'rilievo' && !isRaster(info.header)) throw new Error('Il rilievo deve essere un PMTiles raster (immagini).')
  if (key === 'basemap' && info.header.tileType !== TileType.Mvt) throw new Error('La basemap deve essere un PMTiles vettoriale.')
  if (key === 'score') {
    const layers = (info.meta.vector_layers as { id: string }[] | undefined)?.map((l) => l.id) ?? []
    if (!layers.includes('vth')) throw new Error('Il file non contiene il layer "vth" della pipeline.')
  }
  await db.files.put(stored)
  register(key, pm)
  mapFiles[key] = info
  return info
}

export async function downloadMapFile(key: FileKey, url: string): Promise<FileInfo> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Scaricamento fallito: HTTP ${res.status}`)
  const blob = await res.blob()
  return importMapFile(key, blob, url.split('/').pop() || key)
}

export async function removeMapFile(key: FileKey): Promise<void> {
  await db.files.delete(key)
  instances.delete(key)
  mapFiles[key] = null
}

export function formatBytes(n: number): string {
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} kB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
