<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DepictAtom, DepictData, InteractionData } from '@/types/api'
import { downloadTextFile } from '@/utils/download'

const props = defineProps<{
  /** The full analysis result — the map must not collapse when a residue filter is active. */
  interactions: InteractionData[]
  depict: DepictData | null
  selectedKey: string | null
}>()

const emit = defineEmits<{ 'select-residue': [key: string] }>()

const { t } = useI18n()

const svgEl = ref<SVGSVGElement | null>(null)

type InteractionType = InteractionData['type']
type ColorKey = InteractionType | 'ring' | 'oxygen' | 'nitrogen' | 'sulfur' | 'halogen'

/** Okabe-Ito in one place: the map has to read for colour-vision-deficient users. */
const COLORS: Record<ColorKey, string> = {
  hydrogen_bond: '#009E73',
  ionic: '#0072B2',
  hydrophobic: '#E69F00',
  ring: '#9E9E9E',
  oxygen: '#D55E00',
  nitrogen: '#0072B2',
  sulfur: '#CC79A7',
  halogen: '#56B4E9',
}

const LEGEND_TYPES: readonly InteractionType[] = ['hydrogen_bond', 'ionic', 'hydrophobic']

const WIDTH = 760
const HEIGHT = 560
const CENTER = { x: WIDTH / 2, y: HEIGHT / 2 - 8 }
/** The unit-square depiction, drawn this many pixels wide (flipped: depiction y is up). */
const LIGAND_SPAN = 230
const INNER = { rx: 250, ry: 175 }
const OUTER = { rx: 330, ry: 240 }
const LABEL_HEIGHT = 22
const RING_PAD = 16

interface ResidueNode {
  key: string
  label: string
  /** ionic + hydrogen bonds live on the inner ring; hydrophobic contacts outside. */
  ring: 1 | 2
  width: number
  preferred: number
  x: number
  y: number
}

interface Connector {
  id: string
  type: InteractionType
  path: string
  distance: number
  label: { x: number; y: number } | null
}

interface PxAtom extends DepictAtom {
  px: number
  py: number
}

interface BondLine {
  x1: number
  y1: number
  x2: number
  y2: number
  width?: number
}

function residueKey(row: InteractionData): string {
  return `${row.receptorChain}|${row.receptorResSeq}|${row.receptorResidue}`
}

/** Display residue as ``ILE 208:A`` — same shape the table uses. */
function residueLabel(row: InteractionData): string {
  const parts: string[] = [row.receptorResidue]
  if (row.receptorResSeq) parts.push(row.receptorResSeq)
  if (row.receptorChain) parts.push(`:${row.receptorChain}`)
  return parts.join(' ')
}

function toPx(x: number, y: number): { px: number; py: number } {
  return {
    px: CENTER.x + (x - 0.5) * LIGAND_SPAN,
    py: CENTER.y - (y - 0.5) * LIGAND_SPAN,
  }
}

const ligandAtoms = computed<PxAtom[]>(() =>
  (props.depict?.atoms ?? []).map((atom) => ({ ...atom, ...toPx(atom.x, atom.y) })),
)

const ligandCentroid = computed<{ x: number; y: number } | null>(() => {
  let sx = 0
  let sy = 0
  let n = 0
  for (const atom of props.depict?.atoms ?? []) {
    if (atom.x3 == null || atom.y3 == null) continue
    sx += atom.x3
    sy += atom.y3
    n += 1
  }
  return n > 0 ? { x: sx / n, y: sy / n } : null
})

/**
 * Where a contact row lands on the drawn ligand. Contact rows and depiction
 * atoms share no index (RDKit restores the hydrogens the PDBQT dropped), so
 * the match is the original 3D coordinate, within half an angstrom.
 */
function anchorPx(row: InteractionData): { px: number; py: number } {
  let best: DepictAtom | null = null
  let bestSq = Infinity
  for (const atom of props.depict?.atoms ?? []) {
    if (atom.x3 == null || atom.y3 == null || atom.z3 == null) continue
    const dx = atom.x3 - row.ligandX
    const dy = atom.y3 - row.ligandY
    const dz = atom.z3 - row.ligandZ
    const d = dx * dx + dy * dy + dz * dz
    if (d < bestSq) {
      bestSq = d
      best = atom
    }
  }
  if (best && bestSq <= 0.25) return toPx(best.x, best.y)
  return { px: CENTER.x, py: CENTER.y }
}

const layout = computed(() => {
  const nodes = buildNodes()
  placeNodes(nodes)
  return { nodes, connectors: buildConnectors(nodes) }
})

