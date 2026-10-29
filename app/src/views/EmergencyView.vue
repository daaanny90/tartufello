<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { DANGER_RADIUS_M } from '../diary/danger'
import { db, HAZARD_LABELS, newId, nowIso } from '../diary/db'
import { currentFix } from '../lib/geolocation'
import poison from '../rules/esche-avvelenate.json'
import { settings } from '../settings/settings'

const router = useRouter()

const CONTACTS = [
  { key: 'vetPhone', label: 'Veterinario' },
  { key: 'clinicPhone', label: 'Clinica veterinaria h24' },
  { key: 'aslPhone', label: 'Servizio veterinario ASL' },
] as const

const saved = computed(() => CONTACTS.filter((c) => settings[c.key].trim()))
// Si parte in modifica solo se non c'è niente: digitando il primo numero il campo non deve sparire.
const editing = ref(!saved.value.length)
const tel = (n: string) => `tel:${n.replace(/[^\d+]/g, '')}`
const host = (u: string) => new URL(u).hostname

function back() {
  if (window.history.state?.back) router.back()
  else router.push('/')
}

const marking = ref(false)
const marked = ref<string | null>(null)
const markError = ref('')

/** Nell'emergenza basta una lettura: niente media di 8 secondi. La precisione finisce nelle note. */
async function markHere() {
  marking.value = true
  markError.value = ''
  try {
    const f = await currentFix()
    const id = newId()
    await db.spots.add({
      id,
      name: HAZARD_LABELS.esca,
      kind: 'pericolo',
      hazard: 'esca',
      geom: { type: 'Point', coordinates: [f.lon, f.lat] },
      notes: `Segnato da Emergenza, GPS ±${Math.round(f.acc)} m.`,
      createdAt: nowIso(),
    })
    marked.value = id
  } catch (e) {
    markError.value = (e as Error).message
  } finally {
    marking.value = false
  }
}
</script>

<template>
  <div class="page">
    <a href="#" class="small" @click.prevent="back">← Indietro</a>
    <h1 style="margin-top: 8px">Emergenza cane</h1>

    <section class="card">
      <h2>Chiama</h2>
      <div v-if="saved.length" class="stack">
        <a v-for="c in saved" :key="c.key" class="btn wide call" :href="tel(settings[c.key])">
          <span>{{ c.label }}</span><strong>{{ settings[c.key] }}</strong>
        </a>
      </div>
      <p v-else class="banner warn small">Nessun numero salvato. Mettili adesso, da casa: in bosco non c'è tempo di cercarli.</p>
      <template v-if="editing">
        <label v-for="c in CONTACTS" :key="c.key" class="field">
          <span>{{ c.label }}</span>
          <input v-model.trim="settings[c.key]" type="tel" inputmode="tel" autocomplete="off" />
        </label>
        <p class="small muted">Restano su questo telefono e finiscono nel backup cifrato.</p>
        <button @click="editing = false">Fatto</button>
      </template>
      <button v-else class="ghost small" @click="editing = true">Modifica numeri</button>
    </section>

    <section class="card">
      <h2>Se ha mangiato qualcosa</h2>
      <ol>
        <li v-for="s in poison.firstAid.steps" :key="s">{{ s }}</li>
      </ol>
      <p class="small muted">{{ poison.firstAid.note }}</p>
      <button class="primary" :disabled="marking" @click="markHere">{{ marking ? 'Cerco la posizione…' : 'Segna qui il pericolo' }}</button>
      <p v-if="marked" class="banner ok small" style="margin-top: 10px">
        Segnato. <RouterLink :to="`/diario/spot/${marked}`">Apri lo spot</RouterLink> per cambiare tipo o aggiungere note.
      </p>
      <p v-if="markError" class="banner bad small" style="margin-top: 10px">{{ markError }}</p>
    </section>

    <section class="card">
      <h2>Se trovi un'esca</h2>
      <ul>
        <li v-for="s in poison.baitFound" :key="s">{{ s }}</li>
      </ul>
      <p class="small">
        Sulla mappa: tocca il punto → <strong>Segna pericolo</strong>. Con il GPS acceso (uscita in corso o mappa aperta) l'app avvisa e vibra quando sei a meno di
        {{ DANGER_RADIUS_M }} m. Sull'iPhone non vibra; a schermo spento non avvisa.
      </p>
    </section>

    <section class="card">
      <h2>Segnalazione</h2>
      <p v-if="!poison.verified" class="banner warn small">{{ poison.verificationNote }}</p>
      <ul>
        <li v-for="r in poison.reporting" :key="r">{{ r }}</li>
      </ul>
      <p class="small muted">{{ poison.legalBasis }}. {{ poison.validityNote }}</p>
      <p class="small muted">
        Fonti secondarie:
        <template v-for="(u, i) in poison.secondarySources" :key="u"
          ><template v-if="i">, </template><a :href="u" target="_blank" rel="noopener">{{ host(u) }}</a></template
        >.
      </p>
    </section>
  </div>
</template>

<style scoped>
.call {
  justify-content: space-between;
  background: var(--bad);
  border-color: var(--bad);
  color: #ffffff;
  font-size: 1.05rem;
}

ol,
ul {
  padding-left: 1.2rem;
  margin: 0 0 0.75rem;
}

li + li {
  margin-top: 4px;
}
</style>
