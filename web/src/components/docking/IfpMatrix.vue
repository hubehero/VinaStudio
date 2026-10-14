<template>
  <div class="ifp-canvas-wrap" v-loading="loading" :element-loading-text="t('ifp.loading')">
    <canvas
      ref="el"
      class="ifp-canvas"
      @click="onClick"
      @mousemove="onMove"
      @mouseleave="onLeave"
    />
  </div>
  <div class="ifp-legend">
    <span class="ifp-legend__item" v-for="ty in types" :key="ty">
      <i class="ifp-dot" :class="`ifp-dot--${ty}`"></i>{{ t(`docking.interactions.types.${ty}`) }}
    </span>
    <span class="ifp-legend__note">{{
      mode === 'job' ? t('ifp.legendNote') : t('ifp.legendNoteGroup')
    }}</span>
  </div>
</template>

<script setup lang="ts">
/** Pure canvas bit matrix — rows are poses (job) or ligands (group), no fetch. */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useUiStore } from '@/stores/ui'
import type { IfpMatrixRow, IfpResidue, IfpType } from '@/types/api'

const props = withDefaults(
  defineProps<{
    rows: IfpMatrixRow[]
    residues: IfpResidue[]
    types: IfpType[]
    mode: 'job' | 'group'
    loading?: boolean
    /** Column-header first-cell text (job: poses, group: ligands). */
    poseHeader?: string
    ligandHeader?: string
    /** Job mode: the pose the 3D stage shows; group mode uses internal selection. */
    activeIndex?: number | null
  }>(),
  { loading: false, poseHeader: '', ligandHeader: '', activeIndex: null },
)

const emit = defineEmits<{ select: [index: number] }>()

const { t } = useI18n()
const ui = useUiStore()
const el = ref<HTMLCanvasElement | null>(null)
const hoverIndex = ref<number | null>(null)
const groupActive = ref<number | null>(null)

// Geometry constants — pinned by design §2.2, do not tune.
const ROW_H = 18
const HEADER_H = 64
const SUB_W = 8
const SUB_GAP = 1
const GRP_GAP = 6
const CELL_W = SUB_W * 3 + SUB_GAP * 2
const COL_W = CELL_W + GRP_GAP
const LABEL_W_JOB = 44
const LABEL_W_GROUP = 150

const TYPE_TOKEN: Record<IfpType, string> = {
  ionic: '--vs-danger',
  hydrogen_bond: '--vs-info',
  hydrophobic: '--vs-success',
}

/** Canvas cannot inherit CSS custom properties; read them from the root. */
const tokenCache = new Map<string, string>()
function cssVar(name: string): string {
  let value = tokenCache.get(name)
  if (value === undefined) {
    value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    tokenCache.set(name, value)
  }
  return value
}

const headerW = computed(() => (props.mode === 'job' ? 104 : 180))
const labelW = computed(() => (props.mode === 'job' ? LABEL_W_JOB : LABEL_W_GROUP))
const selected = computed(() => (props.mode === 'job' ? props.activeIndex : groupActive.value))

function rowFromEvent(event: MouseEvent): number | null {
  const canvas = el.value
  if (!canvas) {
    return null
  }
  const rect = canvas.getBoundingClientRect()
  const y = event.clientY - rect.top
  if (y < HEADER_H) {
    return null
  }
  const index = Math.floor((y - HEADER_H) / ROW_H)
  return index >= 0 && index < props.rows.length ? index : null
}

function onClick(event: MouseEvent): void {
  const index = rowFromEvent(event)
  if (index === null) {
    return
  }
  if (props.mode === 'group') {
    // Selection is sticky on purpose: no 3D stage to keep it in step with.
    groupActive.value = index
  }
  emit('select', index)
}

function onMove(event: MouseEvent): void {
  const index = rowFromEvent(event)
  if (index !== hoverIndex.value) {
    hoverIndex.value = index
  }
}

function onLeave(): void {
  hoverIndex.value = null
}

function truncateTo(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
  if (ctx.measureText(text).width <= maxWidth) {
    return text
  }
  let cut = text
  while (cut.length > 1 && ctx.measureText(`${cut}…`).width > maxWidth) {
    cut = cut.slice(0, -1)
  }
  return `${cut}…`
}

