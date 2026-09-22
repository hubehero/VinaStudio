<script setup lang="ts">
import { Check } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useMoleculeStore } from '@/stores/molecules'
import type { MoleculeItem } from '@/types/molecule'
import { getEffectiveType } from '@/types/molecule'

const props = defineProps<{ mol: MoleculeItem }>()
const store = useMoleculeStore()
const { t } = useI18n()

const isReceptor = computed(() => getEffectiveType(props.mol) === 'receptor')

/** The residues the flexible selector offers: what the last report validated. */
const availableResidues = computed(() => {
  const report = props.mol.report
  return report && 'residueList' in report ? report.residueList : []
})

const selected = computed(() => new Set(props.mol.receptorOptions.flexibleResidues))
const selectedCount = computed(() => props.mol.receptorOptions.flexibleResidues.length)

function toggleResidue(residue: string): void {
  const current = props.mol.receptorOptions.flexibleResidues
  const next = selected.value.has(residue)
    ? current.filter((r) => r !== residue)
    : [...current, residue]
  store.setFlexibleResidues(props.mol.id, next)
}

function selectAll(): void {
  store.setFlexibleResidues(props.mol.id, [...availableResidues.value])
}

function clearSelection(): void {
  store.setFlexibleResidues(props.mol.id, [])
}
</script>

<template>
  <section class="options-block">
    <h3 class="options-block__title">{{ t('molecules.options') }}</h3>

    <div class="options__grid">
      <template v-if="isReceptor">
        <label class="options__item">
          <span>{{ t('molecules.optionWaters') }}</span>
          <el-switch v-model="mol.receptorOptions.deleteWaters" size="small" />
        </label>
        <label class="options__item">
          <span>{{ t('molecules.optionHetero') }}</span>
          <el-switch v-model="mol.receptorOptions.deleteHetero" size="small" />
        </label>
        <label class="options__item">
          <span>{{ t('molecules.optionNormalise') }}</span>
          <el-switch v-model="mol.receptorOptions.normaliseAtomOrder" size="small" />
        </label>
        <label class="options__item">
          <span>{{ t('molecules.optionAllowBad') }}</span>
          <el-switch v-model="mol.receptorOptions.allowBadResidues" size="small" />
        </label>
      </template>
      <template v-else>
        <label class="options__item">
          <span>{{ t('molecules.optionOptimise') }}</span>
          <el-switch v-model="mol.ligandOptions.optimiseGeometry" size="small" />
        </label>
        <label class="options__item">
          <span>{{ t('molecules.optionAmides') }}</span>
          <el-switch v-model="mol.ligandOptions.flexibleAmides" size="small" />
        </label>
        <label class="options__item">
          <span>{{ t('molecules.optionMacrocycles') }}</span>
          <el-switch v-model="mol.ligandOptions.rigidMacrocycles" size="small" />
        </label>
        <label class="options__item">
          <span>{{ t('molecules.optionHydrate') }}</span>
          <el-switch v-model="mol.ligandOptions.hydrate" size="small" />
        </label>
        <label class="options__item options__item--wide">
          <span>{{ t('molecules.optionSeed') }}</span>
          <el-input-number
            v-model="mol.ligandOptions.embedSeed"
            size="small"
            :min="0"
            :max="2147483647"
            controls-position="right"
          />
        </label>
      </template>
    </div>

    <p v-if="isReceptor" class="vs-faint option-note">{{ t('molecules.optionNormaliseNote') }}</p>

    <div v-if="isReceptor && availableResidues.length > 0" class="flexible-section">
      <div class="flexible-header">
        <span class="flexible-label">{{ t('molecules.flexibleResidues') }}</span>
        <div class="flexible-actions">
          <el-button size="small" text @click="selectAll">{{ t('common.selectAll') }}</el-button>
          <el-button size="small" text @click="clearSelection">{{ t('common.clear') }}</el-button>
          <span class="flexible-count">{{ selectedCount }} {{ t('common.selected') }}</span>
        </div>
      </div>
      <div class="residue-grid">
        <label
          v-for="res in availableResidues"
          :key="res"
          class="residue-item"
          :class="{ 'is-selected': selected.has(res) }"
        >
          <input type="checkbox" :checked="selected.has(res)" @change="toggleResidue(res)" />
          <span class="residue-name">{{ res }}</span>
          <el-icon v-if="selected.has(res)" class="residue-check"><Check /></el-icon>
        </label>
      </div>
    </div>
  </section>
</template>

<style scoped>
.options-block {
  flex: none;
}

.options-block__title {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--vs-text-faint);
}

.options__grid {
  display: grid;
  gap: 9px;
}

.options__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12.5px;
  color: var(--vs-text-muted);
}

.options__item--wide {
  justify-content: flex-start;
}

.option-note {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.5;
}

.flexible-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--vs-border);
}

.flexible-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.flexible-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--vs-text-muted);
}

.flexible-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.flexible-count {
  font-size: 11px;
  color: var(--vs-text-faint);
}

.residue-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 4px;
  max-height: 150px;
  overflow-y: auto;
  margin-top: 8px;
  padding: 4px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  background: var(--vs-bg-sunken);
}

.residue-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border-radius: var(--vs-radius-sm);
  cursor: pointer;
  font-size: 11px;
  transition: background 0.1s;
}

.residue-item:hover {
  background: var(--vs-bg-surface);
}

.residue-item.is-selected {
  background: rgba(59, 130, 246, 0.15);
  color: var(--vs-accent);
}

.residue-item input {
  display: none;
}

.residue-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.residue-check {
  flex: none;
}
</style>
