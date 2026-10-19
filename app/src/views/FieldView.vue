<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AssessmentSummary from '../components/AssessmentSummary.vue'
import ChipSelect from '../components/ChipSelect.vue'
import { db, newId, nowIso, type FieldAssessment, type Spot } from '../diary/db'
import { model, param } from '../field/model'
import { assess, type FieldInputs } from '../field/vth'
import { currentFix, location } from '../lib/geolocation'
import { formatCoord } from '../lib/geo'
import { plain } from '../lib/plain'
import { mapFiles, pmtiles } from '../map/mapFiles'
import { remoteAt, type RemoteAt } from '../map/remote'

const route = useRoute()
const router = useRouter()

const position = ref<[number, number] | null>(null)
const positionSource = ref('')
const spot = ref<Spot | null>(null)
const remote = ref<RemoteAt | null>(null)
const remoteNote = ref('')
const busy = ref(false)
const saved = ref<string | null>(null)
const notes = ref('')
const spotName = ref('')

const inputs = reactive<FieldInputs>({})
const a = computed(() => assess(inputs, remote.value?.points ?? {}))

const cat = (id: Parameters<typeof param>[0]) => param(id).categories!.map((c) => ({ id: c.id, label: `${c.label} (${c.points})` }))
const fizzLevels = param('caco3').fizzTest!.levels
const orchidGenera = param('orchids').genera!
const insectTaxa = param('insects').taxa!

async function loadRemote(lon: number, lat: number) {
  const pm = pmtiles('score')
  if (!pm) {
    remoteNote.value = 'Nessuna mappa di idoneità caricata: conta solo quello che osservi.'
    return
  }
  try {
    remote.value = await remoteAt(pm, lon, lat)
    remoteNote.value = remote.value ? '' : 'Punto fuori dalla superficie boscata coperta dalla mappa.'
  } catch (e) {
    remoteNote.value = `Lettura della mappa fallita: ${(e as Error).message}`
  }
}

async function useGps() {
  busy.value = true
  try {
    const f = await currentFix()
    position.value = [f.lon, f.lat]
    positionSource.value = `GPS ±${Math.round(f.acc)} m`
    if (f.alt !== null && inputs.elevation === undefined) inputs.elevation = Math.round(f.alt)
    await loadRemote(f.lon, f.lat)
  } catch (e) {
    remoteNote.value = (e as Error).message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  const q = route.query
  if (typeof q.spot === 'string') {
    const s = await db.spots.get(q.spot)
    if (s && s.geom.type === 'Point') {
      spot.value = s
      position.value = s.geom.coordinates as [number, number]
      positionSource.value = `spot "${s.name}"`
      await loadRemote(position.value[0], position.value[1])
      if (!remote.value && s.remote) remote.value = plain(s.remote)
      const last = await db.assessments.where('spotId').equals(s.id).reverse().sortBy('date')
      if (last[0]) Object.assign(inputs, plain(last[0].inputs))
    }
  } else if (typeof q.lon === 'string' && typeof q.lat === 'string') {
    position.value = [Number(q.lon), Number(q.lat)]
    positionSource.value = 'punto scelto sulla mappa'
    await loadRemote(position.value[0], position.value[1])
  } else {
    await useGps()
  }
})

function useGpsAltitude() {
  if (location.fix?.alt != null) inputs.elevation = Math.round(location.fix.alt)
}

function toggleHost(id: string, layer: 'tree' | 'lower') {
  const h = inputs.hosts ?? { tree: [], lower: [] }
  const list = h[layer]
  h[layer] = list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
  inputs.hosts = { ...h }
}

function toggleIn(list: string[] | undefined, v: string): string[] {
  const l = list ?? []
  return l.includes(v) ? l.filter((x) => x !== v) : [...l, v]
}

function setNumber(key: 'ph' | 'caExch' | 'caco3Pct' | 'elevation', raw: string) {
  const v = raw.trim() === '' ? undefined : Number(raw.replace(',', '.'))
  inputs[key] = v !== undefined && Number.isFinite(v) ? v : undefined
}

