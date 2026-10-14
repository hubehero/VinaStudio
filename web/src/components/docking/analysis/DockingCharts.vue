<script setup lang="ts">
/**
 * Result-analysis figures for the report page.
 *
 * Every series is derived from the docking store, so the figures never fetch
 * and never disagree with the pose table. Conventions are stated in the
 * captions on purpose (units, "more negative = stronger", and that Vina's
 * rmsd l.b./u.b. is relative to the top pose rather than to a crystal
 * structure) — the charts are read as evidence, so a silent convention would
 * be a scientific error waiting to happen.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useDockingStore } from '@/stores/docking'

import {
  formatValue,
  histogram,
  linearScale,
  meanSd,
  niceTicks,
  sturgesBinCount,
} from './chart-utils'

const { t } = useI18n()
const docking = useDockingStore()

// -- geometry (one viewBox for every figure keeps the axes comparable) --------
const W = 340
const H = 210
const M = { top: 16, right: 14, bottom: 40, left: 50 }
const PLOT_W = W - M.left - M.right
const PLOT_H = H - M.top - M.bottom
const PLOT_RIGHT = W - M.right
const PLOT_BOTTOM = H - M.bottom

const TICK_LABEL_Y = PLOT_BOTTOM + 14

const poses = computed(() => docking.poses)
const affinities = computed(() => poses.value.map((pose) => pose.affinity))
const currentIndex = computed(() => docking.currentPoseIndex)
const bestAffinity = computed(() => docking.bestAffinity)

function isBest(affinity: number): boolean {
  return bestAffinity.value !== null && affinity === bestAffinity.value
}

// -- shared affinity axis (profile + funnel) ---------------------------------
const affinityDomain = computed<[number, number]>(() => {
  const values = affinities.value
  if (values.length === 0) return [-1, 0]
  return [Math.min(0, ...values), Math.max(0, ...values)]
})
const affinityScale = computed(() => linearScale(affinityDomain.value, [PLOT_BOTTOM, M.top]))
const affinityTicks = computed(() =>
  niceTicks(affinityDomain.value[0], affinityDomain.value[1], 4),
)

// -- ① affinity profile (bar per pose, Vina order) ---------------------------
const profileBars = computed(() => {
  const rows = poses.value
  if (rows.length === 0) return []
  const band = PLOT_W / rows.length
  const barWidth = Math.max(1.5, band * 0.72)
  const baseline = affinityScale.value.map(0)
  return rows.map((pose, index) => {
    const top = affinityScale.value.map(pose.affinity)
    return {
      index: pose.index,
      affinity: pose.affinity,
      x: M.left + band * index + (band - barWidth) / 2,
      width: barWidth,
      y: Math.min(top, baseline),
      height: Math.max(1, Math.abs(baseline - top)),
      best: isBest(pose.affinity),
      current: index === currentIndex.value,
    }
  })
})

const profileXTicks = computed(() => {
  const rows = poses.value
  if (rows.length === 0) return []
  const band = PLOT_W / rows.length
  const step = Math.max(1, Math.ceil(rows.length / 6))
  const ticks: { x: number; label: string }[] = []
  for (let i = 0; i < rows.length; i += step) {
    const row = rows[i]
    if (row) ticks.push({ x: M.left + band * i + band / 2, label: String(row.index) })
  }
  return ticks
})

// -- ② affinity distribution (Sturges bins) ----------------------------------
const affinityBins = computed(() => histogram(affinities.value, sturgesBinCount(affinities.value.length)))
const affinityRange = computed<[number, number]>(() => {
  const bins = affinityBins.value
  const first = bins[0]
  const last = bins[bins.length - 1]
  if (!first || !last) return [-1, 0]
  return [first.x0, last.x1]
})
const histXScale = computed(() => linearScale(affinityRange.value, [M.left, PLOT_RIGHT]))
const histMaxCount = computed(() => Math.max(1, ...affinityBins.value.map((bin) => bin.count)))
const histYScale = computed(() => linearScale([0, histMaxCount.value], [PLOT_BOTTOM, M.top]))
const histTicks = computed(() => niceTicks(affinityRange.value[0], affinityRange.value[1], 4))
const histCountTicks = computed(() => niceTicks(0, histMaxCount.value, 3))
const affinityMean = computed(() => meanSd(affinities.value).mean)
const histBars = computed(() =>
  affinityBins.value.map((bin) => {
    const x = histXScale.value.map(bin.x0)
    const x1 = histXScale.value.map(bin.x1)
    const y = histYScale.value.map(bin.count)
    return {
      key: bin.x0,
      x,
      width: Math.max(1, x1 - x - 1),
      y,
      height: Math.max(0, PLOT_BOTTOM - y),
      count: bin.count,
      label: formatValue((bin.x0 + bin.x1) / 2),
    }
  }),
)

// -- ③ energy funnel (affinity vs RMSD to the top pose) ----------------------
const funnelMaxRmsd = computed(() => Math.max(0.1, ...poses.value.map((pose) => pose.rmsdLower)))
const funnelXScale = computed(() => linearScale([0, funnelMaxRmsd.value * 1.05], [M.left, PLOT_RIGHT]))
const funnelRmsdTicks = computed(() => niceTicks(0, funnelMaxRmsd.value * 1.05, 4))
const funnelPoints = computed(() =>
  poses.value.map((pose, index) => ({
    key: pose.index,
    index: pose.index,
    affinity: pose.affinity,
    rmsd: pose.rmsdLower,
    x: funnelXScale.value.map(pose.rmsdLower),
    y: affinityScale.value.map(pose.affinity),
    best: isBest(pose.affinity),
    current: index === currentIndex.value,
  })),
)

// -- ④ redocking RMSD distribution (vs reference, with the 2 Å convention) ---
const rmsdValues = computed(() => docking.rmsd?.values ?? [])
const rmsdThreshold = computed(() => docking.rmsd?.threshold ?? 2)
const rmsdBins = computed(() => histogram(rmsdValues.value, sturgesBinCount(rmsdValues.value.length)))
const rmsdDomain = computed<[number, number]>(() => {
  const values = rmsdValues.value
  const observed = values.length > 0 ? Math.max(...values) : 1
  return [0, Math.max(observed, rmsdThreshold.value) * 1.1]
})
const rmsdXScale = computed(() => linearScale(rmsdDomain.value, [M.left, PLOT_RIGHT]))
const rmsdMaxCount = computed(() => Math.max(1, ...rmsdBins.value.map((bin) => bin.count)))
const rmsdYScale = computed(() => linearScale([0, rmsdMaxCount.value], [PLOT_BOTTOM, M.top]))
const rmsdTicks = computed(() => niceTicks(0, rmsdDomain.value[1], 4))
const rmsdCountTicks = computed(() => niceTicks(0, rmsdMaxCount.value, 3))
const rmsdBars = computed(() =>
  rmsdBins.value.map((bin) => {
    const x = rmsdXScale.value.map(bin.x0)
    const x1 = rmsdXScale.value.map(bin.x1)
    const y = rmsdYScale.value.map(bin.count)
    return {
      key: bin.x0,
      x,
      width: Math.max(1, x1 - x - 1),
      y,
      height: Math.max(0, PLOT_BOTTOM - y),
      count: bin.count,
    }
  }),
)

// -- summary statistics ------------------------------------------------------
const stats = computed(() => {
  const values = affinities.value
  if (values.length === 0) return null
  const { mean, sd } = meanSd(values)
  return {
    n: values.length,
    best: Math.min(...values),
    mean,
    sd,
    lo: Math.min(...values),
    hi: Math.max(...values),
  }
})

// -- visibility --------------------------------------------------------------
const showProfile = computed(() => poses.value.length >= 1)
const showHistogram = computed(() => poses.value.length >= 3)
const showFunnel = computed(() => poses.value.length >= 3)
const showRmsd = computed(() => rmsdValues.value.length >= 1)
const hasAny = computed(
  () => showProfile.value || showHistogram.value || showFunnel.value || showRmsd.value,
)

function selectPose(index: number): void {
  docking.selectPose(index - 1)
}
</script>

<template>
  <section v-if="hasAny" class="analysis">
    <h4 class="analysis__title">{{ t('docking.analysis.title') }}</h4>

    <p v-if="stats" class="analysis__stats">
      <span>{{ t('docking.analysis.statsN') }} <b>{{ stats.n }}</b></span>
      <span>{{ t('docking.resultsReport.metricBest') }} <b>{{ formatValue(stats.best) }}</b> kcal/mol</span>
      <span>{{ t('docking.analysis.statsMean') }} <b>{{ formatValue(stats.mean) }} ± {{ formatValue(stats.sd) }}</b></span>
      <span>{{ t('docking.analysis.statsRange') }} <b>{{ formatValue(stats.lo) }} … {{ formatValue(stats.hi) }}</b></span>
    </p>

    <div class="analysis__grid">
      <!-- ① affinity profile -->
      <figure v-if="showProfile" class="figure">
        <figcaption class="figure__title">{{ t('docking.analysis.profileTitle') }}</figcaption>
        <svg class="figure__svg" :viewBox="`0 0 ${W} ${H}`" role="img"
             :aria-label="t('docking.analysis.profileTitle')">
          <line :x1="M.left" :x2="PLOT_RIGHT" :y1="PLOT_BOTTOM" :y2="PLOT_BOTTOM" class="axis" />
          <line :x1="M.left" :x2="M.left" :y1="M.top" :y2="PLOT_BOTTOM" class="axis" />
          <g v-for="tick in affinityTicks" :key="`apy-${tick}`">
            <line :x1="M.left" :x2="PLOT_RIGHT" :y1="affinityScale.map(tick)" :y2="affinityScale.map(tick)" class="grid" />
            <text :x="M.left - 6" :y="affinityScale.map(tick) + 3" class="tick" text-anchor="end">{{ formatValue(tick, 0) }}</text>
          </g>
          <rect
            v-for="bar in profileBars"
            :key="`ap-${bar.index}`"
            :x="bar.x" :y="bar.y" :width="bar.width" :height="bar.height"
            class="bar bar--muted" :class="{ 'bar--best': bar.best, 'bar--current': bar.current }"
            role="button" tabindex="0"
            @click="selectPose(bar.index)"
            @keydown.enter="selectPose(bar.index)"
          >
            <title>#{{ bar.index }} · {{ formatValue(bar.affinity) }} kcal/mol</title>
          </rect>
          <text v-for="tick in profileXTicks" :key="`apx-${tick.label}`" :x="tick.x" :y="TICK_LABEL_Y" class="tick" text-anchor="middle">{{ tick.label }}</text>
          <text :x="M.left + PLOT_W / 2" :y="H - 6" class="axis-label" text-anchor="middle">{{ t('docking.analysis.axisPose') }}</text>
          <text :x="14" :y="M.top + PLOT_H / 2" class="axis-label" text-anchor="middle"
                :transform="`rotate(-90 14 ${M.top + PLOT_H / 2})`">{{ t('docking.analysis.axisAffinity') }}</text>
        </svg>
        <p class="figure__caption">{{ t('docking.analysis.profileCaption') }}</p>
      </figure>

      <!-- ② affinity distribution -->
      <figure v-if="showHistogram" class="figure">
        <figcaption class="figure__title">{{ t('docking.analysis.histTitle') }}</figcaption>
        <svg class="figure__svg" :viewBox="`0 0 ${W} ${H}`" role="img"
             :aria-label="t('docking.analysis.histTitle')">
          <line :x1="M.left" :x2="PLOT_RIGHT" :y1="PLOT_BOTTOM" :y2="PLOT_BOTTOM" class="axis" />
          <line :x1="M.left" :x2="M.left" :y1="M.top" :y2="PLOT_BOTTOM" class="axis" />
          <g v-for="tick in histCountTicks" :key="`ahy-${tick}`">
            <line :x1="M.left" :x2="PLOT_RIGHT" :y1="histYScale.map(tick)" :y2="histYScale.map(tick)" class="grid" />
            <text :x="M.left - 6" :y="histYScale.map(tick) + 3" class="tick" text-anchor="end">{{ Math.round(tick) }}</text>
          </g>
          <rect v-for="bar in histBars" :key="`ah-${bar.key}`" :x="bar.x" :y="bar.y" :width="bar.width" :height="bar.height" class="bar bar--muted">
            <title>{{ bar.label }} kcal/mol · {{ bar.count }}</title>
          </rect>
          <line :x1="histXScale.map(affinityMean)" :x2="histXScale.map(affinityMean)" :y1="M.top" :y2="PLOT_BOTTOM" class="marker marker--mean" />
          <text v-for="tick in histTicks" :key="`ahx-${tick}`" :x="histXScale.map(tick)" :y="TICK_LABEL_Y" class="tick" text-anchor="middle">{{ formatValue(tick, 0) }}</text>
          <text :x="M.left + PLOT_W / 2" :y="H - 6" class="axis-label" text-anchor="middle">{{ t('docking.analysis.axisAffinity') }}</text>
          <text :x="14" :y="M.top + PLOT_H / 2" class="axis-label" text-anchor="middle"
                :transform="`rotate(-90 14 ${M.top + PLOT_H / 2})`">{{ t('docking.analysis.axisCount') }}</text>
        </svg>
        <p class="figure__caption">{{ t('docking.analysis.histCaption', { mean: formatValue(affinityMean) }) }}</p>
      </figure>

      <!-- ③ energy funnel -->
      <figure v-if="showFunnel" class="figure">
        <figcaption class="figure__title">{{ t('docking.analysis.funnelTitle') }}</figcaption>
        <svg class="figure__svg" :viewBox="`0 0 ${W} ${H}`" role="img"
             :aria-label="t('docking.analysis.funnelTitle')">
          <line :x1="M.left" :x2="PLOT_RIGHT" :y1="PLOT_BOTTOM" :y2="PLOT_BOTTOM" class="axis" />
          <line :x1="M.left" :x2="M.left" :y1="M.top" :y2="PLOT_BOTTOM" class="axis" />
          <g v-for="tick in affinityTicks" :key="`efy-${tick}`">
            <line :x1="M.left" :x2="PLOT_RIGHT" :y1="affinityScale.map(tick)" :y2="affinityScale.map(tick)" class="grid" />
            <text :x="M.left - 6" :y="affinityScale.map(tick) + 3" class="tick" text-anchor="end">{{ formatValue(tick, 0) }}</text>
          </g>
          <circle
            v-for="point in funnelPoints"
            :key="`ef-${point.index}`"
            :cx="point.x" :cy="point.y" :r="point.best ? 4 : 3"
            class="dot" :class="{ 'dot--best': point.best, 'dot--current': point.current }"
            role="button" tabindex="0"
            @click="selectPose(point.index)"
            @keydown.enter="selectPose(point.index)"
          >
            <title>#{{ point.index }} · {{ formatValue(point.affinity) }} kcal/mol · RMSD {{ formatValue(point.rmsd, 1) }} Å</title>
          </circle>
          <text v-for="tick in funnelRmsdTicks" :key="`efx-${tick}`" :x="funnelXScale.map(tick)" :y="TICK_LABEL_Y" class="tick" text-anchor="middle">{{ formatValue(tick, 1) }}</text>
          <text :x="M.left + PLOT_W / 2" :y="H - 6" class="axis-label" text-anchor="middle">{{ t('docking.analysis.axisRmsd') }}</text>
          <text :x="14" :y="M.top + PLOT_H / 2" class="axis-label" text-anchor="middle"
                :transform="`rotate(-90 14 ${M.top + PLOT_H / 2})`">{{ t('docking.analysis.axisAffinity') }}</text>
        </svg>
        <p class="figure__caption">{{ t('docking.analysis.funnelCaption') }}</p>
      </figure>

      <!-- ④ redocking RMSD distribution -->
      <figure v-if="showRmsd" class="figure">
        <figcaption class="figure__title">{{ t('docking.analysis.rmsdTitle') }}</figcaption>
        <svg class="figure__svg" :viewBox="`0 0 ${W} ${H}`" role="img"
             :aria-label="t('docking.analysis.rmsdTitle')">
          <line :x1="M.left" :x2="PLOT_RIGHT" :y1="PLOT_BOTTOM" :y2="PLOT_BOTTOM" class="axis" />
          <line :x1="M.left" :x2="M.left" :y1="M.top" :y2="PLOT_BOTTOM" class="axis" />
          <g v-for="tick in rmsdCountTicks" :key="`rhy-${tick}`">
            <line :x1="M.left" :x2="PLOT_RIGHT" :y1="rmsdYScale.map(tick)" :y2="rmsdYScale.map(tick)" class="grid" />
            <text :x="M.left - 6" :y="rmsdYScale.map(tick) + 3" class="tick" text-anchor="end">{{ Math.round(tick) }}</text>
          </g>
          <rect v-for="bar in rmsdBars" :key="`rh-${bar.key}`" :x="bar.x" :y="bar.y" :width="bar.width" :height="bar.height" class="bar bar--muted">
            <title>{{ bar.count }}</title>
          </rect>
          <line :x1="rmsdXScale.map(rmsdThreshold)" :x2="rmsdXScale.map(rmsdThreshold)" :y1="M.top" :y2="PLOT_BOTTOM" class="marker marker--threshold" />
          <text :x="rmsdXScale.map(rmsdThreshold)" :y="M.top - 4" class="tick tick--warn" text-anchor="middle">{{ formatValue(rmsdThreshold, 1) }} Å</text>
          <text v-for="tick in rmsdTicks" :key="`rhx-${tick}`" :x="rmsdXScale.map(tick)" :y="TICK_LABEL_Y" class="tick" text-anchor="middle">{{ formatValue(tick, 1) }}</text>
          <text :x="M.left + PLOT_W / 2" :y="H - 6" class="axis-label" text-anchor="middle">{{ t('docking.analysis.axisRmsdRef') }}</text>
          <text :x="14" :y="M.top + PLOT_H / 2" class="axis-label" text-anchor="middle"
                :transform="`rotate(-90 14 ${M.top + PLOT_H / 2})`">{{ t('docking.analysis.axisCount') }}</text>
        </svg>
        <p class="figure__caption">{{ t('docking.analysis.rmsdCaption', { threshold: formatValue(rmsdThreshold, 1) }) }}</p>
      </figure>
    </div>

    <p v-if="showProfile" class="analysis__legend">
      <span class="legend-item"><i class="swatch swatch--best"></i>{{ t('docking.analysis.legendBest') }}</span>
      <span class="legend-item"><i class="swatch swatch--current"></i>{{ t('docking.analysis.legendCurrent') }}</span>
      <span v-if="showHistogram" class="legend-item"><i class="swatch swatch--mean"></i>{{ t('docking.analysis.legendMean') }}</span>
    </p>
  </section>
</template>

<style scoped>
.analysis {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.analysis__title {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--vs-text-faint);
}

.analysis__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  margin: 0;
  font-size: 12px;
  color: var(--vs-text-muted);
  font-variant-numeric: tabular-nums;
}

.analysis__stats b {
  font-weight: 600;
  color: var(--vs-text);
}

.analysis__grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
}

.figure {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  background: var(--vs-bg-surface);
}

.figure__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--vs-text);
}

.figure__svg {
  display: block;
  width: 100%;
  height: auto;
}

.figure__caption {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--vs-text-faint);
}

.axis {
  stroke: var(--vs-border-strong);
  stroke-width: 1;
}

.grid {
  stroke: var(--vs-border);
  stroke-width: 1;
  opacity: 0.55;
}

.tick {
  font-size: 10px;
  fill: var(--vs-text-faint);
  font-variant-numeric: tabular-nums;
}

.tick--warn {
  fill: var(--vs-warning);
}

.axis-label {
  font-size: 10px;
  fill: var(--vs-text-muted);
}

.bar {
  fill: var(--vs-accent);
}

.bar--muted {
  fill: var(--vs-text-muted);
}

.bar--best {
  fill: var(--vs-accent);
}

.bar--current {
  stroke: var(--vs-text);
  stroke-width: 1.2;
}

.bar {
  cursor: pointer;
}

.dot {
  fill: var(--vs-text-muted);
  opacity: 0.75;
}

.dot--best {
  fill: var(--vs-accent);
  opacity: 1;
}

.dot--current {
  stroke: var(--vs-text);
  stroke-width: 1.4;
}

.dot {
  cursor: pointer;
}

.marker {
  stroke-width: 1.4;
  stroke-dasharray: 5 4;
}

.marker--mean {
  stroke: var(--vs-warning);
}

.marker--threshold {
  stroke: var(--vs-warning);
  stroke-dasharray: 4 3;
}

.analysis__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin: 0;
  font-size: 11px;
  color: var(--vs-text-muted);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.swatch--best {
  background: var(--vs-accent);
}

.swatch--current {
  background: var(--vs-text-muted);
  outline: 1.2px solid var(--vs-text);
  outline-offset: -1px;
}

.swatch--mean {
  background: var(--vs-warning);
}
</style>
