<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { backupFileName, download, exportEncrypted, importEncrypted } from '../backup/backup'
import type { FileKey } from '../diary/db'
import { model } from '../field/model'
import { downloadMapFile, formatBytes, importMapFile, mapFiles, removeMapFile } from '../map/mapFiles'
import { fetchPublishedMaps, publishedUrl, type PublishedMap } from '../map/published'
import { calendar } from '../rules/calendar'
import { settings } from '../settings/settings'

const msg = ref<Record<string, { kind: 'ok' | 'bad'; text: string } | null>>({})
const busy = ref<string | null>(null)
const scoreUrl = ref('')

const persisted = ref<boolean | null>(null)
const usage = ref<string>('')

async function refreshStorage() {
  if (!navigator.storage) return
  persisted.value = (await navigator.storage.persisted?.()) ?? null
  const est = await navigator.storage.estimate?.()
  if (est?.usage !== undefined) usage.value = `${formatBytes(est.usage)} usati${est.quota ? ` su ${formatBytes(est.quota)}` : ''}`
}

const published = ref<PublishedMap[]>([])

onMounted(async () => {
  await refreshStorage()
  published.value = await fetchPublishedMaps()
})

function fromPublished(m: PublishedMap) {
  void run('score', async () => {
    const info = await downloadMapFile('score', new URL(publishedUrl(m.file), location.href).href)
    return `Scaricata ${m.title} (${formatBytes(info.size)}).`
  })
}

async function persist() {
  persisted.value = (await navigator.storage?.persist?.()) ?? false
}

async function run(key: string, fn: () => Promise<string>) {
  busy.value = key
  msg.value[key] = null
  try {
    msg.value[key] = { kind: 'ok', text: await fn() }
  } catch (e) {
    msg.value[key] = { kind: 'bad', text: (e as Error).message }
  } finally {
    busy.value = null
    await refreshStorage()
  }
}

function onMapFile(key: FileKey, e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  void run(key, async () => {
    const info = await importMapFile(key, file, file.name)
    input.value = ''
    return `Importato ${info.name} (${formatBytes(info.size)}).`
  })
}

function fromUrl() {
  void run('score', async () => {
    const info = await downloadMapFile('score', scoreUrl.value.trim())
    return `Scaricato ${info.name} (${formatBytes(info.size)}).`
  })
}

const meta = (key: FileKey, k: string) => {
  const v = mapFiles[key]?.meta?.[k]
  return typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean' ? String(v) : null
}

const pass1 = ref('')
const pass2 = ref('')

function doExport() {
  void run('export', async () => {
    if (pass1.value !== pass2.value) throw new Error('Le due passphrase non coincidono.')
    const blob = await exportEncrypted(pass1.value)
    download(blob, backupFileName())
    pass1.value = pass2.value = ''
    return 'Backup cifrato scaricato. Senza passphrase non si apre: segnatela.'
  })
}

const importFile = ref<File | null>(null)
const importPass = ref('')
const importMode = ref<'merge' | 'replace'>('merge')

function doImport() {
  void run('import', async () => {
    if (!importFile.value) throw new Error('Scegli un file.')
    if (importMode.value === 'replace' && !confirm('Sostituire tutto il diario con il backup?')) throw new Error('Annullato.')
    const res = await importEncrypted(importFile.value, importPass.value, importMode.value)
    importPass.value = ''
    return `Importati: ${res.counts.outings} uscite, ${res.counts.finds} ritrovamenti, ${res.counts.spots} spot, ${res.counts.assessments} valutazioni.`
  })
}
</script>