function draw(): void {
  const canvas = el.value
  if (!canvas) {
    return
  }
  const dpr = window.devicePixelRatio || 1
  const w = Math.max(headerW.value + props.residues.length * COL_W - GRP_GAP, headerW.value)
  const h = HEADER_H + props.rows.length * ROW_H
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    return
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)
  ctx.font = `10px ${cssVar('--vs-font-mono')}`
  ctx.textBaseline = 'middle'

  // ① cluster-alternating row bands
  ctx.fillStyle = cssVar('--vs-bg-app')
  for (let i = 0; i < props.rows.length; i++) {
    const row = props.rows[i]
    if (!row || row.fpCluster % 2 === 0) {
      continue
    }
    ctx.globalAlpha = 0.55
    ctx.fillRect(0, HEADER_H + i * ROW_H, w, ROW_H)
    ctx.globalAlpha = 1
  }

  // ② cells: off = sunken, on = the type's semantic colour
  for (let i = 0; i < props.rows.length; i++) {
    const row = props.rows[i]
    if (!row) {
      continue
    }
    const y = HEADER_H + i * ROW_H
    const pairs = new Set(row.pairs.map((pair) => pair[0] * 10 + pair[1]))
    for (let resIdx = 0; resIdx < props.residues.length; resIdx++) {
      const groupX = headerW.value + resIdx * COL_W
      for (let ty = 0; ty < 3; ty++) {
        const typeName = props.types[ty]
        const on = pairs.has(resIdx * 10 + ty) && typeName !== undefined
        ctx.fillStyle = on ? cssVar(TYPE_TOKEN[typeName]) : cssVar('--vs-bg-sunken')
        ctx.fillRect(groupX + ty * (SUB_W + SUB_GAP), y, SUB_W, ROW_H)
      }
    }
  }

  // ③ sunken header, group separators, header underline
  ctx.fillStyle = cssVar('--vs-bg-sunken')
  ctx.fillRect(0, 0, w, HEADER_H)
  ctx.fillStyle = cssVar('--vs-border')
  for (let r = 1; r < props.residues.length; r++) {
    ctx.fillRect(headerW.value + r * COL_W - Math.ceil(GRP_GAP / 2), 0, 1, h)
  }
  ctx.fillRect(0, HEADER_H - 1, w, 1)

  // ④ header corner + rotated residue names
  ctx.fillStyle = cssVar('--vs-text-muted')
  ctx.textAlign = 'left'
  const corner = props.mode === 'job' ? props.poseHeader : props.ligandHeader
  ctx.fillText(corner, 6, HEADER_H - 10)
  for (let r = 0; r < props.residues.length; r++) {
    const residue = props.residues[r]
    if (!residue) {
      continue
    }
    const cx = headerW.value + r * COL_W + CELL_W / 2
    ctx.save()
    ctx.translate(cx, HEADER_H - 4)
    ctx.rotate(-Math.PI / 2)
    ctx.textAlign = 'left'
    ctx.fillText(`${residue.resname}${residue.resSeq}${residue.icode}`, 4, 0)
    ctx.restore()
  }

  // ⑤ row headers: F cluster, optional C cluster, right-aligned label
  for (let i = 0; i < props.rows.length; i++) {
    const row = props.rows[i]
    if (!row) {
      continue
    }
    const y = HEADER_H + i * ROW_H + ROW_H / 2
    const isActive = selected.value === i
    ctx.textAlign = 'left'
    ctx.fillStyle = isActive ? cssVar('--vs-accent') : cssVar('--vs-text')
    ctx.fillText(`F${row.fpCluster + 1}`, 6, y)
    if (props.mode === 'job' && row.rmsdCluster !== null) {
      ctx.fillStyle = cssVar('--vs-text')
      ctx.fillText(`C${row.rmsdCluster + 1}`, 36, y)
    }
    ctx.textAlign = 'right'
    ctx.fillStyle = cssVar('--vs-text')
    ctx.fillText(truncateTo(ctx, row.label, labelW.value), headerW.value - 6, y)
    ctx.textAlign = 'left'
  }

  // ⑥ active band and hover outline sit on top (accent-soft is translucent)
  for (let i = 0; i < props.rows.length; i++) {
    const y = HEADER_H + i * ROW_H
    if (selected.value === i) {
      ctx.fillStyle = cssVar('--vs-accent-soft')
      ctx.fillRect(0, y, w, ROW_H)
      ctx.fillStyle = cssVar('--vs-accent')
      ctx.fillRect(0, y, 2, ROW_H)
    } else if (hoverIndex.value === i) {
      ctx.strokeStyle = cssVar('--vs-border-strong')
      ctx.lineWidth = 1
      ctx.strokeRect(0.5, y + 0.5, w - 1, ROW_H - 1)
    }
  }
}

watch(
  () => [
    props.rows,
    props.residues,
    props.types,
    props.activeIndex,
    groupActive.value,
    hoverIndex.value,
  ],
  () => draw(),
)
// The token values differ per theme; a cached read must never leak across one.
watch(
  () => ui.resolvedTheme,
  () => {
    tokenCache.clear()
    draw()
  },
)
onMounted(() => draw())
</script>

<style scoped>
.ifp-canvas-wrap {
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  max-height: 420px;
  overflow: auto;
  background: var(--vs-bg-surface);
}
.ifp-canvas {
  display: block;
}
.ifp-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 8px;
  font-size: 11px;
  color: var(--vs-text-muted);
}
.ifp-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 4px;
  vertical-align: -1px;
}
.ifp-dot--ionic {
  background: var(--vs-danger);
}
.ifp-dot--hydrogen_bond {
  background: var(--vs-info);
}
.ifp-dot--hydrophobic {
  background: var(--vs-success);
}
</style>
