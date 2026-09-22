<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'
import { ElButton, ElMessage } from 'element-plus'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import { useDockingStore } from '@/stores/docking'
import { useMoleculeStore } from '@/stores/molecules'
import type { InteractionData } from '@/types/api'

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

async function analyzeInteractions(): Promise<void> {
  const jobId = docking.activeJobId
  // The export endpoint numbers poses from 1; the store indexes them from 0.
  const poseNumber = docking.currentPoseIndex + 1
  if (!jobId || !docking.currentPose) return

  analyzingInteractions.value = true
  interactionError.value = null
  interactions.value = []

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

function clearInteractions(): void {
  interactions.value = []
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
        <div class="interactions__table-wrap">
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
