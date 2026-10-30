<script setup lang="ts">
import { CircleCheckFilled, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import StatusPill from '@/components/StatusPill.vue'
import { probeStandaloneRenderer, rendererInfo } from '@/composables/use3Dmol'
import { useSystemStore } from '@/stores/system'
import type { DiagnosticCheck, PackageCheck } from '@/types/api'

const system = useSystemStore()
const { t, te } = useI18n()

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

/**
 * A renderer check belongs to the page that can observe WebGL. The server
 * cannot see the browser, so it is appended only when a diagnostic report is
 * present; it is never auto-repaired because a driver change is a user action.
 */
const rendererCheck = computed<DiagnosticCheck | null>(() => {
  if (!system.diagnostics) return null
  const info = rendererInfo.value
  if (!info) {
    return {
      id: 'renderer',
      severity: 'error',
      fixable: false,
      detail: 'WebGL renderer was not detected',
      params: {},
      suggestions: ['checkWebGL'],
    }
  }
  if (info.software) {
    return {
      id: 'renderer',
      severity: 'warning',
      fixable: false,
      detail: info.renderer,
      params: {},
      suggestions: ['updateGraphicsDriver', 'softwareRenderHint'],
    }
  }
  return {
    id: 'renderer',
    severity: 'ok',
    fixable: false,
    detail: info.renderer,
    params: {},
    suggestions: [],
  }
})

const diagnosticRows = computed<DiagnosticCheck[]>(() => {
  if (!system.diagnostics) return []
  const rows = [...system.diagnostics.checks]
  if (rendererCheck.value) rows.push(rendererCheck.value)
  return rows
})

function diagnosticTitle(check: DiagnosticCheck): string {
  const key = `environment.diagnostics.checks.${check.id}.title`
  return te(key) ? t(key, check.params) : check.id
}

function diagnosticDetail(check: DiagnosticCheck): string {
  if (check.detail) return check.detail
  const key = `environment.diagnostics.checks.${check.id}.detail`
  return te(key) ? t(key, check.params) : t('environment.diagnostics.noDetail')
}

function suggestionText(code: string): string {
  const key = `environment.diagnostics.suggestions.${code}`
  return te(key) ? t(key) : code
}

function diagnosticState(check: DiagnosticCheck): 'ok' | 'warn' | 'error' {
  if (check.severity === 'error') return 'error'
  if (check.severity === 'warning') return 'warn'
  return 'ok'
}

function diagnosticStateLabel(check: DiagnosticCheck): string {
  return t(`environment.diagnostics.severity.${check.severity}`)
}

const diagnosticSummary = computed(() => {
  const report = system.diagnostics
  if (!report) return t('environment.diagnostics.idle')
  return t(`environment.diagnostics.summary.${report.severity}`, {
    checks: diagnosticRows.value.length,
  })
})

async function diagnoseAndRepair(): Promise<void> {
  await system.runDiagnostics()
  if (system.diagnosticError) {
    ElMessage.error(system.diagnosticError)
    return
  }
  if (!system.diagnostics?.repairAvailable) return
  const count = await system.repairDiagnostics()
  if (system.diagnosticError) {
    ElMessage.error(system.diagnosticError)
  } else if (count > 0) {
    ElMessage.success(t('environment.diagnostics.repaired', { n: count }))
  }
}

async function repairSafeItems(): Promise<void> {
  const count = await system.repairDiagnostics()
  if (system.diagnosticError) {
    ElMessage.error(system.diagnosticError)
    return
  }
  if (count === 0) {
    ElMessage.info(t('environment.diagnostics.nothingToRepair'))
  } else {
    ElMessage.success(t('environment.diagnostics.repaired', { n: count }))
  }
}

async function copyDiagnosticReport(): Promise<void> {
  if (!system.diagnostics) return
  const report = {
    ...system.diagnostics,
    renderer: rendererCheck.value,
  }
  try {
    await navigator.clipboard.writeText(JSON.stringify(report, null, 2))
    ElMessage.success(t('environment.diagnostics.copied'))
  } catch {
    ElMessage.error(t('environment.diagnostics.copyFailed'))
  }
}
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

    <div class="vs-card diagnostics-card">
      <div class="vs-card__header">
        <div>
          <div class="vs-card__title">{{ t('environment.diagnostics.title') }}</div>
          <div class="vs-card__subtitle">{{ t('environment.diagnostics.subtitle') }}</div>
        </div>
        <div class="diagnostics__actions">
          <el-button
            type="primary"
            size="small"
            :loading="system.diagnosing || system.repairing"
            :icon="Refresh"
            @click="diagnoseAndRepair"
          >
            {{ system.diagnosing ? t('environment.diagnostics.running') : t('environment.diagnostics.diagnoseRepair') }}
          </el-button>
          <el-button
            size="small"
            :loading="system.diagnosing"
            @click="system.runDiagnostics()"
          >
            {{ t('environment.diagnostics.runOnly') }}
          </el-button>
          <el-button
            size="small"
            :loading="system.repairing"
            :disabled="!system.diagnostics?.repairAvailable"
            @click="repairSafeItems"
          >
            {{ system.repairing ? t('environment.diagnostics.repairing') : t('environment.diagnostics.repair') }}
          </el-button>
          <el-button v-if="system.diagnostics" text size="small" @click="copyDiagnosticReport">
            {{ t('environment.diagnostics.copy') }}
          </el-button>
        </div>
      </div>
      <div class="vs-card__body">
        <el-alert
          v-if="system.diagnosticError"
          type="error"
          :closable="false"
          show-icon
          :title="system.diagnosticError"
        />
        <p class="diagnostics__hint">{{ t('environment.diagnostics.repairHint') }}</p>

        <div v-if="!system.diagnostics" class="diagnostics__idle">
          {{ t('environment.diagnostics.idle') }}
        </div>
        <template v-else>
          <div class="diagnostics__summary">
            <StatusPill
              :state="diagnosticState({ severity: system.diagnostics.severity } as DiagnosticCheck)"
              :label="diagnosticSummary"
            />
            <span class="vs-faint">{{ t('environment.diagnostics.generatedAt', { time: system.diagnostics.generatedAt }) }}</span>
          </div>
          <div class="diagnostics__list">
            <article
              v-for="check in diagnosticRows"
              :key="check.id"
              class="diagnostic-row"
              :class="`is-${check.severity}`"
            >
              <StatusPill :state="diagnosticState(check)" :label="diagnosticStateLabel(check)" />
              <div class="diagnostic-row__body">
                <div class="diagnostic-row__title">{{ diagnosticTitle(check) }}</div>
                <div v-if="diagnosticDetail(check)" class="diagnostic-row__detail vs-mono">
                  {{ diagnosticDetail(check) }}
                </div>
                <ul v-if="check.suggestions.length" class="diagnostic-row__suggestions">
                  <li v-for="suggestion in check.suggestions" :key="suggestion">
                    {{ suggestionText(suggestion) }}
                  </li>
                </ul>
              </div>
            </article>
          </div>
        </template>
      </div>
    </div>

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

.diagnostics-card { margin-bottom: 16px; }
.diagnostics__actions { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; justify-content: flex-end; }
.diagnostics__hint { margin: 0 0 10px; color: var(--vs-text-muted); font-size: 12px; line-height: 1.5; }
.diagnostics__idle { padding: 12px 0; color: var(--vs-text-muted); font-size: 12.5px; }
.diagnostics__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 11.5px;
}
.diagnostics__list { display: flex; flex-direction: column; gap: 2px; }
.diagnostic-row {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 9px 0;
  border-top: 1px solid var(--vs-border);
}
.diagnostic-row__body { min-width: 0; }
.diagnostic-row__title { color: var(--vs-text); font-size: 12.5px; font-weight: 600; }
.diagnostic-row__detail { margin-top: 3px; color: var(--vs-text-faint); font-size: 11px; overflow-wrap: anywhere; white-space: pre-wrap; }
.diagnostic-row__suggestions { margin: 5px 0 0; padding-left: 16px; color: var(--vs-text-muted); font-size: 11.5px; line-height: 1.5; }
.diagnostic-row.is-error .diagnostic-row__title { color: var(--vs-danger); }
.diagnostic-row.is-warning .diagnostic-row__title { color: var(--vs-warning); }

@media (max-width: 1080px) {
  .env-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
