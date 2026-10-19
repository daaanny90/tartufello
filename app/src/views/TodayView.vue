<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { db, type Outing } from '../diary/db'
import { startOuting, tracking } from '../diary/outings'
import { calendar, dayStatus, formatDate, seasonLabel, targetStatus } from '../rules/calendar'
import { settings } from '../settings/settings'
import { formatDistance, trackLength } from '../lib/geo'

const router = useRouter()
const today = new Date()
const status = computed(() => dayStatus(today, settings.zone))
const target = computed(() => targetStatus(today, settings.zone))
const zoneLabel = computed(() => calendar.zones.find((z) => z.id === settings.zone)?.label ?? settings.zone)

const lastOuting = ref<Outing | null>(null)
const seasonFinds = ref(0)
const totalOutings = ref(0)

onMounted(async () => {
  const outings = await db.outings.orderBy('date').reverse().toArray()
  totalOutings.value = outings.length
  lastOuting.value = outings.find((o) => o.endedAt) ?? null
  const since = new Date(today.getFullYear(), 0, 1).toISOString()
  seasonFinds.value = await db.finds.where('date').aboveOrEqual(since).count()
})

const dayBefore = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate() - 1)
const days = (n: number | null) => (n === null ? '' : n === 1 ? 'domani' : `tra ${n} giorni`)

async function go() {
  const o = await startOuting()
  router.push(`/diario/uscita/${o.id}`)
}
</script>

<template>
  <div class="page">
    <div class="row spread">
      <h1>fiuto</h1>
      <span class="muted small">{{ formatDate(today) }} · {{ zoneLabel }}</span>
    </div>

    <div v-if="!status.inValidity" class="banner bad">
      Il calendario caricato vale per il {{ calendar.validYears.from }}-{{ calendar.validYears.to }}. Oggi è fuori: controlla la delibera nuova.
    </div>

    <div v-if="status.suspension" class="banner bad">
      <strong>{{ status.suspension.label }}.</strong> Niente ricerca né raccolta fino al {{ status.suspension.to.split('-').reverse().join('/') }}.
    </div>

    <section class="card hero" :class="target.open ? 'open' : 'closed'">
      <div class="small muted">Tartufo nero (T. aestivum / uncinatum)</div>
      <div class="state">{{ target.open ? 'Aperto' : 'Chiuso' }}</div>
      <p v-if="target.open && target.until">
        {{ target.forms.map((s) => s.common).join(', ') }}, fino al {{ formatDate(dayBefore(target.until)) }}.
      </p>
      <p v-else-if="target.from">
        Riapre il {{ formatDate(target.from) }} ({{ days(status.species.find((s) => s.species.id === target.forms[0]?.id)?.daysToChange ?? null) }})
        con {{ target.forms[0]?.common.toLowerCase() }}.
      </p>
      <div class="row">
        <button v-if="!tracking.outingId" class="primary" :disabled="!!status.suspension" @click="go">Inizia uscita</button>
        <RouterLink v-else class="btn primary" :to="`/diario/uscita/${tracking.outingId}`">Uscita in corso</RouterLink>
        <RouterLink class="btn" to="/campo">Valuta qui</RouterLink>
        <RouterLink class="btn" to="/mappa">Mappa</RouterLink>
      </div>
    </section>

    <section class="card">
      <div class="row spread">
        <h2>Calendario di oggi</h2>
        <RouterLink to="/regole" class="small">Regole</RouterLink>
      </div>
      <table>
        <tbody>
          <tr v-for="s in status.species" :key="s.species.id">
            <td>
              <strong>{{ s.species.common }}</strong>
              <div class="small muted"><i>{{ s.species.latin }}</i> · {{ seasonLabel(s.species, settings.zone) }}</div>
            </td>
            <td style="text-align: right; white-space: nowrap">
              <span class="pill" :class="s.open ? 'ok' : 'no'">{{ s.open ? 'aperto' : 'chiuso' }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!calendar.verified" class="small muted" style="margin-top: 8px">
        Date trascritte dal brief, non ancora confrontate con la delibera. Vedi Regole.
      </p>
    </section>

    <section class="card">
      <h2>Stagione</h2>
      <p class="muted" v-if="!totalOutings">Nessuna uscita registrata. Anche i giri a vuoto contano: sono i dati che servono a tarare la mappa.</p>
      <template v-else>
        <p>{{ totalOutings }} uscite registrate, {{ seasonFinds }} ritrovamenti da gennaio.</p>
        <p v-if="lastOuting" class="small muted">
          Ultima: {{ formatDate(new Date(lastOuting.date)) }}, {{ formatDistance(trackLength(lastOuting.track)) }}.
          <RouterLink :to="`/diario/uscita/${lastOuting.id}`">Apri</RouterLink>
        </p>
      </template>
      <p v-if="!settings.licenseNumber" class="small muted">
        Tesserino non segnato. <RouterLink to="/impostazioni">Aggiungilo</RouterLink> per averlo a portata in bosco.
      </p>
    </section>
  </div>
</template>

<style scoped>
.hero .state {
  font-size: 2.2rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 2px 0 6px;
}

.hero.open .state {
  color: var(--ok);
}

.hero.closed .state {
  color: var(--bad);
}
</style>
