<script setup lang="ts">
import { ArrowLeft, ArrowRight, Download } from '@element-plus/icons-vue'
import { ElButton, ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import { downloadTextFile } from '@/utils/download'
import { useDockingStore } from '@/stores/docking'

const { t } = useI18n()
const docking = useDockingStore()

async function downloadCsv(): Promise<void> {
  if (!docking.activeJobId) return
  try {
    const result = await api.exportCsv(docking.activeJobId)
    downloadTextFile(result.csv, result.filename, 'text/csv')
  } catch {
    ElMessage.error(t('docking.errorExportCsv'))
  }
}

async function exportSinglePose(poseIndex: number): Promise<void> {
  if (!docking.activeJobId) return
  try {
    const result = await api.exportPose(docking.activeJobId, poseIndex)
    if (result.sdf) {
      downloadTextFile(result.sdf, `pose_${poseIndex}.sdf`, 'chemical/x-mdl-sdfile')
    } else if (result.pdbqt) {
      downloadTextFile(result.pdbqt, `pose_${poseIndex}.pdbqt`, 'chemical/x-pdbqt')
    }
  } catch {
    ElMessage.error(t('docking.errorExportPose'))
  }
}
</script>

<template>
  <div v-if="docking.hasResult && docking.poses.length > 0" class="vs-card">
    <div class="vs-card__header">
      <div><div class="vs-card__title">{{ t('docking.results') }}</div></div>
      <ElButton size="small" :icon="Download" @click="downloadCsv">
        {{ t('docking.exportCsv') }}
      </ElButton>
    </div>
    <div class="vs-card__body">
      <!-- Pose Navigator -->
      <div class="pose-nav">
        <ElButton
          size="small"
          :icon="ArrowLeft"
          :disabled="docking.currentPoseIndex === 0"
          @click="docking.prevPose()"
        />
        <div class="pose-nav__info">
          <span class="pose-nav__label">{{ t('docking.poseNavigator.pose') }}</span>
          <span class="pose-nav__index">
            {{ docking.currentPoseIndex + 1 }} / {{ docking.poses.length }}
          </span>
          <span v-if="docking.currentPose" class="pose-nav__energy">
            {{ docking.currentPose.affinity.toFixed(2) }} kcal/mol
          </span>
        </div>
        <ElButton
          size="small"
          :icon="ArrowRight"
          :disabled="docking.currentPoseIndex >= docking.poses.length - 1"
          @click="docking.nextPose()"
        />
      </div>

      <div class="pose-table-wrap">
        <table class="pose-table">
          <thead>
            <tr>
              <th>{{ t('docking.poseTable.pose') }}</th>
              <th>{{ t('docking.poseTable.affinity') }}</th>
              <th>{{ t('docking.poseTable.rmsdLb') }}</th>
              <th>{{ t('docking.poseTable.rmsdUb') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="pose in docking.poses"
              :key="pose.index"
              :class="{ 'pose-row--active': pose.index === docking.currentPose?.index }"
              @click="docking.selectPose(pose.index - 1)"
            >
              <td>{{ pose.index }}</td>
              <td :class="{ 'is-best': docking.bestAffinity !== null && pose.affinity === docking.bestAffinity }">
                {{ pose.affinity.toFixed(2) }}
              </td>
              <td>{{ pose.rmsdLower.toFixed(2) }}</td>
              <td>{{ pose.rmsdUpper.toFixed(2) }}</td>
              <td>
                <ElButton size="small" link @click.stop="exportSinglePose(pose.index)">
                  {{ t('docking.exportPose') }}
                </ElButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pose-table-wrap {
  overflow: auto;
  max-height: 300px;
}

.pose-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.pose-table th,
.pose-table td {
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid var(--vs-border);
}

.pose-table th {
  font-weight: 600;
  color: var(--vs-text-muted);
  position: sticky;
  top: 0;
  background: var(--vs-bg-surface);
}

.is-best {
  color: var(--vs-accent);
  font-weight: 600;
}

.pose-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 0;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--vs-border);
}

.pose-nav__info {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 160px;
  justify-content: center;
}

.pose-nav__label {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.pose-nav__index {
  font-size: 14px;
  font-weight: 600;
  color: var(--vs-text);
}

.pose-nav__energy {
  font-size: 12px;
  color: var(--vs-accent);
  font-weight: 500;
}

.pose-row--active td {
  background: var(--vs-bg-sunken);
}

.pose-table tbody tr {
  cursor: pointer;
}

.pose-table tbody tr:hover td {
  background: var(--vs-bg-sunken);
}
</style>
