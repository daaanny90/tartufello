import { createApp } from 'vue'
import 'maplibre-gl/dist/maplibre-gl.css'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { loadSettings } from './settings/settings'
import { loadMapFiles } from './map/mapFiles'
import { resumeOuting } from './diary/outings'
import { watchDanger } from './diary/danger'
import { db } from './diary/db'
import { ensurePersisted } from './lib/storage'

async function boot() {
  await loadSettings()
  await loadMapFiles()
  createApp(App).use(router).mount('#app')
  watchDanger()
  await resumeOuting()
  // Con dati dentro, si chiede subito di non farli cancellare al browser.
  if ((await db.outings.count()) + (await db.spots.count()) > 0) void ensurePersisted()
}

void boot()
