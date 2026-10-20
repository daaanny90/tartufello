/** Mappe di idoneità pubblicate insieme all'app (public/mappe/), scaricabili con un tocco. */
export interface PublishedMap {
  file: string
  title: string
  model: string
  built: string
  size: number
  warning?: string
}

export const publishedUrl = (file: string) => `${import.meta.env.BASE_URL}mappe/${file}`

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
