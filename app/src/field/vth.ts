import { model, param, type NumericRule, type ParamId, type VthClass } from './model'

/** Quello che si osserva o si misura sul posto. undefined = non valutato. */
export interface FieldInputs {
  bedrock?: string
  ph?: number
  caExch?: number
  caco3Pct?: number
  caco3Fizz?: string
  texture?: string
  elevation?: number
  forestType?: string
  forestStructure?: string
  hosts?: { tree: string[]; lower: string[] }
  orchids?: { genera: string[]; speciesCount: number }
  insects?: string[]
}

/** Punti dei parametri remoti nel punto, come nelle proprietà del PMTiles. */
export type RemotePoints = Partial<Record<ParamId, number>>

export type Origin = 'campo' | 'mappa' | 'mancante' | 'escluso'

export interface ParamResult {
  id: ParamId
  label: string
  points: number | null
  max: number
  origin: Origin
  detail?: string
}

export interface Assessment {
  params: ParamResult[]
  pts: number
  max: number
  /** Punteggio riportato sulla scala VTH a 36 punti. null se non c'è nessun parametro. */
  score36: number | null
  vthClass: VthClass | null
  /** Troppi pochi parametri per fidarsi della classe. */
  provisional: boolean
  observed: number
  estimated: number
  missing: number
}

export function matchRule(value: number, rules: NumericRule[]): number {
  for (const r of rules) {
    if (r.gt !== undefined && !(value > r.gt)) continue
    if (r.gte !== undefined && !(value >= r.gte)) continue
    if (r.lt !== undefined && !(value < r.lt)) continue
    if (r.lte !== undefined && !(value <= r.lte)) continue
    return r.points
  }
  throw new Error(`Nessuna regola per il valore ${value}`)
}

export function categoryPoints(id: ParamId, categoryId: string): number {
  const c = param(id).categories?.find((x) => x.id === categoryId)
  if (!c) throw new Error(`Categoria sconosciuta per ${id}: ${categoryId}`)
  return c.points
}

const HAZEL = new Set(model.hostSpecies.filter((h) => h.hazel).map((h) => h.id))

/**
 * Ospiti secondo VTH. Il nocciolo non conta tra le "più di 2 specie arboree":
 * la regola da 3 punti lo chiede in aggiunta.
 */
export function hostsPoints(hosts: { tree: string[]; lower: string[] }): number {
  const tree = new Set(hosts.tree)
  const lower = new Set(hosts.lower)
  const hazel = [...tree, ...lower].some((h) => HAZEL.has(h))
  const treeNoHazel = [...tree].filter((h) => !HAZEL.has(h))
  if (treeNoHazel.length > 2 && hazel) return 3
  if (tree.size >= 1 && lower.size >= 1) return 2
  if (tree.size + lower.size >= 1) return 1
  return 0
}

export function orchidsPoints(o: { speciesCount: number }): number {
  if (o.speciesCount > 1) return 3
  if (o.speciesCount === 1) return 2
  return 0
}

export function insectsPoints(taxa: string[]): number {
  return taxa.length > 0 ? 3 : 0
}

export function fizzPoints(levelId: string): number {
  const l = param('caco3').fizzTest?.levels.find((x) => x.id === levelId)
  if (!l) throw new Error(`Livello di effervescenza sconosciuto: ${levelId}`)
  return l.points
}

type FieldResult = { points: number; detail: string } | null

