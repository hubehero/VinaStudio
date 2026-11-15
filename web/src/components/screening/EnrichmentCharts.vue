<script setup lang="ts">
import { computed } from 'vue'

import { linearScale, niceTicks } from '@/components/docking/analysis/chart-utils'
import type { EnrichmentPoint } from '@/types/api'

const props = defineProps<{
  roc: EnrichmentPoint[]
  enrichment: EnrichmentPoint[]
}>()

const WIDTH = 300
const HEIGHT = 170
const PAD = 30

const rocX = linearScale([0, 1], [PAD, WIDTH - 8])
const rocY = linearScale([0, 1], [HEIGHT - PAD, 8])

const efMax = computed(() => {
  const max = Math.max(1.5, ...props.enrichment.map((point) => point.y))
  return max * 1.08
})
const efX = linearScale([0, 1], [PAD, WIDTH - 8])
const efY = linearScale([0, efMax.value], [HEIGHT - PAD, 8])

const rocTicks = niceTicks(0, 1, 4)
const efXTicks = niceTicks(0, 1, 4)
const efYTicks = computed(() => niceTicks(0, efMax.value, 4))

function path(
  points: EnrichmentPoint[],
  xScale: ReturnType<typeof linearScale>,
  yScale: ReturnType<typeof linearScale>,
): string {
  return points
    .map(
      (point, index) =>
        `${index === 0 ? 'M' : 'L'}${xScale.map(point.x).toFixed(2)},${yScale.map(point.y).toFixed(2)}`,
    )
    .join(' ')
}
</script>

<template>
  <div class="enrichment-charts">
    <figure>
      <figcaption>ROC</figcaption>
      <svg :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img" aria-label="ROC curve">
        <line
          :x1="PAD"
          :y1="HEIGHT - PAD"
          :x2="WIDTH - 8"
          :y2="HEIGHT - PAD"
          class="axis"
        />
        <line :x1="PAD" :y1="8" :x2="PAD" :y2="HEIGHT - PAD" class="axis" />
        <g v-for="tick in rocTicks" :key="`x-${tick}`">
          <line :x1="rocX.map(tick)" :y1="HEIGHT - PAD" :x2="rocX.map(tick)" :y2="HEIGHT - PAD + 4" class="axis" />
          <text :x="rocX.map(tick)" :y="HEIGHT - PAD + 13" class="tick" text-anchor="middle">{{ tick }}</text>
        </g>
        <text :x="WIDTH / 2" :y="HEIGHT - 2" class="label" text-anchor="middle">FPR</text>
        <text :x="8" :y="14" class="label">TPR</text>
        <path :d="path(roc, rocX, rocY)" class="roc" />
      </svg>
    </figure>

    <figure>
      <figcaption>Enrichment</figcaption>
      <svg :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img" aria-label="Enrichment factor curve">
        <line
          :x1="PAD"
          :y1="HEIGHT - PAD"
          :x2="WIDTH - 8"
          :y2="HEIGHT - PAD"
          class="axis"
        />
        <line :x1="PAD" :y1="8" :x2="PAD" :y2="HEIGHT - PAD" class="axis" />
        <g v-for="tick in efXTicks" :key="`ex-${tick}`">
          <line :x1="efX.map(tick)" :y1="HEIGHT - PAD" :x2="efX.map(tick)" :y2="HEIGHT - PAD + 4" class="axis" />
          <text :x="efX.map(tick)" :y="HEIGHT - PAD + 13" class="tick" text-anchor="middle">{{ tick }}</text>
        </g>
        <g v-for="tick in efYTicks" :key="`ey-${tick}`">
          <line :x1="PAD - 4" :y1="efY.map(tick)" :x2="PAD" :y2="efY.map(tick)" class="axis" />
          <text :x="PAD - 6" :y="efY.map(tick) + 3" class="tick" text-anchor="end">{{ tick }}</text>
        </g>
        <text :x="WIDTH / 2" :y="HEIGHT - 2" class="label" text-anchor="middle">fraction</text>
        <text :x="8" :y="14" class="label">EF</text>
        <path :d="path(enrichment, efX, efY)" class="ef" />
      </svg>
    </figure>
  </div>
</template>

<style scoped>
.enrichment-charts {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 12px;
}

figure {
  margin: 0;
}

figcaption {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-bottom: 4px;
}

svg {
  width: 300px;
  max-width: 100%;
  height: auto;
  overflow: visible;
}

.axis {
  stroke: var(--el-border-color);
  stroke-width: 1;
}

.tick,
.label {
  fill: var(--el-text-color-secondary);
  font-size: 9px;
}

.roc {
  fill: none;
  stroke: var(--el-color-primary);
  stroke-width: 2;
}

.ef {
  fill: none;
  stroke: var(--el-color-success);
  stroke-width: 2;
}
</style>
