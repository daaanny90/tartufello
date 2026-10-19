<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { db, newId, nowIso, SPECIES_LABELS, type Find, type Species } from '../diary/db'
import { model } from '../field/model'
import { currentFix } from '../lib/geolocation'
import { formatCoord } from '../lib/geo'
import { dayStatus } from '../rules/calendar'
import { settings } from '../settings/settings'
import { shrinkPhoto } from '../lib/photo'

const props = defineProps<{ outingId: string }>()
const emit = defineEmits<{ saved: [find: Find]; cancel: [] }>()

const openToday = dayStatus(new Date(), settings.zone).species.filter((s) => s.open).map((s) => s.species.id)
const defaultSpecies: Species = (['uncinatum', 'aestivum'] as Species[]).find((s) => openToday.includes(s)) ?? 'aestivum'

const species = ref<Species>(defaultSpecies)
const grams = ref('')
const depth = ref('')
const host = ref('')
const notes = ref('')
const photo = ref<Blob | null>(null)
const photoUrl = ref<string | null>(null)
const position = ref<[number, number] | null>(null)
const accuracy = ref<number | null>(null)
const error = ref('')
const busy = ref(false)

async function locate() {
  error.value = ''
  try {
    const f = await currentFix(5000)
    position.value = [f.lon, f.lat]
    accuracy.value = Math.round(f.acc)
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(locate)

async function onPhoto(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  photo.value = await shrinkPhoto(file)
  if (photoUrl.value) URL.revokeObjectURL(photoUrl.value)
  photoUrl.value = URL.createObjectURL(photo.value)
}

const num = (s: string) => {
  const v = Number(s.replace(',', '.'))
  return s.trim() && Number.isFinite(v) ? v : undefined
}

async function save() {
  if (!position.value) {
    error.value = 'Serve la posizione.'
    return
  }
  busy.value = true
  const find: Find = {
    id: newId(),
    outingId: props.outingId,
    date: nowIso(),
    position: [position.value[0], position.value[1]],
    species: species.value,
    grams: num(grams.value),
    depthCm: num(depth.value),
    hostNearby: host.value || undefined,
    photo: photo.value ?? undefined,
    notes: notes.value.trim() || undefined,
  }
  await db.finds.add(find)
  busy.value = false
  emit('saved', find)
}
</script>

<template>
  <div class="card">
    <h2>Ritrovamento</h2>
    <div class="row spread small" style="margin-bottom: 10px">
      <span v-if="position">{{ formatCoord(position) }} · ±{{ accuracy }} m</span>
      <span v-else class="muted">Cerco la posizione…</span>
      <button class="ghost" @click="locate">Aggiorna</button>
    </div>
    <p v-if="error" class="banner warn small">{{ error }}</p>
    <label class="field">
      <span>Specie</span>
      <select v-model="species">
        <option v-for="(label, id) in SPECIES_LABELS" :key="id" :value="id">{{ label }}</option>
      </select>
    </label>
    <div class="row" style="flex-wrap: nowrap">
      <label class="field" style="flex: 1">
        <span>Grammi</span>
        <input v-model="grams" inputmode="decimal" />
      </label>
      <label class="field" style="flex: 1">
        <span>Profondità (cm)</span>
        <input v-model="depth" inputmode="decimal" />
      </label>
    </div>
    <label class="field">
      <span>Pianta ospite vicina</span>
      <select v-model="host">
        <option value="">Non annotata</option>
        <option v-for="h in model.hostSpecies" :key="h.id" :value="h.id">{{ h.it }}</option>
      </select>
    </label>
    <label class="field">
      <span>Foto (resta sul telefono, senza dati EXIF)</span>
      <input type="file" accept="image/*" capture="environment" @change="onPhoto" />
    </label>
    <img v-if="photoUrl" :src="photoUrl" alt="Foto del ritrovamento" class="preview" />
    <label class="field">
      <span>Note</span>
      <textarea v-model="notes" />
    </label>
    <div class="row">
      <button class="primary" :disabled="busy || !position" @click="save">Salva</button>
      <button @click="emit('cancel')">Annulla</button>
    </div>
  </div>
</template>

<style scoped>
.preview {
  width: 100%;
  max-height: 240px;
  object-fit: cover;
  border-radius: 10px;
  margin-bottom: 12px;
}
</style>
