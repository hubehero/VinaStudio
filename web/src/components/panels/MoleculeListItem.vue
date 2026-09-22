<script setup lang="ts">
import { Close } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { MoleculeItem } from '@/types/molecule'
import { getEffectiveType } from '@/types/molecule'

const props = defineProps<{
  molecule: MoleculeItem
  active: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  remove: [id: string]
}>()

const { t } = useI18n()

const typeLabel = computed(() => {
  const type = getEffectiveType(props.molecule)
  if (type === 'receptor') return t('molecules.typeReceptor')
  if (type === 'ligand') return t('molecules.typeLigand')
  return t('molecules.typeUnknown')
})

const typeClass = computed(() => `is-${getEffectiveType(props.molecule)}`)

const formatTag = computed(() => props.molecule.name.split('.').pop()?.toUpperCase() ?? '?')

const statusClass = computed(() => {
  const s = props.molecule.status
  if (s === 'prepared') return 'is-ok'
  if (s === 'error') return 'is-error'
  if (s === 'inspecting' || s === 'preparing') return 'is-warn'
  return 'is-idle'
})

const statusLabel = computed(() => t(`molecules.status.${props.molecule.status}`))

const removeLabel = computed(() => `${t('molecules.remove')}: ${props.molecule.name}`)

function select(): void {
  emit('select', props.molecule.id)
}

/** Arrow keys move between rows, so the list can be walked without a mouse. */
function focusSibling(offset: number): void {
  const rows = Array.from(
    document.querySelectorAll<HTMLButtonElement>('[data-molecule-row]'),
  )
  const index = rows.indexOf(document.activeElement as HTMLButtonElement)
  const next = rows[index + offset]
  if (next) next.focus()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    focusSibling(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    focusSibling(-1)
  }
}
</script>

<template>
  <li class="mol-row" :class="{ 'is-active': active }">
    <button
      type="button"
      class="mol-row__main"
      data-molecule-row
      :aria-current="active ? 'true' : undefined"
      :title="molecule.name"
      @click="select"
      @keydown="onKeydown"
    >
      <span class="mol-row__name">{{ molecule.name }}</span>
      <span class="mol-row__meta">
        <span class="mol-row__format">{{ formatTag }}</span>
        <span class="mol-row__type" :class="typeClass">{{ typeLabel }}</span>
        <span class="mol-row__status" :class="statusClass">
          <span class="mol-row__dot" />
          {{ statusLabel }}
        </span>
      </span>
    </button>

    <button
      type="button"
      class="mol-row__remove"
      :aria-label="removeLabel"
      :title="removeLabel"
      @click="emit('remove', molecule.id)"
    >
      <el-icon :size="12"><Close /></el-icon>
    </button>
  </li>
</template>

<style scoped>
.mol-row {
  display: flex;
  align-items: stretch;
  border-radius: var(--vs-radius-sm);
  transition: background 0.12s ease;
}

.mol-row:hover {
  background: var(--vs-bg-sunken);
}

.mol-row.is-active {
  background: color-mix(in srgb, var(--vs-accent) 12%, transparent);
  box-shadow: inset 2px 0 0 var(--vs-accent);
}

.mol-row__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 4px 7px 10px;
  border: none;
  background: none;
  text-align: left;
  font: inherit;
  color: inherit;
  cursor: pointer;
  border-radius: var(--vs-radius-sm);
}

.mol-row__main:focus-visible {
  outline: 2px solid var(--vs-accent);
  outline-offset: -2px;
}

.mol-row__name {
  font-size: 12.5px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mol-row.is-active .mol-row__name {
  color: var(--vs-accent);
  font-weight: 600;
}

.mol-row__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  color: var(--vs-text-faint);
}

.mol-row__format {
  padding: 0 4px;
  border-radius: 3px;
  border: 1px solid var(--vs-border);
  background: var(--vs-bg-app);
  font-family: var(--vs-font-mono);
  font-size: 9px;
  letter-spacing: 0.02em;
}

.mol-row__type.is-receptor {
  color: var(--vs-accent);
}

.mol-row__type.is-ligand {
  color: var(--vs-warning);
}

.mol-row__status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.mol-row__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--vs-text-faint);
  flex: none;
}

.mol-row__status.is-ok .mol-row__dot {
  background: var(--vs-success);
}

.mol-row__status.is-error .mol-row__dot {
  background: var(--vs-danger);
}

.mol-row__status.is-warn .mol-row__dot {
  background: var(--vs-warning);
  animation: mol-pulse 1.6s ease-in-out infinite;
}

@keyframes mol-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.mol-row__remove {
  flex: none;
  width: 26px;
  display: grid;
  place-items: center;
  border: none;
  background: none;
  color: var(--vs-text-faint);
  cursor: pointer;
  border-radius: var(--vs-radius-sm);
  opacity: 0;
  transition: opacity 0.12s ease, color 0.12s ease;
}

.mol-row:hover .mol-row__remove,
.mol-row__remove:focus-visible {
  opacity: 1;
}

.mol-row__remove:hover {
  color: var(--vs-danger);
}

.mol-row__remove:focus-visible {
  outline: 2px solid var(--vs-accent);
  outline-offset: -2px;
}
</style>