async function save() {
  busy.value = true
  try {
    let spotId = spot.value?.id
    if (!spotId && spotName.value.trim() && position.value) {
      const s: Spot = {
        id: newId(),
        name: spotName.value.trim(),
        kind: 'interesse',
        geom: { type: 'Point', coordinates: [position.value[0], position.value[1]] },
        remote: remote.value ? plain({ score: remote.value.score, n: remote.value.n, points: remote.value.points }) : undefined,
        createdAt: nowIso(),
      }
      await db.spots.add(s)
      spotId = s.id
    }
    const rec: FieldAssessment = {
      id: newId(),
      spotId,
      date: nowIso(),
      position: position.value ? [position.value[0], position.value[1]] : undefined,
      modelId: model.id,
      inputs: plain(inputs),
      remote: plain(remote.value?.points ?? {}),
      result: {
        pts: a.value.pts,
        max: a.value.max,
        score36: a.value.score36,
        classId: a.value.vthClass?.id ?? null,
        observed: a.value.observed,
        estimated: a.value.estimated,
      },
      notes: notes.value.trim() || undefined,
    }
    await db.assessments.add(rec)
    saved.value = spotId ?? rec.id
    if (spotId) router.push(`/diario/spot/${spotId}`)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page">
    <h1>Valutazione sul posto</h1>
    <p class="small muted">
      Checklist VTH: quello che osservi vince sulla mappa. Lascia vuoto quello che non sai, non inventare.
    </p>

    <section class="card">
      <div class="row spread">
        <div>
          <div v-if="position"><strong>{{ formatCoord(position) }}</strong></div>
          <div v-else class="muted">Posizione non ancora nota</div>
          <div class="small muted">{{ positionSource }}</div>
        </div>
        <button :disabled="busy" @click="useGps">Usa GPS</button>
      </div>
      <p v-if="remoteNote" class="small muted" style="margin: 8px 0 0">{{ remoteNote }}</p>
      <p v-else-if="remote && remote.score !== undefined" class="small" style="margin: 8px 0 0">
        Score remoto qui: {{ Math.round(remote.score * 100) }}% su {{ remote.n }} parametri.
      </p>
      <p v-if="mapFiles.score?.meta?.synthetic" class="banner bad small" style="margin: 8px 0 0">La mappa caricata è SINTETICA (test).</p>
    </section>

    <section class="card sticky" data-testid="summary">
      <AssessmentSummary :a="a" compact />
    </section>

    <section class="card">
      <h2>Bosco</h2>
      <h3>Struttura</h3>
      <ChipSelect v-model="inputs.forestStructure" :options="cat('forest_structure')" />
      <h3 style="margin-top: 14px">Tipo di bosco</h3>
      <ChipSelect v-model="inputs.forestType" :options="cat('forest_type')" />
    </section>

    <section class="card">
      <div class="row spread">
        <h2>Piante ospiti</h2>
        <button class="ghost small" @click="inputs.hosts = { tree: [], lower: [] }">Nessuna</button>
      </div>
      <p class="small muted">3 punti: più di 2 ospiti arboree e nocciolo. 2: almeno una arborea e una nel piano inferiore.</p>
      <table class="small">
        <thead>
          <tr><th>Specie</th><th>Arboreo</th><th>Inferiore</th></tr>
        </thead>
        <tbody>
          <tr v-for="h in model.hostSpecies" :key="h.id">
            <td>{{ h.it }} <span class="muted"><i>{{ h.latin }}</i></span></td>
            <td><input type="checkbox" class="cb" :checked="inputs.hosts?.tree.includes(h.id)" @change="toggleHost(h.id, 'tree')" /></td>
            <td><input type="checkbox" class="cb" :checked="inputs.hosts?.lower.includes(h.id)" @change="toggleHost(h.id, 'lower')" /></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <div class="row spread">
        <h2>Orchidee</h2>
        <button class="ghost small" @click="inputs.orchids = { genera: [], speciesCount: 0 }">Nessuna</button>
      </div>
      <div class="chips">
        <button
          v-for="g in orchidGenera"
          :key="g"
          type="button"
          class="chip"
          :class="{ on: inputs.orchids?.genera.includes(g) }"
          @click="inputs.orchids = { genera: toggleIn(inputs.orchids?.genera, g), speciesCount: Math.max(inputs.orchids?.speciesCount ?? 0, 1) }"
        >
          <i>{{ g }}</i>
        </button>
      </div>
      <label class="field" style="margin-top: 10px">
        <span>Specie diverse viste (1 = 2 punti, più di 1 = 3 punti)</span>
        <input
          type="number"
          min="0"
          inputmode="numeric"
          :value="inputs.orchids?.speciesCount ?? ''"
          @input="inputs.orchids = { genera: inputs.orchids?.genera ?? [], speciesCount: Math.max(0, Number(($event.target as HTMLInputElement).value) || 0) }"
        />
      </label>
    </section>

    <section class="card">
      <div class="row spread">
        <h2>Insetti</h2>
        <button class="ghost small" @click="inputs.insects = []">Nessuno</button>
      </div>
      <div class="chips">
        <button v-for="t in insectTaxa" :key="t" type="button" class="chip" :class="{ on: inputs.insects?.includes(t) }" @click="inputs.insects = toggleIn(inputs.insects, t)">
          <i>{{ t }}</i>
        </button>
      </div>
    </section>

    <section class="card">
      <h2>Suolo e roccia</h2>
      <label class="field">
        <span>pH (kit da campo)</span>
        <input type="text" inputmode="decimal" placeholder="es. 7,4" :value="inputs.ph ?? ''" @change="setNumber('ph', ($event.target as HTMLInputElement).value)" />
      </label>
      <h3>Effervescenza con HCl 10%</h3>
      <ChipSelect v-model="inputs.caco3Fizz" :options="fizzLevels.map((l) => ({ id: l.id, label: `${l.label} (${l.points})` }))" />
      <p class="small muted" style="margin-top: 6px">{{ param('caco3').fizzTest!.note }}</p>
      <label class="field">
        <span>Tessitura</span>
        <select :value="inputs.texture ?? ''" @change="inputs.texture = ($event.target as HTMLSelectElement).value || undefined">
          <option value="">Non valutata</option>
          <option v-for="c in param('texture').categories" :key="c.id" :value="c.id">{{ c.label }} ({{ c.points }})</option>
        </select>
      </label>
      <h3>Roccia madre</h3>
      <ChipSelect v-model="inputs.bedrock" :options="cat('bedrock')" />
    </section>

    <section class="card">
      <h2>Quota</h2>
      <div class="row">
        <input style="flex: 1" type="text" inputmode="numeric" placeholder="m slm" :value="inputs.elevation ?? ''" @change="setNumber('elevation', ($event.target as HTMLInputElement).value)" />
        <button :disabled="location.fix?.alt == null" @click="useGpsAltitude">Dal GPS</button>
      </div>
    </section>

    <details class="card">
      <summary><strong>Analisi di laboratorio</strong> <span class="small muted">(facoltative)</span></summary>
      <label class="field" style="margin-top: 10px">
        <span>CaCO3 (%)</span>
        <input type="text" inputmode="decimal" :value="inputs.caco3Pct ?? ''" @change="setNumber('caco3Pct', ($event.target as HTMLInputElement).value)" />
      </label>
      <label class="field">
        <span>Ca scambiabile (cmol+/kg)</span>
        <input type="text" inputmode="decimal" :value="inputs.caExch ?? ''" @change="setNumber('caExch', ($event.target as HTMLInputElement).value)" />
      </label>
      <p class="small muted">C/N: {{ param('cn').excludedReason }}</p>
    </details>

    <section class="card">
      <h2>Riepilogo</h2>
      <AssessmentSummary :a="a" />
    </section>

    <section class="card">
      <label v-if="!spot" class="field">
        <span>Salva anche come spot (nome)</span>
        <input v-model="spotName" placeholder="es. Fragno, castagneto sopra la strada" />
      </label>
      <label class="field">
        <span>Note</span>
        <textarea v-model="notes" />
      </label>
      <button class="primary wide" :disabled="busy || a.score36 === null" @click="save">Salva valutazione</button>
      <p v-if="saved && !spot" class="banner ok small" style="margin-top: 10px">Salvata. <RouterLink to="/diario">Vai al diario</RouterLink></p>
    </section>
  </div>
</template>

<style scoped>
.sticky {
  position: sticky;
  top: 0;
  z-index: 5;
  box-shadow: 0 2px 8px rgb(0 0 0 / 0.08);
}

.cb {
  width: 24px;
  height: 24px;
  min-height: 0;
}

h3 {
  font-size: 0.9rem;
  color: var(--muted);
}
</style>
