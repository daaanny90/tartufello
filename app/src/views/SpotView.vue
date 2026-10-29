<script setup lang="ts">
import { liveQuery, type Subscription } from 'dexie'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AssessmentSummary from '../components/AssessmentSummary.vue'
import { DANGER_RADIUS_M } from '../diary/danger'
import { db, HAZARD_LABELS, type FieldAssessment, type Find, type Hazard, type Outing, type Spot } from '../diary/db'
import { VISIT_RADIUS_M } from '../diary/outings'
import { param, REMOTE_PARAMS } from '../field/model'
import { assess, remoteClass } from '../field/vth'
import { distance, formatCoord } from '../lib/geo'
import { formatDate } from '../rules/calendar'

const props = defineProps<{ id: string }>()
const router = useRouter()

const spot = ref<Spot | null>(null)
const assessments = ref<FieldAssessment[]>([])
const outings = ref<Outing[]>([])
const nearFinds = ref<Find[]>([])
const subs: Subscription[] = []

onMounted(() => {
  subs.push(
    liveQuery(() => db.spots.get(props.id)).subscribe((s) => (spot.value = s ?? null)),
    liveQuery(() => db.assessments.where('spotId').equals(props.id).reverse().sortBy('date')).subscribe((a) => (assessments.value = a)),
    liveQuery(() => db.outings.filter((o) => o.spotsVisited.includes(props.id)).toArray()).subscribe((o) => (outings.value = o)),
    liveQuery(async () => {
      const s = await db.spots.get(props.id)
      if (!s || s.geom.type !== 'Point') return []
      const p = s.geom.coordinates as [number, number]
      return db.finds.filter((f) => distance(p, f.position) <= VISIT_RADIUS_M).toArray()
    }).subscribe((f) => (nearFinds.value = f)),
  )
})
onBeforeUnmount(() => subs.forEach((s) => s.unsubscribe()))

const coords = computed(() => (spot.value?.geom.type === 'Point' ? (spot.value.geom.coordinates as [number, number]) : null))

/** Ricalcola con il modello attuale: se le soglie cambiano, la storia si rilegge con quelle nuove. */
const results = computed(() => assessments.value.map((a) => ({ rec: a, now: assess(a.inputs, a.remote) })))

async function rename(name: string) {
  if (name.trim()) await db.spots.update(props.id, { name: name.trim() })
}

async function setKind(kind: Spot['kind']) {
  await db.spots.update(props.id, kind === 'pericolo' && !spot.value?.hazard ? { kind, hazard: 'esca' } : { kind })
}

async function setHazard(hazard: Hazard) {
  await db.spots.update(props.id, { hazard })
}

async function setNotes(notes: string) {
  await db.spots.update(props.id, { notes: notes.trim() || undefined })
}

async function remove() {
  if (!confirm('Eliminare lo spot e le sue valutazioni? Uscite e ritrovamenti restano.')) return
  await db.transaction('rw', db.spots, db.assessments, async () => {
    await db.assessments.where('spotId').equals(props.id).delete()
    await db.spots.delete(props.id)
  })
  router.replace('/diario')
}
</script>

<template>
  <div v-if="spot" class="page">
    <RouterLink to="/diario" class="small">← Diario</RouterLink>
    <h1 style="margin-top: 8px">{{ spot.name }}</h1>
    <div v-if="spot.kind === 'riservato'" class="banner bad">Tartufaia coltivata o controllata: raccolta riservata, off-limits.</div>
    <div v-if="spot.kind === 'pericolo'" class="banner bad">
      Pericolo per il cane. Con il GPS acceso l'app avvisa e vibra entro {{ DANGER_RADIUS_M }} m.
      <RouterLink to="/emergenza">Cosa fare in emergenza</RouterLink>
    </div>

    <section class="card">
      <div class="small muted" v-if="coords">{{ formatCoord(coords) }}</div>
      <label class="field" style="margin-top: 8px">
        <span>Nome</span>
        <input :value="spot.name" @change="rename(($event.target as HTMLInputElement).value)" />
      </label>
      <div class="chips">
        <button class="chip" :class="{ on: spot.kind === 'interesse' }" @click="setKind('interesse')">Di interesse</button>
        <button class="chip" :class="{ on: spot.kind === 'riservato' }" @click="setKind('riservato')">Riservata (off-limits)</button>
        <button class="chip" :class="{ on: spot.kind === 'pericolo' }" @click="setKind('pericolo')">Pericolo (esche)</button>
      </div>
      <div v-if="spot.kind === 'pericolo'" class="chips" style="margin-top: 8px">
        <button v-for="(label, h) in HAZARD_LABELS" :key="h" class="chip" :class="{ on: spot.hazard === h }" @click="setHazard(h)">{{ label }}</button>
      </div>
      <label class="field" style="margin-top: 12px">
        <span>Note</span>
        <textarea :value="spot.notes ?? ''" :placeholder="spot.kind === 'pericolo' ? 'es. polpetta vicino alla sbarra, segnalata all\'ASL il…' : ''" @change="setNotes(($event.target as HTMLTextAreaElement).value)" />
      </label>
      <div class="row" style="margin-top: 12px">
        <RouterLink class="btn primary" :to="{ path: '/campo', query: { spot: spot.id } }">Nuova valutazione</RouterLink>
        <RouterLink v-if="coords" class="btn" :to="{ path: '/mappa', query: { spot: spot.id, lon: coords[0], lat: coords[1], z: 16 } }">Portami qui</RouterLink>
      </div>
    </section>

    <section v-if="spot.remote" class="card">
      <h2>Dalla mappa</h2>
      <p v-if="spot.remote.score !== undefined">
        <span class="pill" :style="{ background: remoteClass(spot.remote.score).color, color: '#1b1714' }">{{ remoteClass(spot.remote.score).label }}</span>
        {{ Math.round(spot.remote.score * 100) }}% su {{ spot.remote.n }} parametri
      </p>
      <p v-else class="muted">Dati insufficienti.</p>
      <table class="small">
        <tbody>
          <tr v-for="id in REMOTE_PARAMS" :key="id">
            <td>{{ param(id).label }}</td>
            <td style="text-align: right">
              <template v-if="spot.remote.points[id] !== undefined">{{ spot.remote.points[id] }}/{{ param(id).remote.max }}</template>
              <span v-else class="muted">n.d.</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <h2>Valutazioni sul posto</h2>
      <p v-if="!results.length" class="muted small">Nessuna.</p>
      <div v-for="r in results" :key="r.rec.id" class="assessment">
        <div class="small muted">{{ formatDate(new Date(r.rec.date)) }} · modello {{ r.rec.modelId }}</div>
        <AssessmentSummary :a="r.now" />
        <p v-if="r.rec.notes" class="small" style="margin-top: 6px">{{ r.rec.notes }}</p>
      </div>
    </section>

    <section class="card">
      <h2>Storia</h2>
      <p class="small">{{ outings.length }} uscite ci sono passate, {{ nearFinds.length }} ritrovamenti entro {{ VISIT_RADIUS_M }} m.</p>
      <ul class="list">
        <li v-for="o in outings" :key="o.id">
          <RouterLink :to="`/diario/uscita/${o.id}`">{{ formatDate(new Date(o.date)) }}</RouterLink>
        </li>
      </ul>
    </section>

    <button class="danger wide" @click="remove">Elimina spot</button>
  </div>
  <div v-else class="page"><p class="empty">Spot non trovato.</p></div>
</template>

<style scoped>
.assessment + .assessment {
  border-top: 1px solid var(--line);
  margin-top: 12px;
  padding-top: 12px;
}
</style>