function fieldValue(id: ParamId, f: FieldInputs): FieldResult {
  const p = param(id)
  const label = (cat?: string) => p.categories?.find((c) => c.id === cat)?.label ?? cat ?? ''
  switch (id) {
    case 'bedrock':
      return f.bedrock ? { points: categoryPoints(id, f.bedrock), detail: label(f.bedrock) } : null
    case 'ph':
      return f.ph !== undefined ? { points: matchRule(f.ph, p.rules!), detail: `pH ${f.ph}` } : null
    case 'ca_exch':
      return f.caExch !== undefined ? { points: matchRule(f.caExch, p.rules!), detail: `${f.caExch} cmol+/kg` } : null
    case 'caco3':
      if (f.caco3Pct !== undefined) return { points: matchRule(f.caco3Pct, p.rules!), detail: `${f.caco3Pct}% (laboratorio)` }
      if (f.caco3Fizz) {
        const lvl = p.fizzTest!.levels.find((l) => l.id === f.caco3Fizz)
        return { points: fizzPoints(f.caco3Fizz), detail: `effervescenza: ${lvl?.label.toLowerCase()} (stima)` }
      }
      return null
    case 'texture':
      return f.texture ? { points: categoryPoints(id, f.texture), detail: label(f.texture) } : null
    case 'elevation':
      return f.elevation !== undefined
        ? { points: matchRule(f.elevation, p.rules!), detail: `${Math.round(f.elevation)} m` }
        : null
    case 'forest_type':
      return f.forestType ? { points: categoryPoints(id, f.forestType), detail: label(f.forestType) } : null
    case 'forest_structure':
      return f.forestStructure ? { points: categoryPoints(id, f.forestStructure), detail: label(f.forestStructure) } : null
    case 'hosts':
      return f.hosts
        ? { points: hostsPoints(f.hosts), detail: `${f.hosts.tree.length} arboree, ${f.hosts.lower.length} nel piano inferiore` }
        : null
    case 'orchids':
      return f.orchids
        ? { points: orchidsPoints(f.orchids), detail: f.orchids.speciesCount ? `${f.orchids.speciesCount} specie` : 'nessuna' }
        : null
    case 'insects':
      return f.insects ? { points: insectsPoints(f.insects), detail: f.insects.length ? f.insects.join(', ') : 'nessuno' } : null
    case 'cn':
      return null
  }
}

export function classFor(score36: number): VthClass {
  const sorted = [...model.classes].sort((a, b) => b.min36 - a.min36)
  return sorted.find((c) => score36 >= c.min36) ?? sorted[sorted.length - 1]
}

/**
 * Combina osservazioni sul posto e punti remoti della mappa.
 * Il campo vince sempre sulla mappa. Il totale è riportato a 36 sul massimo
 * effettivamente ottenibile con i parametri presenti (stessa logica dello score remoto).
 */
export function assess(field: FieldInputs, remote: RemotePoints = {}): Assessment {
  const params: ParamResult[] = model.params.map((p) => {
    if (p.kind === 'excluded') {
      return { id: p.id, label: p.label, points: null, max: 0, origin: 'escluso', detail: p.excludedReason }
    }
    const fv = fieldValue(p.id, field)
    if (fv) return { id: p.id, label: p.label, points: fv.points, max: model.maxPerParam, origin: 'campo', detail: fv.detail }
    const rv = remote[p.id]
    if (p.remote.available && rv !== undefined && rv !== null) {
      return { id: p.id, label: p.label, points: rv, max: p.remote.max, origin: 'mappa', detail: 'dalla mappa' }
    }
    return { id: p.id, label: p.label, points: null, max: 0, origin: 'mancante' }
  })
  const counted = params.filter((r) => r.points !== null)
  const pts = counted.reduce((s, r) => s + (r.points ?? 0), 0)
  const max = counted.reduce((s, r) => s + r.max, 0)
  const score36 = max > 0 ? (pts / max) * model.maxTotal : null
  return {
    params,
    pts,
    max,
    score36,
    vthClass: score36 === null ? null : classFor(score36),
    provisional: counted.length < model.field.minParamsForClass,
    observed: params.filter((r) => r.origin === 'campo').length,
    estimated: params.filter((r) => r.origin === 'mappa').length,
    missing: params.filter((r) => r.origin === 'mancante').length,
  }
}

/** Classe dello score remoto normalizzato (0..1), sulla stessa scala. */
export function remoteClass(score: number): VthClass {
  return classFor(score * model.maxTotal)
}
