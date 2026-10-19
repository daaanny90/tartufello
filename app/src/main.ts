import { createApp } from 'vue'
import 'maplibre-gl/dist/maplibre-gl.css'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { loadSettings } from './settings/settings'
import { loadMapFiles } from './map/mapFiles'
import { resumeOuting } from './diary/outings'

async function boot() {
  await loadSettings()
  await loadMapFiles()
  createApp(App).use(router).mount('#app')
  await resumeOuting()
}

void boot()