function buildNodes(): ResidueNode[] {
  const groups = new Map<string, InteractionData[]>()
  for (const row of props.interactions) {
    const key = residueKey(row)
    const list = groups.get(key)
    if (list) list.push(row)
    else groups.set(key, [row])
  }

  const centroid = ligandCentroid.value
  const nodes: ResidueNode[] = []
  let fallbackIndex = 0
  for (const [key, rows] of groups) {
    const first = rows[0]
    if (!first) continue
    const types = new Set(rows.map((row) => row.type))
    const ring: 1 | 2 = types.has('ionic') || types.has('hydrogen_bond') ? 1 : 2

    // Preferred direction: where the residue meets the ligand in 3D, so the
    // label starts near its real position instead of an arbitrary slot.
    let mx = 0
    let my = 0
    for (const row of rows) {
      mx += row.receptorX
      my += row.receptorY
    }
    mx /= rows.length
    my /= rows.length
    let preferred: number
    if (centroid && Math.abs(mx - centroid.x) + Math.abs(my - centroid.y) > 1e-6) {
      preferred = Math.atan2(my - centroid.y, mx - centroid.x)
    } else {
      // No real direction (degenerate geometry): golden angle spreads evenly.
      preferred = fallbackIndex * 2.399963229728653
      fallbackIndex += 1
    }

    const label = residueLabel(first)
    nodes.push({ key, label, ring, width: label.length * 7.4 + 18, preferred, x: 0, y: 0 })
  }
  return nodes
}

/**
 * Relax node angles until neighbouring labels fit; the ring is only a
 * suggestion, labels may never overlap (§8 fallback if 3D-derived angles
 * still collide: this relaxation is the layout).
 */
function placeNodes(nodes: ResidueNode[]): void {
  const rings = [
    { ring: 1 as const, ellipse: INNER },
    { ring: 2 as const, ellipse: OUTER },
  ]
  for (const { ring, ellipse } of rings) {
    const group = nodes.filter((node) => node.ring === ring).sort((a, b) => a.preferred - b.preferred)
    if (group.length === 0) continue
    const first = group[0]
    if (!first) continue
    if (group.length === 1) {
      assign(first, ellipse, first.preferred)
      continue
    }
    const radius = (ellipse.rx + ellipse.ry) / 2
    const angles = group.map((node) => node.preferred)
    for (let iter = 0; iter < 24; iter++) {
      let moved = false
      for (let i = 0; i < group.length; i++) {
        const j = (i + 1) % group.length
        const currentNode = group[i]
        const nextNode = group[j]
        const currentAngle = angles[i]
        const nextAngle = angles[j]
        if (!currentNode || !nextNode || currentAngle == null || nextAngle == null) continue
        const need = ((currentNode.width + nextNode.width) / 2 + RING_PAD) / radius
        const gap = j === 0 ? nextAngle + Math.PI * 2 - currentAngle : nextAngle - currentAngle
        if (gap < need) {
          const push = (need - gap) / 2
          angles[i] = currentAngle - push
          angles[j] = nextAngle + push
          moved = true
        }
      }
      if (!moved) break
    }
    group.forEach((node, i) => {
      const angle = angles[i]
      if (angle != null) assign(node, ellipse, angle)
    })
  }
}

function assign(node: ResidueNode, ellipse: { rx: number; ry: number }, angle: number): void {
  const a = ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)
  node.x = CENTER.x + ellipse.rx * Math.cos(a)
  node.y = CENTER.y + ellipse.ry * Math.sin(a)
}

function buildConnectors(nodes: ResidueNode[]): Connector[] {
  const byKey = new Map(nodes.map((node) => [node.key, node]))
  // One connector per residue per type: the closest contact represents them all.
  const closest = new Map<string, Map<InteractionType, InteractionData>>()
  for (const row of props.interactions) {
    const key = residueKey(row)
    let types = closest.get(key)
    if (!types) {
      types = new Map()
      closest.set(key, types)
    }
    const existing = types.get(row.type)
    if (!existing || row.distance < existing.distance) types.set(row.type, row)
  }

  const connectors: Connector[] = []
  for (const [key, types] of closest) {
    const node = byKey.get(key)
    if (!node) continue
    for (const [type, row] of types) {
      const anchor = anchorPx(row)
      const edge = edgePoint(node, anchor)
      const dx = edge.px - anchor.px
      const dy = edge.py - anchor.py
      const len = Math.hypot(dx, dy) || 1
      const end = { px: anchor.px + (dx / len) * 7, py: anchor.py + (dy / len) * 7 }
      if (type === 'hydrophobic') {
        connectors.push({ id: `${key}|${type}`, type, path: arcPath(edge, end), distance: row.distance, label: null })
      } else {
        const mx = (edge.px + end.px) / 2
        const my = (edge.py + end.py) / 2
        const ox = mx - CENTER.x
        const oy = my - CENTER.y
        const olen = Math.hypot(ox, oy) || 1
        connectors.push({
          id: `${key}|${type}`,
          type,
          path: `M ${edge.px} ${edge.py} L ${end.px} ${end.py}`,
          distance: row.distance,
          label: { x: mx + (ox / olen) * 11, y: my + (oy / olen) * 11 },
        })
      }
    }
  }
  return connectors
}

