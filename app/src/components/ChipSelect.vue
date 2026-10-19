<script setup lang="ts">
defineProps<{ options: { id: string; label: string }[]; modelValue: string | undefined }>()
const emit = defineEmits<{ 'update:modelValue': [value: string | undefined] }>()
</script>

<template>
  <div class="chips">
    <button
      v-for="o in options"
      :key="o.id"
      type="button"
      class="chip"
      :class="{ on: modelValue === o.id }"
      @click="emit('update:modelValue', modelValue === o.id ? undefined : o.id)"
    >
      {{ o.label }}
    </button>
  </div>
</template>
