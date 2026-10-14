<script setup lang="ts">
import { ElTooltip } from 'element-plus'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { LigandProperties } from '@/types/api'

const props = defineProps<{
  properties: LigandProperties | null
  propertiesError?: string | undefined
}>()

const { t } = useI18n()

type Verdict = 'pass' | 'fail' | 'dash' | 'empty'

interface MetricRow {
  label: string
  value: string
  limit: string
  verdict: Verdict
  /** Rule-source tooltip; absent = no tooltip (reference rows, QED). */
  tip?: string
}

const rows = computed<MetricRow[]>(() => {
  const p = props.properties
  if (!p) return []
  const lipinski = t('molecules.druglikeness.tip.lipinski')
  const veber = t('molecules.druglikeness.tip.veber')
  return [
    {
      label: t('molecules.druglikeness.metric.molWt'),
      value: p.molWt.toFixed(2),
      limit: '≤ 500',
      verdict: p.molWt <= 500 ? 'pass' : 'fail',
      tip: lipinski,
    },
    {
      label: t('molecules.druglikeness.metric.molLogP'),
      value: p.molLogP.toFixed(2),
      limit: '≤ 5',
      verdict: p.molLogP <= 5 ? 'pass' : 'fail',
      tip: lipinski,
    },
    {
      label: t('molecules.druglikeness.metric.tpsa'),
      value: p.tpsa.toFixed(1),
      limit: '≤ 140',
      verdict: p.tpsa <= 140 ? 'pass' : 'fail',
      tip: veber,
    },
    {
      label: t('molecules.druglikeness.metric.hbd'),
      value: String(p.numHDonors),
      limit: '≤ 5',
      verdict: p.numHDonors <= 5 ? 'pass' : 'fail',
      tip: lipinski,
    },
    {
      label: t('molecules.druglikeness.metric.hba'),
      value: String(p.numHAcceptors),
      limit: '≤ 10',
      verdict: p.numHAcceptors <= 10 ? 'pass' : 'fail',
      tip: lipinski,
    },
    {
      label: t('molecules.druglikeness.metric.rotB'),
      value: String(p.numRotatableBonds),
      limit: '≤ 10',
      verdict: p.numRotatableBonds <= 10 ? 'pass' : 'fail',
      tip: veber,
    },
    {
      label: t('molecules.druglikeness.metric.rings'),
      value: String(p.ringCount),
      limit: t('molecules.druglikeness.refValue'),
      verdict: 'dash',
    },
    {
      label: t('molecules.druglikeness.qed'),
      value: p.qed.toFixed(3),
      limit: '—',
      verdict: 'empty',
    },
  ]
})

const violations = computed(() => props.properties?.lipinskiViolations ?? 0)

const badgeClass = computed(() => {
  const n = violations.value
  if (n === 0) return 'druglikeness__badge--success'
  if (n === 1) return 'druglikeness__badge--warning'
  return 'druglikeness__badge--danger'
})

const violationsText = computed(() =>
  t('molecules.druglikeness.violations', { n: violations.value }),
)

const qedText = computed(() => (props.properties ? props.properties.qed.toFixed(3) : ''))
</script>

<template>
  <section class="detail__section">
    <h3 class="detail__section-title">{{ t('molecules.druglikeness.title') }}</h3>
    <template v-if="properties">
      <div class="druglikeness__summary">
        <span class="druglikeness__badge" :class="badgeClass">{{ violationsText }}</span>
        <span class="druglikeness__qed">{{ t('molecules.druglikeness.qed') }} {{ qedText }}</span>
      </div>
      <table class="druglikeness__table">
        <colgroup>
          <col />
          <col style="width: 72px" />
          <col style="width: 88px" />
          <col style="width: 64px" />
        </colgroup>
        <thead>
          <tr>
            <th>{{ t('molecules.druglikeness.col.metric') }}</th>
            <th class="druglikeness__num">{{ t('molecules.druglikeness.col.value') }}</th>
            <th>{{ t('molecules.druglikeness.col.limit') }}</th>
            <th>{{ t('molecules.druglikeness.col.verdict') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.label">
            <td class="druglikeness__metric">{{ row.label }}</td>
            <td class="druglikeness__num">{{ row.value }}</td>
            <td>
              <el-tooltip v-if="row.tip" :content="row.tip" placement="top">
                <span>{{ row.limit }}</span>
              </el-tooltip>
              <template v-else>{{ row.limit }}</template>
            </td>
            <td>
              <span v-if="row.verdict === 'pass'" class="druglikeness__verdict--pass">
                {{ t('molecules.druglikeness.pass') }}
              </span>
              <span v-else-if="row.verdict === 'fail'" class="druglikeness__verdict--fail">
                {{ t('molecules.druglikeness.fail') }}
              </span>
              <span v-else-if="row.verdict === 'dash'" class="druglikeness__dash">—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="druglikeness__footnote">{{ t('molecules.druglikeness.disclaimer') }}</p>
    </template>
    <p v-else class="druglikeness__failed">
      {{ t('molecules.druglikeness.computeFailed', { reason: propertiesError }) }}
    </p>
  </section>
</template>

<style scoped>
/* Section chrome mirrors MoleculeDetail's detail__section: scoped styles
   keep the panels independent, per the design spec's "copy the styles". */
.detail__section {
  flex: none;
}

.detail__section-title {
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--vs-text-faint);
}

.druglikeness__summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.druglikeness__badge {
  padding: 2px 8px;
  border-radius: var(--vs-radius-sm);
  font-size: 12px;
  font-weight: 600;
}

.druglikeness__badge--success {
  color: var(--vs-success);
  background: color-mix(in srgb, var(--vs-success) 12%, transparent);
}

.druglikeness__badge--warning {
  color: var(--vs-warning);
  background: color-mix(in srgb, var(--vs-warning) 14%, transparent);
}

.druglikeness__badge--danger {
  color: var(--vs-danger);
  background: color-mix(in srgb, var(--vs-danger) 12%, transparent);
}

.druglikeness__qed {
  font-family: var(--vs-font-mono);
  font-size: 12.5px;
  color: var(--vs-text);
}

.druglikeness__table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 12px;
}

.druglikeness__table th {
  padding: 2px 8px 4px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--vs-border) 50%, transparent);
  color: var(--vs-text-muted);
  font-size: 11.5px;
  font-weight: 600;
  text-align: left;
}

.druglikeness__table td {
  padding: 3px 8px 3px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--vs-border) 50%, transparent);
  color: var(--vs-text);
}

.druglikeness__table th:last-child,
.druglikeness__table td:last-child {
  padding-right: 0;
}

.druglikeness__num {
  text-align: right;
  font-family: var(--vs-font-mono);
  font-size: 12.5px;
}

.druglikeness__metric {
  color: var(--vs-text-muted);
}

.druglikeness__verdict--pass {
  color: var(--vs-success);
}

.druglikeness__verdict--fail {
  color: var(--vs-warning);
}

.druglikeness__dash {
  color: var(--vs-text-muted);
}

.druglikeness__footnote {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--vs-text-faint);
}

.druglikeness__failed {
  margin: 0;
  font-size: 12px;
  color: var(--vs-text-faint);
}
</style>
