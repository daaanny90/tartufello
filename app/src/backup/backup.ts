import { db, USER_TABLES, type FiutoDb, type UserTable } from '../diary/db'
import { decrypt, encrypt, fromBase64, toBase64, type Envelope } from './crypto'

/** Marcatore per i Blob (foto) serializzati in JSON. */
interface BlobRef {
  __blob: true
  type: string
  data: string
}

const isBlobRef = (v: unknown): v is BlobRef => typeof v === 'object' && v !== null && (v as BlobRef).__blob === true

async function serialize(value: unknown): Promise<unknown> {
  if (value instanceof Blob) {
    return { __blob: true, type: value.type, data: toBase64(new Uint8Array(await value.arrayBuffer())) } satisfies BlobRef
  }
  if (Array.isArray(value)) return Promise.all(value.map(serialize))
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value)) out[k] = await serialize(v)
    return out
  }
  return value
}

function deserialize(value: unknown): unknown {
  if (isBlobRef(value)) return new Blob([fromBase64(value.data)], { type: value.type })
  if (Array.isArray(value)) return value.map(deserialize)
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value)) out[k] = deserialize(v)
    return out
  }
  return value
}

export interface Snapshot {
  app: 'fiuto'
  schema: 1
  exportedAt: string
  tables: Record<UserTable, unknown[]>
}

export async function snapshot(database: FiutoDb = db): Promise<Snapshot> {
  const tables = {} as Record<UserTable, unknown[]>
  for (const t of USER_TABLES) tables[t] = (await serialize(await database.table(t).toArray())) as unknown[]
  return { app: 'fiuto', schema: 1, exportedAt: new Date().toISOString(), tables }
}

export async function exportEncrypted(passphrase: string, database: FiutoDb = db): Promise<Blob> {
  const env = await encrypt(JSON.stringify(await snapshot(database)), passphrase)
  return new Blob([JSON.stringify(env)], { type: 'application/json' })
}

export function backupFileName(d = new Date()): string {
  return `fiuto-backup-${d.toISOString().slice(0, 10)}.fiuto`
}

export interface ImportResult {
  counts: Record<UserTable, number>
}

/**
 * replace: svuota e sostituisce. merge: aggiunge e sovrascrive per id, non cancella nulla.
 */
export async function importEncrypted(
  file: Blob,
  passphrase: string,
  mode: 'merge' | 'replace',
  database: FiutoDb = db,
): Promise<ImportResult> {
  let env: Envelope
  try {
    env = JSON.parse(await file.text())
  } catch {
    throw new Error('Il file non è un backup di fiuto.')
  }
  const snap = JSON.parse(await decrypt(env, passphrase)) as Snapshot
  if (snap.app !== 'fiuto' || snap.schema !== 1) throw new Error('Versione del backup non supportata.')
  const counts = {} as Record<UserTable, number>
  await database.transaction('rw', USER_TABLES.map((t) => database.table(t)), async () => {
    for (const t of USER_TABLES) {
      const rows = (snap.tables[t] ?? []).map(deserialize)
      if (mode === 'replace') await database.table(t).clear()
      await database.table(t).bulkPut(rows)
      counts[t] = rows.length
    }
  })
  return { counts }
}

export function download(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