/** Point where a connector leaves the residue label box, aimed at the anchor. */
function edgePoint(node: ResidueNode, target: { px: number; py: number }): { px: number; py: number } {
  const dx = target.px - node.x
  const dy = target.py - node.y
  const hw = node.width / 2 + 3
  const hh = LABEL_HEIGHT / 2 + 3
  const tx = Math.abs(dx) < 1e-6 ? Infinity : hw / Math.abs(dx)
  const ty = Math.abs(dy) < 1e-6 ? Infinity : hh / Math.abs(dy)
  const t = Math.min(tx, ty, 1)
  return { px: node.x + dx * t, py: node.y + dy * t }
}

/** Hydrophobic contacts bow away from the ligand instead of crossing it. */
function arcPath(from: { px: number; py: number }, to: { px: number; py: number }): string {
  const mx = (from.px + to.px) / 2
  const my = (from.py + to.py) / 2
  const vx = mx - CENTER.x
  const vy = my - CENTER.y
  const len = Math.hypot(vx, vy) || 1
  return `M ${from.px} ${from.py} Q ${mx + (vx / len) * 34} ${my + (vy / len) * 34} ${to.px} ${to.py}`
}

const ligandBonds = computed<BondLine[]>(() => {
  const byIdx = new Map(ligandAtoms.value.map((atom) => [atom.idx, atom]))
  const lines: BondLine[] = []
  for (const bond of props.depict?.bonds ?? []) {
    const a = byIdx.get(bond.a1)
    const b = byIdx.get(bond.a2)
    if (!a || !b) continue
    if (bond.order >= 2 && !bond.aromatic) {
      const dx = b.px - a.px
      const dy = b.py - a.py
      const len = Math.hypot(dx, dy) || 1
      const ox = (-dy / len) * 2.2
      const oy = (dx / len) * 2.2
      lines.push(
        { x1: a.px + ox, y1: a.py + oy, x2: b.px + ox, y2: b.py + oy, width: 2 },
        { x1: a.px - ox, y1: a.py - oy, x2: b.px - ox, y2: b.py - oy, width: 2 },
      )
    } else {
      lines.push({ x1: a.px, y1: a.py, x2: b.px, y2: b.py, width: bond.aromatic ? 2.6 : 2 })
    }
  }
  return lines
})

/** Carbons are the vertices; everything else gets its element circle. */
const labelledAtoms = computed(() => ligandAtoms.value.filter((atom) => atom.symbol !== 'C'))

function atomStroke(atom: PxAtom): string {
  const symbol = atom.symbol.toUpperCase()
  if (symbol === 'O') return COLORS.oxygen
  if (symbol === 'N') return COLORS.nitrogen
  if (symbol === 'S') return COLORS.sulfur
  if (symbol === 'F' || symbol === 'CL' || symbol === 'BR' || symbol === 'I') return COLORS.halogen
  return '#111111'
}

function atomText(atom: PxAtom): string {
  if (atom.charge > 0) return `${atom.symbol}${atom.charge > 1 ? atom.charge : ''}+`
  if (atom.charge < 0) return `${atom.symbol}-`
  return atom.symbol
}

function dashFor(type: InteractionType): string {
  if (type === 'hydrogen_bond') return '6 4'
  if (type === 'ionic') return '1.5 3'
  return ''
}

const legend = computed(() => {
  const items: { type: InteractionType; x: number; label: string }[] = []
  let x = 14
  for (const type of LEGEND_TYPES) {
    const label = t(`docking.interactions.types.${type}`)
    items.push({ type, x, label })
    x += 34 + label.length * 13 + 26
  }
  return items
})

const distanceLabels = computed(() => layout.value.connectors.filter((connector) => connector.label))

function exportSvg(): void {
  const svg = svgEl.value
  if (!svg) return
  const source = new XMLSerializer().serializeToString(svg)
  downloadTextFile(source, 'interactions-2d.svg', 'image/svg+xml')
  ElMessage.success(t('docking.interactions2d.exportDone'))
}

defineExpose({ exportSvg })
</script>

