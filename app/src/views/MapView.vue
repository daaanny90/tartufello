<script setup lang="ts">
import { addProtocol, Map as MlMap, removeProtocol, ScaleControl, setWorkerUrl, type GeoJSONSource, type MapMouseEvent } from 'maplibre-gl'
// MapLibre 6 cerca il worker accanto al proprio modulo: dopo il bundle va indicato a mano.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { liveQuery, type Subscription } from 'dexie'
import type { Feature, FeatureCollection } from 'geojson'
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { db, newId, nowIso, type Find, type Spot } from '../diary/db'
import { tracking } from '../diary/outings'
import { model, param, REMOTE_PARAMS, type ParamId } from '../field/model'
import { remoteClass } from '../field/vth'
import { acquireLocation, location } from '../lib/geolocation'
import { circle, formatCoord } from '../lib/geo'
import { plain } from '../lib/plain'
import { mapFiles, protocol, sourceUrl } from '../map/mapFiles'
import { toRemote, type RemoteAt } from '../map/remote'
import { baseStyle, FONT, scoreLayers, type ScoreView } from '../map/style'
import { settings } from '../settings/settings'

defineOptions({ name: 'MapView' })

const router = useRouter()
const route = useRoute()
const container = ref<HTMLDivElement>()
const map = shallowRef<MlMap>()

const VIEW_KEY = 'fiuto:map-view'
const DEFAULT_VIEW = { center: [10.05, 44.6] as [number, number], zoom: 10 }

function savedView() {
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_KEY) ?? 'null')
    if (v && Array.isArray(v.center) && typeof v.zoom === 'number') return v as typeof DEFAULT_VIEW
  } catch {
    /* vista salvata non leggibile: uso quella di default */
  }
  return DEFAULT_VIEW
}

const ui = reactive({
  layersOpen: false,
  follow: false,
  view: { kind: 'score' } as ScoreView,
  newSpotName: '',
})

interface Selection {
  lngLat: [number, number]
  remote: RemoteAt | null
  spot: Spot | null
}
const selection = ref<Selection | null>(null)

const spots = ref<Spot[]>([])
const finds = ref<Find[]>([])
const track = ref<[number, number][]>([])
const subs: Subscription[] = []

const synthetic = computed(() => mapFiles.score?.meta?.synthetic === true)
const metaText = (k: string) => {
  const v = mapFiles.score?.meta?.[k]
  return typeof v === 'string' && v.trim() ? v : null
}
const scoreWarning = computed(() => metaText('warning'))
const notesOpen = ref(false)
const offlineMissing = computed(() => settings.basemap === 'offline' && !mapFiles.basemap)

const paramOptions = computed(() =>
  REMOTE_PARAMS.map((id) => ({ id, label: param(id).label, max: param(id).remote.max })),
)

function fc(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features }
}

function setData(id: string, data: FeatureCollection) {
  const src = map.value?.getSource(id) as GeoJSONSource | undefined
  src?.setData(data)
}

function spotsData() {
  return fc(
    spots.value
      .filter((s) => s.geom.type === 'Point')
      .map((s) => ({ type: 'Feature', geometry: s.geom, properties: { id: s.id, name: s.name, kind: s.kind } })),
  )
}

function findsData() {
  return fc(finds.value.map((f) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: f.position }, properties: { id: f.id, species: f.species } })))
}

function trackData() {
  return fc(track.value.length > 1 ? [{ type: 'Feature', geometry: { type: 'LineString', coordinates: track.value }, properties: {} }] : [])
}

function meData() {
  const f = location.fix
  if (!f) return fc([])
  return fc([
    { type: 'Feature', geometry: { type: 'Polygon', coordinates: [circle([f.lon, f.lat], f.acc)] }, properties: { kind: 'acc' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [f.lon, f.lat] }, properties: { kind: 'dot' } },
  ])
}

function addScore(m: MlMap) {
  for (const l of ['vth-line', 'vth-fill', 'vth-nodata']) if (m.getLayer(l)) m.removeLayer(l)
  if (m.getSource('vth')) m.removeSource('vth')
  if (!mapFiles.score) return
  m.addSource('vth', { type: 'vector', url: sourceUrl('score') })
  const before = m.getLayer('track-line') ? 'track-line' : undefined
  for (const l of scoreLayers(ui.view)) m.addLayer(l, before)
}

