<script setup lang="ts">
import { liveQuery, type Subscription } from 'dexie'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { db, type FieldAssessment, type Find, type Outing, type Spot } from '../diary/db'
import { startOuting, tracking } from '../diary/outings'
import { outingLabel } from '../lib/storage'
import { model } from '../field/model'
import { remoteClass } from '../field/vth'
import { formatDistance, formatDuration, trackLength } from '../lib/geo'
import { formatDate } from '../rules/calendar'

const router = useRouter()
const tab = ref<'uscite' | 'spot'>('uscite')
const outings = ref<Outing[]>([])
const finds = ref<Find[]>([])
const spots = ref<Spot[]>([])
const assessments = ref<FieldAssessment[]>([])
const subs: Subscription[] = []

onMounted(() => {
  subs.push(
    liveQuery(() => db.outings.orderBy('date').reverse().toArray()).subscribe((o) => (outings.value = o)),
    liveQuery(() => db.finds.toArray()).subscribe((f) => (finds.value = f)),
    liveQuery(() => db.spots.orderBy('createdAt').reverse().toArray()).subscribe((s) => (spots.value = s)),
    liveQuery(() => db.assessments.orderBy('date').toArray()).subscribe((a) => (assessments.value = a)),
  )
})
onBeforeUnmount(() => subs.forEach((s) => s.unsubscribe()))

const findsBy = computed(() => {
  const m = new Map<string, Find[]>()
  for (const f of finds.value) m.set(f.outingId, [...(m.get(f.outingId) ?? []), f])
  return m
})

const lastAssessment = computed(() => {
  const m = new Map<string, FieldAssessment>()
  for (const a of assessments.value) if (a.spotId) m.set(a.spotId, a)
  return m
})

const classOf = (id: string | null | undefined) => model.classes.find((c) => c.id === id)

const duration = (o: Outing) => (o.endedAt ? new Date(o.endedAt).getTime() - new Date(o.date).getTime() : 0)

async function newOuting() {
  const o = await startOuting()
  router.push(`/diario/uscita/${o.id}`)
}
</script>

<template>
  <div class="page">
    <div class="row spread">
      <h1>Diario</h1>
      <button v-if="!tracking.outingId" class="primary" @click="newOuting">Nuova uscita</button>
    </div>
    <div class="chips" style="margin-bottom: 12px">
      <button class="chip" :class="{ on: tab === 'uscite' }" @click="tab = 'uscite'">Uscite ({{ outings.length }})</button>
      <button class="chip" :class="{ on: tab === 'spot' }" @click="tab = 'spot'">Spot ({{ spots.length }})</button>
    </div>

    <section v-if="tab === 'uscite'" class="card">
      <p v-if="!outings.length" class="empty">Nessuna uscita. La prima finestra vera è lo scorzone estivo da giugno 2027.</p>
      <ul class="list">
        <li v-for="o in outings" :key="o.id">
          <RouterLink :to="`/diario/uscita/${o.id}`">
            <div class="row spread">
              <strong>{{ formatDate(new Date(o.date)) }}<span v-if="o.kind === 'sopralluogo'" class="muted small"> · {{ outingLabel(o.kind) }}</span></strong>
              <span
                class="pill"
                :class="!o.endedAt ? 'warn' : findsBy.get(o.id)?.length ? 'ok' : 'neutral'"
              >
                {{ !o.endedAt ? 'in corso' : findsBy.get(o.id)?.length ? `${findsBy.get(o.id)!.length} trovati` : o.kind === 'sopralluogo' ? `${o.spotsVisited.length} spot` : 'giro a vuoto' }}
              </span>
            </div>
            <div class="small muted">
              {{ formatDistance(trackLength(o.track)) }}<template v-if="o.endedAt"> · {{ formatDuration(duration(o)) }}</template>
              <template v-if="o.dog"> · {{ o.dog }}</template>
              <template v-if="o.spotsVisited.length"> · {{ o.spotsVisited.length }} spot</template>
            </div>
          </RouterLink>
        </li>
      </ul>
    </section>

    <section v-else class="card">
      <p v-if="!spots.length" class="empty">Nessuno spot. Si creano dalla mappa o salvando una valutazione.</p>
      <ul class="list">
        <li v-for="s in spots" :key="s.id">
          <RouterLink :to="`/diario/spot/${s.id}`">
            <div class="row spread">
              <strong>{{ s.name }}</strong>
              <span v-if="s.kind === 'riservato'" class="pill no">riservata</span>
              <span
                v-else-if="lastAssessment.get(s.id)?.result.classId"
                class="pill"
                :style="{ background: classOf(lastAssessment.get(s.id)!.result.classId)?.color, color: '#1b1714' }"
              >
                {{ classOf(lastAssessment.get(s.id)!.result.classId)?.label }} sul posto
              </span>
              <span v-else-if="s.remote?.score !== undefined" class="pill neutral">mappa: {{ remoteClass(s.remote.score).label }}</span>
            </div>
            <div class="small muted">
              {{ assessments.filter((a) => a.spotId === s.id).length }} valutazioni ·
              {{ outings.filter((o) => o.spotsVisited.includes(s.id)).length }} visite
            </div>
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>
