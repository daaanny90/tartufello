import { reactive, watch } from 'vue'
import { db } from '../diary/db'
import type { ZoneId } from '../rules/calendar'

export type BasemapId = 'opentopomap' | 'osm' | 'offline'

export interface Settings {
  zone: ZoneId
  dog: string
  basemap: BasemapId
  licenseNumber: string
  wakeLock: boolean
  /** ISO dell'ultimo backup esportato, '' se mai. */
  lastBackupAt: string
}

const DEFAULTS: Settings = {
  zone: 'collina',
  dog: '',
  basemap: 'opentopomap',
  licenseNumber: '',
  wakeLock: true,
  lastBackupAt: '',
}

export const settings = reactive<Settings>({ ...DEFAULTS })

let loaded = false

export async function loadSettings(): Promise<void> {
  const rows = await db.settings.toArray()
  for (const r of rows) {
    if (r.key in DEFAULTS) (settings as Record<string, unknown>)[r.key] = r.value
  }
  if (!loaded) {
    loaded = true
    watch(
      () => ({ ...settings }),
      async (s) => {
        await db.settings.bulkPut(Object.entries(s).map(([key, value]) => ({ key, value })))
      },
      { deep: true },
    )
  }
}
