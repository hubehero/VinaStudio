<script setup lang="ts">
import type { MoleculeItem } from '@/types/molecule'

import MoleculeListItem from './MoleculeListItem.vue'

defineProps<{
  title: string
  items: MoleculeItem[]
  activeId: string | null
}>()

const emit = defineEmits<{
  select: [id: string]
  remove: [id: string]
}>()
</script>

<template>
  <section v-if="items.length > 0" class="mol-section">
    <h3 class="mol-section__title">
      {{ title }}
      <span class="mol-section__count">{{ items.length }}</span>
    </h3>
    <ul class="mol-section__list">
      <MoleculeListItem
        v-for="item in items"
        :key="item.id"
        :molecule="item"
        :active="item.id === activeId"
        @select="emit('select', $event)"
        @remove="emit('remove', $event)"
      />
    </ul>
  </section>
</template>

<style scoped>
.mol-section + .mol-section {
  margin-top: 10px;
}

.mol-section__title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--vs-text-faint);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.mol-section__count {
  padding: 0 5px;
  border-radius: 999px;
  background: var(--vs-bg-sunken);
  border: 1px solid var(--vs-border);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.mol-section__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
</style>
