<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'
import { ElButton, ElMessage } from 'element-plus'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import { useDockingStore } from '@/stores/docking'
import { useMoleculeStore } from '@/stores/molecules'
import type { DepictData, InteractionData } from '@/types/api'

import Interactions2D from './Interactions2D.vue'

/**
 * The rows shown in the table and drawn as annotations on the viewport.
 * The parent owns the list because the viewport consumes it.
 */
const interactions = defineModel<InteractionData[]>({ required: true })

const { t } = useI18n()
const docking = useDockingStore()
const molecules = useMoleculeStore()

/**
 * Search radius handed to the interaction analysis. It must cover the widest
 * rule the backend applies (hydrophobic and ionic: 4 A), otherwise pairs are
 * filtered out before they can be classified.
 */
const INTERACTION_RADIUS = 4.0

const analyzingInteractions = ref(false)
const interactionError = ref<string | null>(null)

/**
 * The 2D map and the residue filter. `fullInteractions` keeps the complete
 * analysis while the model above may show a filtered subset — the map itself
 * always renders the full picture so selecting a residue cannot collapse it.
 */
const depict = ref<DepictData | null>(null)
const fullInteractions = ref<InteractionData[]>([])
const view = ref<'table' | '2d'>('table')
const selectedResidue = ref<string | null>(null)
const map2d = ref<{ exportSvg: () => void } | null>(null)

async function analyzeInteractions(): Promise<void> {
  const jobId = docking.activeJobId
  // The export endpoint numbers poses from 1; the store indexes them from 0.
  const poseNumber = docking.currentPoseIndex + 1
  if (!jobId || !docking.currentPose) return

  analyzingInteractions.value = true
  interactionError.value = null
  interactions.value = []
  fullInteractions.value = []
  depict.value = null
  selectedResidue.value = null
  view.value = 'table'

  try {
    const receptorPath = molecules.receptorPdbqtPath
    if (!receptorPath) {
      throw new Error('Receptor PDBQT not found')
    }

    // Analyse the pose the user selected. The ligand as prepared sits wherever
    // it was built, so its contacts would describe a different geometry.
    const pose = await api.exportPose(jobId, poseNumber)

    const result = await api.analyzeInteractions({
      receptorPath,
      ligandPdbqtString: pose.pdbqt,
      distanceCutoff: INTERACTION_RADIUS,
    })

    interactions.value = result.interactions
    fullInteractions.value = result.interactions
    depict.value = result.depict
    // One click, the map: open the 2D view as soon as there is something to draw.
    if (result.depict && result.interactions.length > 0) {
      view.value = '2d'
    }
    if (result.interactions.length === 0) {
      ElMessage.info(t('docking.interactions.noneFound'))
    }
  } catch (cause) {
    interactionError.value = cause instanceof Error ? cause.message : String(cause)
    ElMessage.error(t('docking.interactions.error'))
  } finally {
    analyzingInteractions.value = false
  }
}

/**
 * Display residue as ``ILE 208:A`` when sequence number and chain are present,
 * falling back to the bare resname for SDF ligand atoms which carry none.
 */
function formatResidue(inter: InteractionData): string {
  const parts: string[] = [inter.receptorResidue]
  if (inter.receptorResSeq) parts.push(inter.receptorResSeq)
  if (inter.receptorChain) parts.push(`:${inter.receptorChain}`)
  return parts.join(' ')
}

function residueKey(inter: InteractionData): string {
  return `${inter.receptorChain}|${inter.receptorResSeq}|${inter.receptorResidue}`
}

/**
 * Residue click from the map: filter the table and the viewport annotations to
 * that residue (the viewport redraws the model list it is given). Clicking the
 * same residue again clears the filter.
 */
function selectResidue(key: string): void {
  if (selectedResidue.value === key) {
    clearResidueFilter()
    return
  }
  selectedResidue.value = key
  interactions.value = fullInteractions.value.filter((row) => residueKey(row) === key)
}

function clearResidueFilter(): void {
  selectedResidue.value = null
  interactions.value = fullInteractions.value
}

const selectedResidueLabel = computed(() => {
  if (!selectedResidue.value) return ''
  const row = fullInteractions.value.find((item) => residueKey(item) === selectedResidue.value)
  return row ? formatResidue(row) : ''
})

function clearInteractions(): void {
  interactions.value = []
  fullInteractions.value = []
  depict.value = null
  selectedResidue.value = null
  view.value = 'table'
  interactionError.value = null
}
</script>

