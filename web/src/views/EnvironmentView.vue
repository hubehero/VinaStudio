<script setup lang="ts">
import { CircleCheckFilled, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import StatusPill from '@/components/StatusPill.vue'
import { probeStandaloneRenderer, rendererInfo } from '@/composables/use3Dmol'
import { useSystemStore } from '@/stores/system'
import type { PackageCheck } from '@/types/api'

const system = useSystemStore()
const { t } = useI18n()

onMounted(() => {
  // The renderer row is the one field a "the 3D view is slow" report needs, and
  // this page can be reached before any viewer exists, so probe here rather than
  // waiting for a viewport to do it.
  probeStandaloneRenderer()
  if (!system.info) {
    void system.refresh()
  }
})

/**
 * Which backend docking will use, in the form the user can act on: the door, and
 * the reason it was chosen (`reasonCode` is translated; the server's English
 * `reason` stays in the API for logs).
 */
function dockingBackendText(): string {
  const docking = system.info?.docking
  if (!docking?.backend) {
    return t('environment.dockingNone')
  }
  const door =
    docking.backend === 'vina-cli'
      ? t('environment.dockingCli')
      : t('environment.dockingApi')
  return `${door} · ${t(`environment.dockingReason.${docking.reasonCode}`)}`
}

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
    {
      label: t('environment.renderMode'),
      value: system.info?.rendering?.softwareRenderRequested
        ? t('environment.softwareRenderOn')
        : t('environment.softwareRenderOff'),
    },
    {
      label: t('environment.renderer'),
      value: rendererInfo.value?.renderer ?? t('environment.rendererUnknown'),
    },
    {
      label: t('environment.buffer'),
      value: bufferSizeText(),
    },
    {
      label: t('environment.devicePixelRatio'),
      value: rendererInfo.value?.devicePixelRatio?.toString() ?? t('environment.rendererUnknown'),
    },
    {
      label: t('environment.msaa'),
      value:
        rendererInfo.value?.samples === undefined
          ? t('environment.rendererUnknown')
          : rendererInfo.value.samples > 0
            ? `${rendererInfo.value.samples}×`
            : t('environment.msaaOff'),
    },
    { label: t('environment.dockingBackend'), value: dockingBackendText() },
  ]
})

/**
 * The viewport's drawing buffer in device pixels.
 *
 * Render cost tracks this number: ambient occlusion is a fixed 64 taps per
 * pixel, so doubling the display scale quadruples it. "How big is the buffer"
 * is therefore the first question a "the 3D view stutters" report raises, and
 * it cannot be answered from the renderer string alone.
 */
function bufferSizeText(): string {
  const info = rendererInfo.value
  if (!info?.bufferWidth || !info?.bufferHeight) return t('environment.rendererUnknown')
  return `${info.bufferWidth} × ${info.bufferHeight} px`
}

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
  const check = system.selfCheck
  if (!check) return t('environment.selfCheckIdle')
  if (check.dockingAvailable) return t('environment.dockingReady')
  // No library is to blame: nothing provides the engine at all (no importable
  // `vina` module and no `vina` binary). Saying "missing dependencies: " with
  // an empty list would read as a bug of its own.
  if (check.dockingMissing.length === 0) return t('environment.dockingNoEngine')
  return t('environment.dockingMissing', { packages: check.dockingMissing.join(', ') })
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
