<script setup lang="ts">
import { CircleCheckFilled, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import StatusPill from '@/components/StatusPill.vue'
import { useSystemStore } from '@/stores/system'
import type { PackageCheck } from '@/types/api'

const system = useSystemStore()
const { t } = useI18n()

onMounted(() => {
  if (!system.info) {
    void system.refresh()
  }
})

const runtimeRows = computed(() => {
  const runtime = system.info?.runtime
  return [
    { label: t('environment.python'), value: runtime?.python ?? t('common.unknown') },
    {
      label: t('environment.platform'),
      value: runtime ? `${runtime.platform} ${runtime.platformRelease}` : t('common.unknown'),
    },
    { label: t('environment.machine'), value: runtime?.machine ?? t('common.unknown') },
    { label: t('environment.home'), value: system.info?.home ?? t('common.unknown') },
  ]
})

const packageRows = computed<PackageCheck[]>(() => system.selfCheck?.checks ?? [])

function declaredVersion(name: string): string {
  return system.info?.packages?.[name] ?? t('environment.notDeclared')
}

function importState(row: PackageCheck): 'ok' | 'error' {
  return row.importable ? 'ok' : 'error'
}

const dockingState = computed<'ok' | 'error' | 'idle'>(() => {
  if (!system.selfCheck) return 'idle'
  return system.selfCheck.dockingAvailable ? 'ok' : 'error'
})

const dockingLabel = computed(() => {
  if (!system.selfCheck) return t('environment.selfCheckIdle')
  return system.selfCheck.dockingAvailable
    ? t('environment.dockingReady')
    : t('environment.dockingMissing', { packages: system.selfCheck.failed.join(', ') })
})
</script>

<template>
  <div class="vs-page">
    <div class="vs-page__head">
      <div>
        <h1 class="vs-page__title">{{ t('environment.title') }}</h1>
        <p class="vs-page__subtitle">{{ t('environment.subtitle') }}</p>
      </div>
      <el-button
        type="primary"
        :loading="system.checking"
        :icon="Refresh"
        @click="system.runSelfCheck()"
      >
        {{ system.checking ? t('environment.running') : t('environment.runSelfCheck') }}
      </el-button>
    </div>

    <el-alert v-if="system.error" type="error" :closable="false" show-icon :title="system.error" />

    <div class="env-grid">
      <div class="vs-card">
        <div class="vs-card__header">
          <div class="vs-card__title">{{ t('environment.runtime') }}</div>
          <StatusPill
            :state="system.reachable ? 'ok' : 'error'"
            :label="system.health ? `API ${system.health.version}` : t('status.disconnected')"
          />
        </div>
        <div class="vs-card__body">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item
              v-for="row in runtimeRows"
              :key="row.label"
              :label="row.label"
            >
              <span class="vs-mono">{{ row.value }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </div>

      <div class="vs-card">
        <div class="vs-card__header">
          <div class="vs-card__title">{{ t('environment.dockingAvailable') }}</div>
        </div>
        <div class="vs-card__body">
          <div class="docking" :class="`is-${dockingState}`">
            <el-icon class="docking__icon">
              <WarningFilled v-if="dockingState === 'error'" />
              <CircleCheckFilled v-else />
            </el-icon>
            <span>{{ dockingLabel }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="vs-card">
      <div class="vs-card__header">
        <div>
          <div class="vs-card__title">{{ t('environment.dependencies') }}</div>
          <div class="vs-card__subtitle">{{ t('environment.selfCheckHint') }}</div>
        </div>
      </div>
      <div class="vs-card__body">
        <el-table
          v-if="packageRows.length"
          :data="packageRows"
          size="small"
          :border="false"
          row-key="distribution"
        >
          <el-table-column prop="distribution" label="Package" min-width="110" />
          <el-table-column :label="t('environment.declared')" min-width="130">
            <template #default="{ row }">
              <span class="vs-mono">{{ declaredVersion(row.distribution) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('environment.importable')" width="150">
            <template #default="{ row }">
              <StatusPill
                :state="importState(row)"
                :label="row.importable ? t('environment.importable') : t('environment.failedImport')"
              />
            </template>
          </el-table-column>
          <el-table-column :label="t('environment.loaded')" width="120" align="right">
            <template #default="{ row }">
              <span class="vs-mono">{{ t('common.milliseconds', { value: row.importMs }) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Detail" min-width="200">
            <template #default="{ row }">
              <span class="vs-faint detail">{{ row.error ?? '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else :description="t('environment.noCheckResults')" :image-size="72" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.env-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 16px;
}

.docking {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 13.5px;
  font-weight: 600;
}

.docking__icon {
  font-size: 18px;
}

.docking.is-ok {
  color: var(--vs-success);
}

.docking.is-error {
  color: var(--vs-danger);
}

.docking.is-idle {
  color: var(--vs-text-muted);
}

.detail {
  font-size: 12px;
  word-break: break-word;
}

@media (max-width: 1080px) {
  .env-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
