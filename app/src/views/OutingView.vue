<script setup lang="ts">
import { liveQuery, type Subscription } from 'dexie'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import FindForm from '../components/FindForm.vue'
import TrackPreview from '../components/TrackPreview.vue'
import { db, SPECIES_LABELS, type Find, type Outing, type Spot } from '../diary/db'
import { endOuting, startOuting, tracking } from '../diary/outings'
import { model } from '../field/model'
import { formatDistance, formatDuration, trackLength } from '../lib/geo'
import { formatDate } from '../rules/calendar'

const props = defineProps<{ id: string }>()
const router = useRouter()

const outing = ref<Outing | null>(null)
const finds = ref<Find[]>([])
const spots = ref<Spot[]>([])
const adding = ref(false)
const photoUrls = ref<Record<string, string>>({})
const subs: Subscription[] = []

onMounted(() => {
  subs.push(
    liveQuery(() => db.outings.get(props.id)).subscribe((o) => (outing.value = o ?? null)),
    liveQuery(() => db.finds.where('outingId').equals(props.id).sortBy('date')).subscribe((f) => (finds.value = f)),
    liveQuery(() => db.spots.toArray()).subscribe((s) => (spots.value = s)),
  )
})

watch(finds, (list) => {
  for (const f of list) if (f.photo && !photoUrls.value[f.id]) photoUrls.value[f.id] = URL.createObjectURL(f.photo)
})

onBeforeUnmount(() => {
  subs.forEach((s) => s.unsubscribe())
  Object.values(photoUrls.value).forEach((u) => URL.revokeObjectURL(u))
})

const active = computed(() => !!outing.value && !outing.value.endedAt)
const recording = computed(() => tracking.outingId === props.id)
const now = ref(Date.now())
const timer = setInterval(() => (now.value = Date.now()), 30_000)
onBeforeUnmount(() => clearInterval(timer))

const duration = computed(() => {
  const o = outing.value
  if (!o) return 0
  return (o.endedAt ? new Date(o.endedAt).getTime() : now.value) - new Date(o.date).getTime()
})
const length = computed(() => (outing.value ? trackLength(outing.value.track) : 0))
const totalGrams = computed(() => finds.value.reduce((s, f) => s + (f.grams ?? 0), 0))
const visited = computed(() => spots.value.filter((s) => outing.value?.spotsVisited.includes(s.id)))
const spotPoints = computed(() => visited.value.filter((s) => s.geom.type === 'Point').map((s) => s.geom.coordinates as [number, number]))
const hostName = (id?: string) => model.hostSpecies.find((h) => h.id === id)?.it

async function update(patch: Partial<Outing>) {
  await db.outings.update(props.id, patch)
}

async function finish() {
  await endOuting(props.id)
}

async function resume() {
  await db.outings.update(props.id, { endedAt: undefined })
  await startOuting()
}

async function removeFind(f: Find) {
  if (confirm('Eliminare questo ritrovamento?')) await db.finds.delete(f.id)
}

async function removeOuting() {
  if (!confirm('Eliminare l\'uscita con traccia e ritrovamenti? Non si torna indietro.')) return
  if (recording.value) await endOuting(props.id)
  await db.transaction('rw', db.outings, db.finds, async () => {
    await db.finds.where('outingId').equals(props.id).delete()
    await db.outings.delete(props.id)
  })
  router.replace('/diario')
}
</script>

<template>
  <div class="page" v-if="outing">
    <RouterLink to="/diario" class="small">← Diario</RouterLink>
    <div class="row spread" style="margin-top: 8px">
      <h1>Uscita del {{ formatDate(new Date(outing.date)) }}</h1>
      <span class="pill" :class="active ? 'warn' : finds.length ? 'ok' : 'neutral'">
        {{ active ? 'in corso' : finds.length ? `${finds.length} trovati` : 'giro a vuoto' }}
      </span>
    </div>

    <section class="card">
      <div class="row spread">
        <span>{{ formatDuration(duration) }}</span>
        <span>{{ formatDistance(length) }}</span>
        <span>{{ outing.track.length }} punti</span>
        <span v-if="totalGrams">{{ totalGrams }} g</span>
      </div>
      <TrackPreview :track="outing.track" :finds="finds.map((f) => f.position)" :spots="spotPoints" style="margin-top: 10px" />
      <p v-if="recording" class="small muted" style="margin-top: 8px">
        Registro la traccia finché l'app resta aperta{{ tracking.wakeLock ? ' (schermo tenuto acceso)' : '' }}. A schermo bloccato il browser può fermare il GPS.
      </p>
      <div class="row" style="margin-top: 10px">
        <template v-if="active">
          <button class="primary" @click="adding = true">Ritrovamento</button>
          <button v-if="!recording" @click="startOuting()">Riprendi traccia</button>
          <button @click="finish">Termina uscita</button>
        </template>
        <button v-else class="ghost" @click="resume">Riapri</button>
      </div>
    </section>

    <FindForm v-if="adding" :outing-id="outing.id" @saved="adding = false" @cancel="adding = false" />

    <section class="card">
      <h2>Ritrovamenti</h2>
      <p v-if="!finds.length" class="muted small">Nessuno. Va registrata lo stesso: anche il vuoto serve alla calibrazione.</p>
      <ul class="list">
        <li v-for="f in finds" :key="f.id">
          <div class="item row" style="flex-wrap: nowrap; align-items: flex-start">
            <img v-if="photoUrls[f.id]" :src="photoUrls[f.id]" alt="" class="thumb" />
            <div style="flex: 1">
              <strong>{{ SPECIES_LABELS[f.species] }}</strong>
              <div class="small muted">
                {{ new Date(f.date).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) }}
                <template v-if="f.grams"> · {{ f.grams }} g</template>
                <template v-if="f.depthCm"> · {{ f.depthCm }} cm</template>
                <template v-if="f.hostNearby"> · {{ hostName(f.hostNearby) }}</template>
              </div>
              <div v-if="f.notes" class="small">{{ f.notes }}</div>
            </div>
            <button class="ghost small" aria-label="Elimina ritrovamento" @click="removeFind(f)">✕</button>
          </div>
        </li>
      </ul>
    </section>

    <section class="card">
      <h2>Dettagli</h2>
      <label class="field">
        <span>Cane</span>
        <input :value="outing.dog" @change="update({ dog: ($event.target as HTMLInputElement).value })" />
      </label>
      <label class="field">
        <span>Meteo e terreno</span>
        <input :value="outing.weather ?? ''" placeholder="es. 3 giorni dopo pioggia, terreno umido" @change="update({ weather: ($event.target as HTMLInputElement).value })" />
      </label>
      <label class="field">
        <span>Note</span>
        <textarea :value="outing.notes ?? ''" @change="update({ notes: ($event.target as HTMLTextAreaElement).value })" />
      </label>
      <h3>Spot visitati</h3>
      <p v-if="!visited.length" class="small muted">{{ active ? 'Si calcolano alla fine, dalla traccia.' : 'Nessuno spot sulla traccia.' }}</p>
      <ul class="list">
        <li v-for="s in visited" :key="s.id"><RouterLink :to="`/diario/spot/${s.id}`">{{ s.name }}</RouterLink></li>
      </ul>
    </section>

    <button class="danger wide" @click="removeOuting">Elimina uscita</button>
  </div>
  <div v-else class="page"><p class="empty">Uscita non trovata.</p></div>
</template>

<style scoped>
.thumb {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 8px;
}
</style>
