<script setup lang="ts">
import { Check } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import SequenceView from '@/components/panels/SequenceView.vue'
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

/** Solvent groups offered by the preview; the keep field accepts their keys. */
const solventGroups = computed(() => {
  const preview = props.mol.preview
  if (!preview || !('waters' in preview)) return []
  return [...preview.waters, ...preview.hetero]
})

const keepText = computed(() =>
  (props.mol.receptorOptions.keepResidues ?? []).join(', '),
)

function updateKeep(value: string): void {
  const keys = value
    .split(/[,;\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  store.setKeepResidues(props.mol.id, [...new Set(keys)])
}

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

// -- sequence picker (TASK-12) ---------------------------------------------

const sequenceOpen = ref(false)

/** Chains for the drawer; an empty list makes the view report "no sequence". */
const sequenceChains = computed(() => {
  const preview = props.mol.preview
  if (!preview || !('sequence' in preview)) return []
  return preview.sequence?.chains ?? []
})

function parseKey(key: string): [chainId: string, seqId: number] | null {
  const sep = key.indexOf(':')
  if (sep <= 0) return null
  return [key.slice(0, sep), Number(key.slice(sep + 1))]
}

/**
 * Row-major closed interval unioned into the flexible set (§4: every cell in
 * the range becomes selected, never inverted). A cross-chain Shift click
 * takes each chain's own segment of the path; HETATM cells are never keys.
 */
function applySequenceRange(from: string, to: string): void {
  const chains = sequenceChains.value
  const start = parseKey(from)
  const end = parseKey(to)
  if (!start || !end) return
  const flat: { chainId: string; seqId: number; het: boolean }[] = []
  for (const chain of chains) {
    for (const residue of chain.residues) {
      flat.push({ chainId: chain.id, seqId: residue.seqId, het: residue.het })
    }
  }
  const fromIndex = flat.findIndex((e) => e.chainId === start[0] && e.seqId === start[1])
  const toIndex = flat.findIndex((e) => e.chainId === end[0] && e.seqId === end[1])
  if (fromIndex < 0 || toIndex < 0) return
  const lo = Math.min(fromIndex, toIndex)
  const hi = Math.max(fromIndex, toIndex)
  const next = new Set(props.mol.receptorOptions.flexibleResidues)
  for (let i = lo; i <= hi; i++) {
    const entry = flat[i]!
    if (!entry.het) next.add(`${entry.chainId}:${entry.seqId}`)
  }
  store.setFlexibleResidues(props.mol.id, [...next])
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
        <label class="options__item options__item--wide options__item--keep">
          <span>{{ t('molecules.optionKeep') }}</span>
          <el-input
            :model-value="keepText"
            size="small"
            :placeholder="t('molecules.optionKeepPlaceholder')"
            @update:model-value="updateKeep"
          />
        </label>
        <p class="vs-faint option-note">
          {{ t('molecules.optionKeepNote', { n: solventGroups.length }) }}
        </p>
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
          <el-button size="small" text @click="sequenceOpen = true">
            {{ t('molecules.sequence.pickFromSequence') }}
          </el-button>
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

    <el-drawer v-model="sequenceOpen" direction="rtl" size="60%">
      <template #header>
        <div class="sequence-drawer__head">
          <span>{{ t('molecules.sequence.pickFromSequence') }}</span>
          <span class="sequence-drawer__count">
            {{ t('molecules.sequence.selectedCount', { n: selectedCount }) }}
          </span>
        </div>
      </template>
      <SequenceView
        :chains="sequenceChains"
        :selected="selected"
        @toggle="toggleResidue"
        @toggle-range="applySequenceRange"
      />
    </el-drawer>
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

.options__item--keep {
  align-items: flex-start;
}

.options__item--keep :deep(.el-input) {
  flex: 1;
  min-width: 0;
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

.sequence-drawer__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.sequence-drawer__count {
  font-size: 12px;
  color: var(--vs-text-faint);
}

/* The drawer body gives the component a real height so its own overflow
 * (both axes, per the design) scrolls instead of the drawer. */
.el-drawer__body .sequence-view {
  height: 100%;
}
</style>