function addOverlays(m: MlMap) {
  const empty = fc([])
  m.addSource('track', { type: 'geojson', data: empty })
  m.addSource('spots', { type: 'geojson', data: empty })
  m.addSource('finds', { type: 'geojson', data: empty })
  m.addSource('me', { type: 'geojson', data: empty })
  m.addLayer({ id: 'track-line', type: 'line', source: 'track', paint: { 'line-color': '#7b3fa0', 'line-width': 3, 'line-opacity': 0.85 } })
  m.addLayer({
    id: 'finds-circle',
    type: 'circle',
    source: 'finds',
    paint: { 'circle-radius': 6, 'circle-color': '#3b2f2a', 'circle-stroke-color': '#f6f1e7', 'circle-stroke-width': 2 },
  })
  m.addLayer({
    id: 'spots-circle',
    type: 'circle',
    source: 'spots',
    paint: {
      'circle-radius': 8,
      'circle-color': ['match', ['get', 'kind'], 'riservato', '#b3261e', '#2f6fb3'],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2,
    },
  })
  m.addLayer({
    id: 'spots-label',
    type: 'symbol',
    source: 'spots',
    minzoom: 12,
    layout: { 'text-field': ['get', 'name'], 'text-font': FONT, 'text-size': 12, 'text-offset': [0, 1.2], 'text-anchor': 'top' },
    paint: { 'text-color': '#2a211d', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
  })
  m.addLayer({ id: 'me-acc', type: 'fill', source: 'me', filter: ['==', ['get', 'kind'], 'acc'], paint: { 'fill-color': '#1e88e5', 'fill-opacity': 0.12 } })
  m.addLayer({
    id: 'me-dot',
    type: 'circle',
    source: 'me',
    filter: ['==', ['get', 'kind'], 'dot'],
    paint: { 'circle-radius': 7, 'circle-color': '#1e88e5', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
  })
  addScore(m)
  setData('spots', spotsData())
  setData('finds', findsData())
  setData('track', trackData())
  setData('me', meData())
}

function onClick(e: MapMouseEvent) {
  const m = map.value!
  const box: [[number, number], [number, number]] = [
    [e.point.x - 10, e.point.y - 10],
    [e.point.x + 10, e.point.y + 10],
  ]
  const spotHit = m.getLayer('spots-circle') ? m.queryRenderedFeatures(box, { layers: ['spots-circle'] })[0] : undefined
  const spot = spotHit ? (spots.value.find((s) => s.id === spotHit.properties.id) ?? null) : null
  const lngLat: [number, number] = spot && spot.geom.type === 'Point' ? (spot.geom.coordinates as [number, number]) : [e.lngLat.lng, e.lngLat.lat]
  const layers = ['vth-fill', 'vth-nodata'].filter((l) => m.getLayer(l))
  const vth = layers.length ? m.queryRenderedFeatures(m.project(lngLat), { layers })[0] : undefined
  selection.value = { lngLat, remote: vth ? toRemote(vth.properties) : null, spot }
  ui.newSpotName = ''
}

let releaseGps: (() => void) | null = null

function locate() {
  ui.follow = true
  const f = location.fix
  if (f) map.value?.easeTo({ center: [f.lon, f.lat], zoom: Math.max(map.value.getZoom(), 15) })
}

watch(
  () => location.fix,
  (f) => {
    setData('me', meData())
    if (f && ui.follow) map.value?.easeTo({ center: [f.lon, f.lat], duration: 500 })
  },
)

watch(
  () => settings.basemap,
  () => map.value?.setStyle(baseStyle(settings.basemap, !!mapFiles.basemap), { diff: false }),
)

watch(
  () => mapFiles.score,
  () => map.value?.isStyleLoaded() && addScore(map.value),
)

watch(
  () => ui.view,
  () => map.value && addScore(map.value),
  { deep: true },
)

let trackSub: Subscription | null = null

watch(
  () => tracking.outingId,
  (id) => {
    trackSub?.unsubscribe()
    trackSub = null
    track.value = []
    setData('track', trackData())
    if (!id) return
    trackSub = liveQuery(() => db.outings.get(id)).subscribe((o) => {
      track.value = o?.track.map((p) => [p.lon, p.lat] as [number, number]) ?? []
      setData('track', trackData())
    })
  },
  { immediate: true },
)

onMounted(() => {
  setWorkerUrl(workerUrl)
  addProtocol('pmtiles', protocol.tile)
  const view = savedView()
  const m = new MlMap({
    container: container.value!,
    style: baseStyle(settings.basemap, !!mapFiles.basemap),
    center: view.center,
    zoom: view.zoom,
    attributionControl: { compact: true },
  })
  m.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left')
  m.on('style.load', () => addOverlays(m))
  // L'attribuzione compatta parte aperta e copre mezza mappa sul telefono: la chiudo, resta il pulsante (i).
  const collapseAttribution = () => {
    const el = container.value?.querySelector('.maplibregl-ctrl-attrib.maplibregl-compact-show')
    el?.classList.remove('maplibregl-compact-show')
    el?.removeAttribute('open')
  }
  m.once('load', collapseAttribution)
  m.once('idle', collapseAttribution)
  m.on('click', onClick)
  m.on('dragstart', () => (ui.follow = false))
  m.on('moveend', () => {
    try {
      const c = m.getCenter()
      localStorage.setItem(VIEW_KEY, JSON.stringify({ center: [c.lng, c.lat], zoom: m.getZoom() }))
    } catch {
      /* storage non disponibile: pazienza */
    }
  })
  map.value = m

  subs.push(
    liveQuery(() => db.spots.toArray()).subscribe((s) => {
      spots.value = s
      setData('spots', spotsData())
    }),
    liveQuery(() => db.finds.toArray()).subscribe((f) => {
      finds.value = f
      setData('finds', findsData())
    }),
  )
})

/** /mappa?lon=..&lat=..&z=.. centra la mappa (es. da uno spot). */
function applyQuery() {
  const lon = Number(route.query.lon)
  const lat = Number(route.query.lat)
  if (!route.query.lon || !route.query.lat || !Number.isFinite(lon) || !Number.isFinite(lat)) return
  ui.follow = false
  map.value?.jumpTo({ center: [lon, lat], zoom: Number(route.query.z) || 15 })
}

watch(() => route.query, () => route.name === 'mappa' && applyQuery())

onActivated(() => {
  releaseGps = acquireLocation()
  map.value?.resize()
  applyQuery()
})

onDeactivated(() => {
  releaseGps?.()
  releaseGps = null
})

onBeforeUnmount(() => {
  releaseGps?.()
  subs.forEach((s) => s.unsubscribe())
  trackSub?.unsubscribe()
  map.value?.remove()
  removeProtocol('pmtiles')
})

async function saveSpot(kind: Spot['kind']) {
  const sel = selection.value
  if (!sel) return
  const spot: Spot = {
    id: newId(),
    name: ui.newSpotName.trim() || (kind === 'riservato' ? 'Tartufaia riservata' : `Spot ${new Date().toLocaleDateString('it-IT')}`),
    kind,
    geom: { type: 'Point', coordinates: [sel.lngLat[0], sel.lngLat[1]] },
    remote: sel.remote ? plain({ score: sel.remote.score, n: sel.remote.n, points: sel.remote.points }) : undefined,
    createdAt: nowIso(),
  }
  await db.spots.add(spot)
  selection.value = { ...sel, spot }
}

function assessHere() {
  const sel = selection.value
  if (!sel) return
  if (sel.spot) router.push({ path: '/campo', query: { spot: sel.spot.id } })
  else router.push({ path: '/campo', query: { lon: sel.lngLat[0].toFixed(6), lat: sel.lngLat[1].toFixed(6) } })
}

function setView(v: string) {
  if (v === 'score' || v === 'off') ui.view = { kind: v }
  else ui.view = { kind: 'param', param: v, max: param(v as ParamId).remote.max }
}

const viewValue = computed(() => (ui.view.kind === 'param' ? ui.view.param : ui.view.kind))

const legend = computed(() => {
  if (ui.view.kind === 'score') return [...model.classes].reverse().map((c) => ({ color: c.color, label: c.label }))
  if (ui.view.kind === 'param') {
    return ui.view.max === 1
      ? [
          { color: '#1a9850', label: '1 pt' },
          { color: '#d73027', label: '0 pt' },
        ]
      : [3, 2, 1, 0].map((p) => ({ color: ['#d73027', '#fc8d59', '#a6d96a', '#1a9850'][p], label: `${p} pt` }))
  }
  return []
})
</script>

<template>
  <div class="mapwrap">
    <div ref="container" class="map" data-testid="map" />

    <div class="notices">
      <div v-if="synthetic" class="banner bad small">Mappa di prova con dati SINTETICI: non usarla per cercare.</div>
      <div v-else-if="scoreWarning" class="banner warn small" @click="notesOpen = !notesOpen">
        Mappa in bozza: alcune classificazioni sono da rivedere.
        <template v-if="notesOpen"><br />{{ scoreWarning }}<template v-if="metaText('aoi_note')"><br />{{ metaText('aoi_note') }}</template></template>
        <template v-else> (tocca per i dettagli)</template>
      </div>
      <div v-if="!mapFiles.score" class="banner warn small">
        Nessuna mappa di idoneità caricata. <RouterLink to="/impostazioni">Importala</RouterLink> dal file della pipeline.
      </div>
      <div v-if="offlineMissing" class="banner warn small">Basemap offline non importata: uso OpenTopoMap online.</div>
      <div v-if="location.error" class="banner warn small">{{ location.error }}</div>
    </div>

    <div class="controls">
      <button class="ctl" :class="{ on: ui.follow }" aria-label="Centra sulla mia posizione" @click="locate">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>
      </button>
      <button class="ctl" :class="{ on: ui.layersOpen }" aria-label="Livelli" @click="ui.layersOpen = !ui.layersOpen">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3 9 5-9 5-9-5 9-5zM3 13l9 5 9-5" /></svg>
      </button>
    </div>

    <div v-if="ui.layersOpen" class="panel layers">
      <label class="field">
        <span>Idoneità</span>
        <select :value="viewValue" @change="setView(($event.target as HTMLSelectElement).value)">
          <option value="score">Score remoto (classi VTH)</option>
          <option v-for="p in paramOptions" :key="p.id" :value="p.id">Solo {{ p.label.toLowerCase() }}</option>
          <option value="off">Nascondi</option>
        </select>
      </label>
      <label class="field">
        <span>Sfondo</span>
        <select v-model="settings.basemap">
          <option value="opentopomap">OpenTopoMap (online)</option>
          <option value="osm">OpenStreetMap (online)</option>
          <option value="offline">Offline (Protomaps importato)</option>
        </select>
      </label>
      <div v-if="legend.length" class="row small">
        <span v-for="l in legend" :key="l.label" class="row" style="gap: 4px"><span class="swatch" :style="{ background: l.color }" />{{ l.label }}</span>
        <span class="row" style="gap: 4px"><span class="swatch" style="background: #7a7a7a; opacity: 0.5" />dati insufficienti</span>
      </div>
    </div>

    <div v-if="selection" class="panel sheet" data-testid="sheet">
      <div class="row spread">
        <strong>{{ selection.spot ? selection.spot.name : 'Punto selezionato' }}</strong>
        <button class="ghost" aria-label="Chiudi" @click="selection = null">✕</button>
      </div>
      <div class="small muted">{{ formatCoord(selection.lngLat) }}</div>
      <div v-if="selection.spot?.kind === 'riservato'" class="banner bad small" style="margin: 8px 0">Tartufaia riservata: off-limits.</div>

      <template v-if="selection.remote">
        <div class="row" style="margin: 8px 0">
          <template v-if="selection.remote.score !== undefined">
            <span class="pill" :style="{ background: remoteClass(selection.remote.score).color, color: '#1b1714' }">
              {{ remoteClass(selection.remote.score).label }}
            </span>
            <span>{{ Math.round(selection.remote.score * 100) }}% · {{ selection.remote.pts }}/{{ selection.remote.max }} punti su {{ selection.remote.n }} parametri</span>
          </template>
          <span v-else class="pill neutral">Dati insufficienti ({{ selection.remote.n ?? 0 }} parametri)</span>
        </div>
        <table class="small">
          <tbody>
            <tr v-for="p in paramOptions" :key="p.id">
              <td>{{ p.label }}</td>
              <td style="text-align: right">
                <template v-if="selection.remote.points[p.id] !== undefined">{{ selection.remote.points[p.id] }}/{{ p.max }}</template>
                <span v-else class="muted">n.d.</span>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
      <p v-else-if="mapFiles.score" class="small muted" style="margin-top: 8px">Fuori dalla superficie boscata coperta dalla mappa.</p>

      <div v-if="!selection.spot" class="stack" style="margin-top: 10px">
        <input v-model="ui.newSpotName" placeholder="Nome (facoltativo)" />
        <div class="row">
          <button @click="saveSpot('interesse')">Salva spot</button>
          <button class="danger" @click="saveSpot('riservato')">Segna riservata</button>
          <button class="primary" @click="assessHere">Valuta qui</button>
        </div>
      </div>
      <div v-else class="row" style="margin-top: 10px">
        <RouterLink class="btn" :to="`/diario/spot/${selection.spot.id}`">Apri spot</RouterLink>
        <button class="primary" @click="assessHere">Valuta</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mapwrap {
  position: relative;
  height: calc(100% - var(--nav-h) - var(--safe-b));
}

.map {
  position: absolute;
  inset: 0;
}

.notices {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 64px;
  z-index: 2;
}

.notices .banner {
  margin-bottom: 6px;
  padding: 8px 10px;
}

.controls {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 2;
}

.ctl {
  width: 44px;
  height: 44px;
  padding: 0;
  background: var(--surface);
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.25);
}

.ctl.on {
  color: #1e88e5;
}

.panel {
  position: absolute;
  left: 10px;
  right: 10px;
  z-index: 3;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px 14px;
  box-shadow: 0 4px 16px rgb(0 0 0 / 0.2);
  max-width: 520px;
  margin: 0 auto;
}

.layers {
  top: 120px;
}

.sheet {
  bottom: 12px;
  max-height: 60%;
  overflow-y: auto;
}
</style>