<template>
  <div v-if="docking.isCompleted" class="vs-card">
    <div class="vs-card__header">
      <div><div class="vs-card__title">{{ t('docking.interactions.title') }}</div></div>
      <div class="interactions__actions">
        <ElButton
          size="small"
          :icon="Connection"
          :loading="analyzingInteractions"
          @click="analyzeInteractions"
        >
          {{ t('docking.interactions.analyze') }}
        </ElButton>
        <ElButton
          v-if="interactions.length > 0"
          size="small"
          @click="clearInteractions"
        >
          {{ t('docking.interactions.clear') }}
        </ElButton>
        <ElButton
          v-if="depict && interactions.length > 0"
          size="small"
          @click="view = view === '2d' ? 'table' : '2d'"
        >
          {{ view === '2d' ? t('docking.interactions2d.viewTable') : t('docking.interactions2d.view2d') }}
        </ElButton>
        <ElButton
          v-if="view === '2d' && depict && interactions.length > 0"
          size="small"
          @click="map2d?.exportSvg()"
        >
          {{ t('docking.interactions2d.exportSvg') }}
        </ElButton>
      </div>
    </div>
    <div class="vs-card__body">
      <div v-if="interactionError" class="interactions__error">
        {{ interactionError }}
      </div>
      <div v-else-if="interactions.length === 0 && !analyzingInteractions" class="interactions__empty">
        {{ t('docking.interactions.empty') }}
      </div>
      <div v-else-if="interactions.length > 0" class="interactions__list">
        <div class="interactions__summary">
          {{ t('docking.interactions.found', { count: interactions.length }) }}
        </div>
        <div v-if="selectedResidue" class="interactions__chip">
          <span>
            {{ t('docking.interactions2d.filterNote', { residue: selectedResidueLabel }) }}
          </span>
          <ElButton size="small" link type="primary" @click="clearResidueFilter">
            {{ t('docking.interactions2d.clearFilter') }}
          </ElButton>
        </div>
        <div v-if="!depict" class="interactions__note">
          {{ t('docking.interactions2d.noDepict') }}
        </div>
        <Interactions2D
          v-if="view === '2d' && depict"
          ref="map2d"
          :interactions="fullInteractions"
          :depict="depict"
          :selected-key="selectedResidue"
          @select-residue="selectResidue"
        />
        <div v-else class="interactions__table-wrap">
          <table class="interactions__table">
            <thead>
              <tr>
                <th>{{ t('docking.interactions.table.type') }}</th>
                <th>{{ t('docking.interactions.table.residue') }}</th>
                <th>{{ t('docking.interactions.table.distance') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(inter, idx) in interactions" :key="idx">
                <td>
                  <span class="interactions__type-badge" :class="`interactions__type-badge--${inter.type}`">
                    {{ t(`docking.interactions.types.${inter.type}`) }}
                  </span>
                </td>
                <td>{{ formatResidue(inter) }}</td>
                <td>{{ inter.distance.toFixed(2) }} Å</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.interactions__actions {
  display: flex;
  gap: 8px;
}

.interactions__error {
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: var(--vs-radius);
  color: #ef4444;
  font-size: 12.5px;
}

.interactions__empty {
  padding: 12px;
  text-align: center;
  color: var(--vs-text-muted);
  font-size: 12.5px;
}

.interactions__summary {
  margin-bottom: 8px;
  font-size: 12.5px;
  color: var(--vs-text-muted);
}

.interactions__chip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding: 4px 8px;
  border-radius: var(--vs-radius);
  background: rgba(22, 119, 255, 0.08);
  font-size: 12.5px;
  color: var(--vs-text);
}

.interactions__note {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.interactions__table-wrap {
  overflow: auto;
  max-height: 250px;
}

.interactions__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.interactions__table th,
.interactions__table td {
  padding: 5px 8px;
  text-align: left;
  border-bottom: 1px solid var(--vs-border);
}

.interactions__table th {
  font-weight: 600;
  color: var(--vs-text-muted);
  position: sticky;
  top: 0;
  background: var(--vs-bg-surface);
}

.interactions__type-badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
}

.interactions__type-badge--hydrogen_bond {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.interactions__type-badge--hydrophobic {
  background: rgba(168, 85, 247, 0.15);
  color: #a855f7;
}

.interactions__type-badge--ionic {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}
</style>
