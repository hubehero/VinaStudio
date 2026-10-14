<script setup lang="ts">
import { ref } from 'vue'

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

/** Sections start expanded; collapsing is how a long ligand list is tamed. */
const collapsed = ref(false)
</script>

<template>
  <section v-if="items.length > 0" class="mol-section">
    <button
      type="button"
      class="mol-section__header"
      :aria-expanded="!collapsed"
      @click="collapsed = !collapsed"
    >
      <span class="mol-section__arrow">{{ collapsed ? '▸' : '▾' }}</span>
      <span class="mol-section__title">{{ title }}</span>
      <span class="mol-section__count">{{ items.length }}</span>
    </button>
    <ul v-show="!collapsed" class="mol-section__list">
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

.mol-section__header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  margin: 0;
  padding: 6px 10px;
  border: none;
  border-radius: var(--vs-radius-sm);
  background: none;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.mol-section__header:hover {
  background: var(--vs-bg-sunken);
}

.mol-section__header:focus-visible {
  outline: 2px solid var(--vs-accent);
  outline-offset: -2px;
}

.mol-section__arrow {
  width: 10px;
  font-size: 10px;
  color: var(--vs-text-faint);
}

.mol-section__title {
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