<template>
  <div class="page">
    <h1>Altro</h1>

    <section class="card">
      <h2>Io e il cane</h2>
      <label class="field">
        <span>Zona del calendario</span>
        <select v-model="settings.zone">
          <option v-for="z in calendar.zones" :key="z.id" :value="z.id">{{ z.label }}</option>
        </select>
      </label>
      <p class="small muted">{{ calendar.zonesNote }}</p>
      <label class="field">
        <span>Nome del cane</span>
        <input v-model="settings.dog" placeholder="La Lagotto in arrivo a gennaio" />
      </label>
      <label class="field">
        <span>Numero del tesserino</span>
        <input v-model="settings.licenseNumber" />
      </label>
      <label class="row">
        <input v-model="settings.wakeLock" type="checkbox" style="width: auto; min-height: 0" />
        <span>Schermo acceso durante le uscite (traccia più affidabile, più batteria)</span>
      </label>
    </section>

    <section class="card">
      <h2>Mappa di idoneità</h2>
      <template v-if="mapFiles.score">
        <p>
          <strong>{{ mapFiles.score.name }}</strong> · {{ formatBytes(mapFiles.score.size) }}
          <br />
          <span class="small muted">
            modello {{ meta('score', 'model') ?? '?' }} · generata {{ meta('score', 'built') ?? '?' }} · zoom {{ mapFiles.score.header.minZoom }}-{{ mapFiles.score.header.maxZoom }}
          </span>
        </p>
        <p v-if="meta('score', 'model') && meta('score', 'model') !== model.id" class="banner warn small">
          Il file è stato generato con il modello {{ meta('score', 'model') }}, l'app usa {{ model.id }}.
        </p>
        <p v-if="mapFiles.score.meta?.synthetic" class="banner bad small">Dati SINTETICI di test: non usarla per cercare.</p>
        <p v-if="meta('score', 'warning')" class="banner warn small">{{ meta('score', 'warning') }}</p>
        <p v-if="meta('score', 'aoi_note')" class="small muted">{{ meta('score', 'aoi_note') }}</p>
        <p v-if="meta('score', 'attribution')" class="small muted">{{ meta('score', 'attribution') }}</p>
        <button class="danger" @click="removeMapFile('score')">Rimuovi</button>
      </template>
      <p v-else class="small muted">Nessuna. Il file `.pmtiles` lo genera la pipeline (cartella pipeline/ del repo).</p>
      <div v-if="published.length" class="stack" style="margin-top: 10px">
        <div v-for="m in published" :key="m.file" class="row spread" style="flex-wrap: nowrap">
          <div>
            <strong>{{ m.title }}</strong>
            <div class="small muted">{{ formatBytes(m.size) }} · modello {{ m.model }} · {{ m.built.slice(0, 10) }}{{ m.warning ? ' · in bozza' : '' }}</div>
          </div>
          <button class="primary" :disabled="busy === 'score'" @click="fromPublished(m)">Scarica</button>
        </div>
      </div>
      <label class="field" style="margin-top: 10px">
        <span>Importa file PMTiles</span>
        <input type="file" accept=".pmtiles" data-testid="score-file" :disabled="busy === 'score'" @change="onMapFile('score', $event)" />
      </label>
      <div class="row" style="flex-wrap: nowrap">
        <input v-model="scoreUrl" placeholder="oppure URL, es. dal server di casa" />
        <button :disabled="!scoreUrl || busy === 'score'" @click="fromUrl">Scarica</button>
      </div>
      <p v-if="msg.score" class="banner small" :class="msg.score.kind" style="margin-top: 10px">{{ msg.score.text }}</p>
    </section>

    <section class="card">
      <h2>Basemap offline</h2>
      <p class="small">
        Le basemap online (OpenTopoMap, OpenStreetMap) vedono quali tessere chiedi, quindi l'area che guardi. Con la basemap offline nessuno sa dove sei.
        In bosco funziona solo quella offline o le tessere già viste.
      </p>
      <p class="small muted">
        Si prepara una volta dal computer con
        <code>pmtiles extract https://build.protomaps.com/AAAAMMGG.pmtiles parma.pmtiles --bbox=…</code>
        (go-pmtiles), poi si importa qui.
      </p>
      <template v-if="mapFiles.basemap">
        <p><strong>{{ mapFiles.basemap.name }}</strong> · {{ formatBytes(mapFiles.basemap.size) }}</p>
        <button class="danger" @click="removeMapFile('basemap')">Rimuovi</button>
      </template>
      <label class="field" style="margin-top: 10px">
        <span>Importa basemap PMTiles</span>
        <input type="file" accept=".pmtiles" :disabled="busy === 'basemap'" @change="onMapFile('basemap', $event)" />
      </label>
      <label class="field">
        <span>Sfondo in uso</span>
        <select v-model="settings.basemap">
          <option value="opentopomap">OpenTopoMap (online)</option>
          <option value="osm">OpenStreetMap (online)</option>
          <option value="offline">Offline</option>
        </select>
      </label>
      <p v-if="msg.basemap" class="banner small" :class="msg.basemap.kind">{{ msg.basemap.text }}</p>
    </section>

    <section class="card">
      <h2>Backup cifrato</h2>
      <p class="small">Uscite, ritrovamenti (con foto), spot e valutazioni in un file cifrato con la tua passphrase. Le mappe non entrano: si rigenerano.</p>
      <label class="field">
        <span>Passphrase (almeno 8 caratteri)</span>
        <input v-model="pass1" type="password" autocomplete="new-password" />
      </label>
      <label class="field">
        <span>Ripeti</span>
        <input v-model="pass2" type="password" autocomplete="new-password" />
      </label>
      <button class="primary" :disabled="busy === 'export' || pass1.length < 8" @click="doExport">Esporta backup</button>
      <p v-if="msg.export" class="banner small" :class="msg.export.kind" style="margin-top: 10px">{{ msg.export.text }}</p>

      <h3 style="margin-top: 18px">Ripristina</h3>
      <label class="field">
        <span>File .fiuto</span>
        <input type="file" accept=".fiuto,application/json" @change="importFile = ($event.target as HTMLInputElement).files?.[0] ?? null" />
      </label>
      <label class="field">
        <span>Passphrase</span>
        <input v-model="importPass" type="password" autocomplete="current-password" />
      </label>
      <div class="chips" style="margin-bottom: 10px">
        <button class="chip" :class="{ on: importMode === 'merge' }" @click="importMode = 'merge'">Unisci</button>
        <button class="chip" :class="{ on: importMode === 'replace' }" @click="importMode = 'replace'">Sostituisci tutto</button>
      </div>
      <button :disabled="busy === 'import' || !importFile || !importPass" @click="doImport">Ripristina</button>
      <p v-if="msg.import" class="banner small" :class="msg.import.kind" style="margin-top: 10px">{{ msg.import.text }}</p>
    </section>

    <section class="card">
      <h2>Spazio sul telefono</h2>
      <p class="small">{{ usage || 'Stima non disponibile.' }}</p>
      <p class="small">
        Archiviazione persistente:
        <strong>{{ persisted === null ? 'non supportata' : persisted ? 'sì' : 'no' }}</strong>.
        Senza, il browser può cancellare i dati se lo spazio scarseggia.
      </p>
      <button v-if="persisted === false" @click="persist">Chiedi archiviazione persistente</button>
    </section>

    <section class="card">
      <RouterLink to="/regole">Regole, calendario e fonti →</RouterLink>
      <p class="small muted" style="margin-top: 8px">fiuto · tutto resta su questo dispositivo. Niente account, niente server, niente telemetria.</p>
    </section>
  </div>
</template>
