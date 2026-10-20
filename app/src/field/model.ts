import modelData from '@model/vth-v2.json'

export interface NumericRule {
  gt?: number
  gte?: number
  lt?: number
  lte?: number
  points: number
}

export interface Category {
  id: string
  label: string
  points: number
}

export interface FizzLevel {
  id: string
  label: string
  faoRange: string
  points: number
}

export interface ParamDef {
  id: ParamId
  label: string
  kind: 'category' | 'numeric' | 'excluded' | 'hosts' | 'orchids' | 'insects'
  unit?: string
  remote: { available: boolean; max: number; from: string }
  field: boolean
  fieldNote?: string
  categories?: Category[]
  rules?: NumericRule[]
  fizzTest?: { note: string; levels: FizzLevel[] }
  excludedReason?: string
  genera?: string[]
  taxa?: string[]
}

export interface HostSpecies {
  id: string
  latin: string
  it: string
  hazel?: boolean
  group?: string
  note?: string
}

export interface VthClass {
  id: string
  label: string
  min36: number
  color: string
}

export type ParamId =
  | 'bedrock'
  | 'ph'
  | 'ca_exch'
  | 'caco3'
  | 'cn'
  | 'texture'
  | 'elevation'
  | 'forest_type'
  | 'forest_structure'
  | 'hosts'
  | 'orchids'
  | 'insects'

export interface VthModel {
  id: string
  title: string
  source: { citation: string; doi: string; license: string }
  maxPerParam: number
  maxTotal: number
  classes: VthClass[]
  field: { minParamsForClass: number; minParamsNote: string }
  remote: { minParams: number; minParamsNote: string; normalization: string }
  params: ParamDef[]
  hostSpecies: HostSpecies[]
  tiles: { layer: string }
}

export const model = modelData as unknown as VthModel

export const param = (id: ParamId): ParamDef => {
  const p = model.params.find((x) => x.id === id)
  if (!p) throw new Error(`Parametro sconosciuto: ${id}`)
  return p
}

/** Parametri con score remoto nel PMTiles, nell'ordine del contratto. */
export const REMOTE_PARAMS = model.params.filter((p) => p.remote.available).map((p) => p.id)