<template>
  <div class="interactions2d">
    <svg
      ref="svgEl"
      class="interactions2d__svg"
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      xmlns="http://www.w3.org/2000/svg"
      font-family="sans-serif"
      role="img"
      :aria-label="t('docking.interactions2d.title')"
    >
      <g>
        <template v-for="item in legend" :key="item.type">
          <line
            :x1="item.x"
            :x2="item.x + 18"
            y1="16"
            y2="16"
            :stroke="COLORS[item.type]"
            stroke-width="3"
            :stroke-dasharray="dashFor(item.type)"
          />
          <text
            :x="item.x + 24"
            y="20"
            class="legend__label"
            font-size="12"
            style="fill: var(--vs-text-muted, #666666)"
          >{{ item.label }}</text>
        </template>
      </g>

      <g class="contacts">
        <path
          v-for="connector in layout.connectors"
          :key="connector.id"
          :d="connector.path"
          fill="none"
          :stroke="COLORS[connector.type]"
          stroke-width="2"
          :stroke-dasharray="dashFor(connector.type)"
        />
        <text
          v-for="connector in distanceLabels"
          :key="`d-${connector.id}`"
          :x="connector.label?.x"
          :y="connector.label?.y"
          class="contacts__distance"
          font-size="11"
          text-anchor="middle"
          style="
            fill: var(--vs-text-muted, #666666);
            paint-order: stroke;
            stroke: var(--vs-bg-surface, #ffffff);
            stroke-width: 3px;
          "
        >
          {{ connector.distance.toFixed(1) }}
        </text>
      </g>

      <g class="ligand">
        <line
          v-for="(line, idx) in ligandBonds"
          :key="`b-${idx}`"
          :x1="line.x1"
          :y1="line.y1"
          :x2="line.x2"
          :y2="line.y2"
          :stroke="COLORS.ring"
          :stroke-width="line.width ?? 2"
        />
        <g v-for="atom in labelledAtoms" :key="`a-${atom.idx}`">
          <circle
            :cx="atom.px"
            :cy="atom.py"
            r="9"
            fill="#ffffff"
            :stroke="atomStroke(atom)"
            stroke-width="1.6"
          />
          <text
            :x="atom.px"
            :y="atom.py"
            class="ligand__atom"
            font-size="10"
            font-weight="700"
            :fill="atomStroke(atom)"
            text-anchor="middle"
            dominant-baseline="central"
          >
            {{ atomText(atom) }}
          </text>
        </g>
      </g>

      <g
        v-for="node in layout.nodes"
        :key="node.key"
        class="node"
        :class="{ 'node--selected': node.key === selectedKey }"
        :transform="`translate(${node.x} ${node.y})`"
        role="button"
        :aria-label="node.label"
        tabindex="0"
        @click="emit('select-residue', node.key)"
        @keydown.enter="emit('select-residue', node.key)"
      >
        <rect
          :x="-node.width / 2"
          :y="-LABEL_HEIGHT / 2"
          :width="node.width"
          :height="LABEL_HEIGHT"
          rx="11"
          class="node__box"
          :stroke="node.key === selectedKey ? 'var(--el-color-primary)' : COLORS.ring"
          :stroke-width="node.key === selectedKey ? 2 : 1.2"
          style="fill: var(--vs-bg-surface, #ffffff)"
        />
        <text
          y="1"
          class="node__label"
          font-size="12"
          text-anchor="middle"
          dominant-baseline="central"
          style="fill: var(--vs-text, #222222)"
        >
          {{ node.label }}
        </text>
      </g>

      <text
        :x="14"
        :y="HEIGHT - 14"
        class="note"
        font-size="11"
        style="fill: var(--vs-text-muted, #888888)"
      >{{ t('docking.interactions2d.note') }}</text>
    </svg>
  </div>
</template>

<style scoped>
.interactions2d__svg {
  display: block;
  width: 100%;
  height: auto;
  max-height: 340px;
}

.legend__label {
  font-size: 12px;
  fill: var(--vs-text-muted, #666666);
}

.contacts__distance {
  font-size: 11px;
  fill: var(--vs-text-muted, #666666);
  text-anchor: middle;
  paint-order: stroke;
  stroke: var(--vs-bg-surface, #ffffff);
  stroke-width: 3px;
}

.ligand__atom {
  font-size: 10px;
  font-weight: 700;
}

.node {
  cursor: pointer;
}

.node__box {
  fill: var(--vs-bg-surface, #ffffff);
}

.node__label {
  font-size: 12px;
  fill: var(--vs-text, #222222);
  paint-order: stroke;
}

.node--selected .node__label {
  font-weight: 700;
}

.note {
  font-size: 11px;
  fill: var(--vs-text-muted, #888888);
}
</style>
