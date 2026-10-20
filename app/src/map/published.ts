import type { FileKey } from '../diary/db'

/** Mappe pubblicate insieme all'app (public/mappe/), scaricabili con un tocco. */
export interface PublishedMap {
  file: string
  title: string
  /** Slot in cui finisce: idoneità, basemap vettoriale o rilievo. Assente nei primi file = score. */
  kind?: FileKey
  /** Zona a cui appartiene (es. "Val Baganza"): i file di una zona si scaricano insieme. */
  area?: string
  model?: string
  built: string
  size: number
  warning?: string
}

export interface PublishedArea {
  area: string
  maps: PublishedMap[]
  size: number
}

export const publishedUrl = (file: string) => `${import.meta.env.BASE_URL}mappe/${file}`

export const kindOf = (m: PublishedMap): FileKey => m.kind ?? 'score'

export const KIND_LABEL: Record<FileKey, string> = {
  score: 'idoneità',
  basemap: 'mappa di base',
  rilievo: 'rilievo',
}

export function groupByArea(maps: PublishedMap[]): PublishedArea[] {
  const byArea = new Map<string, PublishedMap[]>()
  for (const m of maps) {
    const a = m.area ?? m.title
    byArea.set(a, [...(byArea.get(a) ?? []), m])
  }
  const order: FileKey[] = ['score', 'basemap', 'rilievo']
  return [...byArea].map(([area, list]) => ({
    area,
    maps: list.sort((x, y) => order.indexOf(kindOf(x)) - order.indexOf(kindOf(y))),
    size: list.reduce((s, m) => s + m.size, 0),
  }))
}

export async function fetchPublishedMaps(): Promise<PublishedMap[]> {
  try {
    const res = await fetch(publishedUrl('index.json'))
    if (!res.ok) return []
    const data = (await res.json()) as { maps?: PublishedMap[] }
    return data.maps ?? []
  } catch {
    // Offline o nessuna mappa pubblicata: si importa a mano.
    return []
  }
}
