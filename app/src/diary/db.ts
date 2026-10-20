import Dexie, { type EntityTable } from 'dexie'
import type { Point, Polygon } from 'geojson'
import type { FieldInputs, RemotePoints } from '../field/vth'

export type Species = 'aestivum' | 'uncinatum' | 'magnatum' | 'borchii' | 'brumale' | 'other'

export const SPECIES_LABELS: Record<Species, string> = {
  uncinatum: 'Uncinatum (nero di Fragno)',
  aestivum: 'Aestivum (scorzone estivo)',
  magnatum: 'Magnatum (bianco)',
  borchii: 'Borchii (bianchetto)',
  brumale: 'Brumale',
  other: 'Altro',
}

/** Punto o area di interesse. "riservato" = tartufaia coltivata/controllata con tabella: off-limits. */
export interface Spot {
  id: string
  name: string
  kind: 'interesse' | 'riservato'
  geom: Point | Polygon
  /** Punti remoti letti dalla mappa al momento del salvataggio. */
  remote?: { score?: number; n?: number; points: RemotePoints }
  notes?: string
  createdAt: string
}

export interface FieldAssessment {
  id: string
  spotId?: string
  date: string
  position?: [number, number]
  modelId: string
  inputs: FieldInputs
  remote: RemotePoints
  result: { pts: number; max: number; score36: number | null; classId: string | null; observed: number; estimated: number }
  notes?: string
}

export interface TrackPoint {
  lon: number
  lat: number
  t: number
  acc?: number
  alt?: number | null
}

export type OutingKind = 'cerca' | 'sopralluogo'

/** Anche i giri a vuoto: sono dati. */
export interface Outing {
  id: string
  /** 'sopralluogo' = giro senza cane per valutare posti; assente nei dati vecchi = 'cerca'. */
  kind?: OutingKind
  date: string
  endedAt?: string
  dog: string
  weather?: string
  notes?: string
  track: TrackPoint[]
  spotsVisited: string[]
}

export interface Find {
  id: string
  outingId: string
  date: string
  position: [number, number]
  species: Species
  grams?: number
  depthCm?: number
  hostNearby?: string
  photo?: Blob
  notes?: string
}

export type FileKey = 'score' | 'basemap'

export interface StoredFile {
  key: FileKey
  name: string
  blob: Blob
  size: number
  importedAt: string
  meta?: unknown
}

export interface Setting {
  key: string
  value: unknown
}

export class FiutoDb extends Dexie {
  spots!: EntityTable<Spot, 'id'>
  assessments!: EntityTable<FieldAssessment, 'id'>
  outings!: EntityTable<Outing, 'id'>
  finds!: EntityTable<Find, 'id'>
  files!: EntityTable<StoredFile, 'key'>
  settings!: EntityTable<Setting, 'key'>

  constructor(name = 'fiuto') {
    super(name)
    this.version(1).stores({
      spots: 'id, kind, createdAt',
      assessments: 'id, spotId, date',
      outings: 'id, date, endedAt',
      finds: 'id, outingId, date, species',
      files: 'key',
      settings: 'key',
    })
  }
}

export const db = new FiutoDb()

/** Tabelle con i dati dell'utente: finiscono nel backup. I file mappa no, si rigenerano. */
export const USER_TABLES = ['spots', 'assessments', 'outings', 'finds', 'settings'] as const
export type UserTable = (typeof USER_TABLES)[number]

export const newId = () => crypto.randomUUID()
export const nowIso = () => new Date().toISOString()
