import * as $3Dmol from '3dmol'
import { onBeforeUnmount, onMounted, ref, shallowRef, type Ref } from 'vue'

/** How the receptor backbone is drawn. */
export type ReceptorRepresentation = 'cartoon' | 'trace' | 'stick' | 'line' | 'sphere'

/** How the receptor is coloured. All of these are 3Dmol built-ins. */
export type ReceptorColourScheme = 'spectrum' | 'chain' | 'ss' | 'element'

/** How the ligand is drawn. */
export type LigandRepresentation = 'stick' | 'sphere' | 'line'

/**
 * Solvent-excluded / accessible surface kinds 3Dmol can compute.
 *
 * Note what these are *not*: none of them is a hydrophobicity or electrostatic
 * map, so the interface must not label them as one.
 */
export type SurfaceKind = 'VDW' | 'SAS' | 'SES'

/**
 * Rendering quality presets — controls visual fidelity vs performance.
 *
 * This only affects the 3D viewer rendering, NOT docking calculations.
 * All scientific results (affinity, poses, energies) are computed by
 * Vina in the Python backend and are completely unaffected by this setting.
 */
export type RenderQuality = 'low' | 'medium' | 'high'

/**
 * Quality preset configuration.
 *
 * - `cartoonQuality`: Controls the number of segments in cartoon ribbons
 * - `shapeQuality`: Controls the tessellation of spheres and cylinders
 * - `aoStrength`: Ambient occlusion intensity (0 = disabled)
 * - `aoRadius`: AO sampling radius in Angstroms
 * - `maxInteractions`: Maximum number of interaction annotations to render
 * - `antialias`: WebGL anti-aliasing
 */
export interface RenderQualityPreset {
  name: string
  description: string
  cartoonQuality: number
  shapeQuality: number
  aoStrength: number
  aoRadius: number
  maxInteractions: number
  antialias: boolean
}

/** Quality presets — low prioritizes performance, high prioritizes visuals. */
export const RENDER_QUALITY_PRESETS: Record<RenderQuality, RenderQualityPreset> = {
  low: {
    name: 'Performance',
    description: 'Fast rendering for large molecules or low-end devices',
    cartoonQuality: 8,
    shapeQuality: 1,
    aoStrength: 0,
    aoRadius: 0,
    maxInteractions: 15,
    antialias: false,
  },
  medium: {
    name: 'Balanced',
    description: 'Good balance of performance and visual quality',
    cartoonQuality: 10,
    shapeQuality: 2,
    aoStrength: 0.15,
    aoRadius: 3.0,
    maxInteractions: 30,
    antialias: true,
  },
  high: {
    name: 'Quality',
    description: 'Best visuals for screenshots and demos',
    cartoonQuality: 14,
    shapeQuality: 3,
    aoStrength: 0.2,
    aoRadius: 5.0,
    maxInteractions: 50,
    antialias: true,
  },
}

/** Which WebGL renderer the viewer actually got, probed once per session. */
export interface RendererInfo {
  /** UNMASKED_RENDERER_WEBGL (or RENDERER) string, verbatim. */
  renderer: string
  /** True when the string names a CPU rasteriser — frames will be slow. */
  software: boolean
}

/**
 * Shared renderer probe result.
 *
 * Chromium silently serves SwiftShader when the GPU is blocklisted, so the
 * app cannot assume hardware acceleration — this ref lets the viewport and
 * settings tell the user which renderer they are actually on.
 */
export const rendererInfo = ref<RendererInfo | null>(null)

/** Strings that only ever appear on CPU rasterisers. */
const SOFTWARE_RENDERER_RE =
  /swiftshader|llvmpipe|softpipe|software rasterizer|microsoft basic render|gdi generic/i

/** Ask the GL context who it is; safe to call once after viewer creation. */
function probeRenderer(viewer: $3Dmol.GLViewer): void {
  if (rendererInfo.value !== null) return
  // 3Dmol exposes no public GL handle: `renderer` is private in the typings
  // but present at runtime, and its context is the shared (singleton) one, so
  // a single probe describes every viewer in the page.
  const renderer = (
    viewer as unknown as {
      renderer?: { getContext?: () => WebGL2RenderingContext | null }
    }
  ).renderer
  const gl = renderer?.getContext?.()
  if (!gl) return
  const name = (() => {
    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info')
    if (debugInfo) {
      return String(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL))
    }
    return String(gl.getParameter(gl.RENDERER))
  })()
  if (name) {
    rendererInfo.value = { renderer: name, software: SOFTWARE_RENDERER_RE.test(name) }
  }
}

/** Interaction data for 3D visualization. */
export interface InteractionData {
  type: 'hydrogen_bond' | 'hydrophobic' | 'ionic'
  receptorX: number
  receptorY: number
  receptorZ: number
  ligandX: number
  ligandY: number
  ligandZ: number
  receptorResidue?: string
  /** Receptor-side identifiers carried by the analysis rows; the residue
   * highlight key needs them (absent on older/synthetic callers). */
  receptorChain?: string
  receptorResSeq?: string
  ligandAtom?: string
  distance?: number
}

/**
 * Residue key exactly as the 2D map and the interactions table build it:
 * `chain|resSeq|resname`. Same template, same fields — the highlight must
 * agree with the row the user clicked, never an approximation of it.
 */
function contactResidueKey(row: InteractionData): string {
  return `${row.receptorChain}|${row.receptorResSeq}|${row.receptorResidue}`
}

/** Overlay colour for the selected residue — distinct from every contact colour. */
const HIGHLIGHT_COLOR = '#f59e0b'
/** Adjacent atoms further apart than this are not bridged (ring closures). */
const HIGHLIGHT_MAX_BOND = 2.5

/** A concrete centre for an atom, or null when the coordinates are absent. */
function atomCenter(atom: $3Dmol.AtomSpec | undefined): { x: number; y: number; z: number } | null {
  if (atom?.x === undefined || atom.y === undefined || atom.z === undefined) {
    return null
  }
  return { x: atom.x, y: atom.y, z: atom.z }
}

export interface ViewerStyle {
  receptor: ReceptorRepresentation
  receptorColour: ReceptorColourScheme
  ligand: LigandRepresentation
  surface: SurfaceKind | null
  surfaceOpacity: number
}

export const DEFAULT_VIEWER_STYLE: ViewerStyle = {
  receptor: 'cartoon',
  receptorColour: 'spectrum',
  ligand: 'stick',
  surface: null,
  surfaceOpacity: 0.75,
}

/** A box in the same terms the backend uses: centre plus three edge lengths. */
export interface BoxGeometry {
  center: [number, number, number]
  size: [number, number, number]
  color?: string
}

/**
 * The twelve edges of a box, as index pairs into a corner list ordered
 * ``(x0|x1, y0|y1, z0|z1)``.
 */
const BOX_EDGES: ReadonlyArray<readonly [number, number]> = [
  [0, 1], [1, 2], [2, 3], [3, 0], // bottom face
  [4, 5], [5, 6], [6, 7], [7, 4], // top face
  [0, 4], [1, 5], [2, 6], [3, 7], // vertical edges
]

/**
 * Thin lifecycle wrapper around a 3Dmol GLViewer.
 *
 * 3Dmol holds WebGL resources that must be released explicitly, so the viewer
 * is owned by a class and never stored in a reactive proxy: `shallowRef` keeps
 * Vue from walking the (very large) Three.js object graph.
 */
export class MoleculeViewer {
  readonly raw: $3Dmol.GLViewer
  private disposed = false
  /** Edge shapes making up the current search box. */
  private boxShapes: $3Dmol.GLShape[] = []
  private receptorModel: $3Dmol.GLModel | null = null
  private ligandModel: $3Dmol.GLModel | null = null
  private surfaceId: number | null = null
  private style: ViewerStyle = { ...DEFAULT_VIEWER_STYLE }
  private pendingBox: BoxGeometry | null = null
  /** ID of a pending requestAnimationFrame render, for batching. */
  private _renderFrame: number | null = null

  /** Shapes drawn for the current interaction set, so only they are removed. */
  private interactionShapes: $3Dmol.GLShape[] = []
  private boxFrame: number | null = null

  /** Current rendering quality preset. */
  private currentQuality: RenderQuality = 'medium'

  constructor(container: HTMLElement, options: { background?: string; quality?: RenderQuality } = {}) {
    this.currentQuality = options.quality ?? 'medium'
    const preset = RENDER_QUALITY_PRESETS[this.currentQuality]

    // 3Dmol installs its own ResizeObserver on the container and renders the
    // canvas at 100% of it, so no extra resize plumbing is needed here.
    this.raw = $3Dmol.createViewer(container, {
      backgroundColor: options.background ?? '#0d1526',
      antialias: preset.antialias,
      cartoonQuality: preset.cartoonQuality,
      disableFog: true,
    })

    // Enable ambient occlusion for depth shading — makes crevices and pockets
    // visually deeper without any extra geometry.  Strength and radius are
    // controlled by the quality preset.
    if (preset.aoStrength > 0) {
      try {
        this.raw.setViewStyle({
          style: 'ambientOcclusion',
          strength: preset.aoStrength,
          radius: preset.aoRadius,
        })
      } catch {
        // AO may not be supported on all WebGL implementations; degrade gracefully.
      }
    }

    probeRenderer(this.raw)
  }

  resize(): void {
    if (this.disposed) {
      return
    }
    this.raw.resize()
    this.raw.render()
  }

  /**
   * Schedule a render on the next animation frame, coalescing rapid calls.
   *
   * Many operations (loadReceptor, applyStyle, setBox) trigger a render, and
   * when they run in quick succession this avoids redundant draw calls.
   */
  private scheduleRender(): void {
    if (this._renderFrame !== null) {
      return
    }
    this._renderFrame = window.requestAnimationFrame(() => {
      this._renderFrame = null
      if (!this.disposed) {
        this.raw.render()
      }
    })
  }

  /**
   * Zoom by a factor, coalescing the redraw with any other pending update.
   *
   * Wheel bursts fire far faster than the screen can show frames; a direct
   * render per event spends a full AO pass on frames nobody sees.
   */
  zoomBy(scale: number): void {
    this.raw.zoom(scale)
    this.scheduleRender()
  }

  setBackground(color: string): void {
    // The type declares alpha as required even though the runtime defaults it.
    this.raw.setBackgroundColor(color, 1.0)
    this.raw.render()
  }

  /**
   * Change the rendering quality preset.
   *
   * This updates AO settings but does NOT recreate the viewer — cartoon quality
   * and anti-aliasing are set at construction time and cannot be changed at runtime.
   * For full effect, the viewer should be recreated with the new quality.
   *
   * This only affects visual rendering, NOT docking calculations.
   */
  setQuality(quality: RenderQuality): void {
    this.currentQuality = quality
    const preset = RENDER_QUALITY_PRESETS[quality]

    // Update ambient occlusion
    try {
      if (preset.aoStrength > 0) {
        this.raw.setViewStyle({
          style: 'ambientOcclusion',
          strength: preset.aoStrength,
          radius: preset.aoRadius,
        })
      } else {
        // Reset to default view style (no AO)
        this.raw.setViewStyle({ style: 'default' })
      }
    } catch {
      // AO may not be supported; degrade gracefully.
    }

    this.scheduleRender()
  }

  /** Get the current quality preset configuration. */
  getQualityPreset(): RenderQualityPreset {
    return RENDER_QUALITY_PRESETS[this.currentQuality]
  }

  clear(): void {
    this.raw.removeAllModels()
    this.raw.removeAllSurfaces()
    this.raw.removeAllLabels()
    // Shapes are removed through their owners instead of a blanket wipe:
    // every shape this viewer draws belongs to the box or the interaction set,
    // so tracking stays honest about who owns what.
    for (const shape of this.boxShapes) {
      this.raw.removeShape(shape)
    }
    for (const shape of this.interactionShapes) {
      this.raw.removeShape(shape)
    }
    // The viewer forgot the models, so the handles must not outlive them.
    this.receptorModel = null
    this.ligandModel = null
    this.boxShapes = []
    this.interactionShapes = []
    this.scheduleRender()
  }

  /**
   * Empty-state preview of the search box (20 A cube centred on the origin).
   * This is the same rendering a defined box uses, so the viewport proves the
   * WebGL pipeline end to end before anything is loaded.
   */
  drawReferenceFrame(options: { boxEdge?: number; boxColor?: string } = {}): void {
    const edge = options.boxEdge ?? 20
    this.drawBox({
      center: [0, 0, 0],
      size: [edge, edge, edge],
      color: options.boxColor ?? '#4fd1c5',
    })
    this.fit()
  }

  /**
   * Render a search box using Vina's semantics: centre in Angstrom and the
   * three edge lengths (not half-extents).
   *
   * The box is drawn as twelve thin cylinders (one per edge).  Lines would be
   * cheaper but WebGL line width is capped at 1 px on most drivers, making
   * them nearly invisible when zoomed out; thin cylinders are always visible
   * and don't suffer from the diagonal artifact a wireframe box would add.
   */
  drawBox(spec: BoxGeometry): void {
    this.removeBox()

    const [sizeX, sizeY, sizeZ] = spec.size
    const [centerX, centerY, centerZ] = spec.center
    const color = spec.color ?? '#4fd1c5'

    const minX = centerX - sizeX / 2
    const maxX = centerX + sizeX / 2
    const minY = centerY - sizeY / 2
    const maxY = centerY + sizeY / 2
    const minZ = centerZ - sizeZ / 2
    const maxZ = centerZ + sizeZ / 2

    const corners: Array<[number, number, number]> = [
      [minX, minY, minZ],
      [maxX, minY, minZ],
      [maxX, maxY, minZ],
      [minX, maxY, minZ],
      [minX, minY, maxZ],
      [maxX, minY, maxZ],
      [maxX, maxY, maxZ],
      [minX, maxY, maxZ],
    ]

    this.boxShapes = BOX_EDGES.map(([from, to]) => {
      const [x1, y1, z1] = corners[from]!
      const [x2, y2, z2] = corners[to]!
      return this.raw.addCylinder({
        start: { x: x1, y: y1, z: z1 },
        end: { x: x2, y: y2, z: z2 },
        color,
        radius: 0.04,
        fromCap: 2,
        toCap: 2,
      })
    })
    this.raw.render()
  }

  /**
   * Set the search box, coalescing rapid updates.
   *
   * Dragging the box changes the geometry every pointer move, and each change
   * has to rebuild twelve line shapes because 3Dmol finalises a shape once it
   * has been drawn. Scheduling on the next frame keeps that to one rebuild per
   * frame instead of one per event.
   */
  setBox(spec: BoxGeometry | null): void {
    if (spec === null) {
      this.pendingBox = null
      if (this.boxFrame !== null) {
        window.cancelAnimationFrame(this.boxFrame)
        this.boxFrame = null
      }
      this.removeBox()
      this.raw.render()
      return
    }

    this.pendingBox = spec
    if (this.boxFrame !== null) {
      return
    }
    this.boxFrame = window.requestAnimationFrame(() => {
      this.boxFrame = null
      const pending = this.pendingBox
      if (pending && !this.disposed) {
        this.drawBox(pending)
      }
    })
  }

  /** Get the box currently scheduled or drawn, for a drag handler to offset. */
  get box(): BoxGeometry | null {
    return this.pendingBox
  }

  /** Remove the box edges, if any are present. */
  removeBox(): void {
    for (const shape of this.boxShapes) {
      this.raw.removeShape(shape)
    }
    this.boxShapes = []
  }

  // -- appearance --------------------------------------------------------
  get currentStyle(): ViewerStyle {
    return { ...this.style }
  }

  /** Apply a full style spec, re-rendering only what actually changed. */
  async applyStyle(next: Partial<ViewerStyle>): Promise<void> {
    const merged = { ...this.style, ...next }
    const receptorChanged =
      merged.receptor !== this.style.receptor ||
      merged.receptorColour !== this.style.receptorColour
    const ligandChanged = merged.ligand !== this.style.ligand
    const surfaceChanged =
      merged.surface !== this.style.surface ||
      merged.surfaceOpacity !== this.style.surfaceOpacity

    this.style = merged

    if (receptorChanged) {
      this.applyReceptorStyle()
    }
    if (ligandChanged) {
      this.applyLigandStyle()
    }
    if (surfaceChanged) {
      await this.rebuildSurface()
    }
    this.scheduleRender()
  }

  private applyReceptorStyle(): void {
    const model = this.receptorModel
    if (model === null) {
      return
    }
    const rep = this.style.receptor
    const base = receptorColourSpec(this.style.receptorColour)
    switch (rep) {
      case 'cartoon':
        model.setStyle({}, { cartoon: { ...base, tubes: false, opacity: 1.0 } })
        break
      case 'stick':
        model.setStyle({}, { stick: { ...base, radius: 0.12 } })
        break
      case 'sphere':
        model.setStyle({}, { sphere: { ...base, scale: 0.22 } })
        break
      case 'line':
        model.setStyle({}, { line: { ...base, linewidth: 1.5 } })
        break
      default:
        model.setStyle({}, { [rep]: base } as Record<string, unknown>)
    }
  }

  private applyLigandStyle(): void {
    const model = this.ligandModel
    if (model === null) {
      return
    }
    // Single-atom molecules (metal ions like Na+, Ca2+) have no bonds, so stick
    // and line rendering would show nothing.  Force sphere rendering for them.
    const atoms = model.selectedAtoms({})
    const useSphere = atoms.length === 1
    model.setStyle({}, useSphere
      ? { sphere: { scale: 0.4, colorscheme: 'Jmol' } }
      : ligandStyle(this.style.ligand))
  }

  /**
   * Recompute the molecular surface, if one is selected.
   *
   * 3Dmol computes surfaces asynchronously over a worker pool, and the returned
   * handle is a promise unless a callback was supplied, so both shapes are
   * handled rather than assuming one.
   */
  private async rebuildSurface(): Promise<void> {
    this.removeSurface()
    const kind = this.style.surface
    const model = this.receptorModel
    if (kind === null || model === null) {
      return
    }

    const result = this.raw.addSurface(kind, {
      opacity: this.style.surfaceOpacity,
      colorscheme: 'whiteCarbon',
    }, { model })

    const resolved = typeof result === 'number' ? result : await Promise.resolve(result)
    if (typeof resolved === 'number') {
      this.surfaceId = resolved
    }
  }

  private removeSurface(): void {
    if (this.surfaceId !== null) {
      this.raw.removeSurface(this.surfaceId)
      this.surfaceId = null
    }
  }

  setProjection(orthographic: boolean): void {
    this.raw.setProjection(orthographic ? 'orthographic' : 'perspective')
    this.raw.render()
  }

  fit(): void {
    this.raw.zoomTo()
    this.raw.render()
  }

  /** Base64 PNG of the current framebuffer, for the export action. */
  pngDataUrl(): string {
    this.raw.render()
    return this.raw.pngURI()
  }

  // -- molecules ---------------------------------------------------------
  /**
   * Load a receptor and style it for inspection.
   *
   * The file must be PDB: 3Dmol cannot parse PDBQT, and the backend writes a
   * PDB alongside every prepared receptor precisely so the cartoon can be drawn.
   *
   * Callers must remove any existing receptor before calling this method.
   */
  async loadReceptor(url: string): Promise<void> {
    const text = await fetchMolecule(url)
    this.receptorModel = this.raw.addModel(text, 'pdb')
    this.applyReceptorStyle()
    this.scheduleRender()
  }

  /**
   * Load a ligand from SDF.
   *
   * SDF rather than PDBQT because SDF carries bond orders, so the sticks are
   * drawn with correct connectivity and the ring systems look right.
   *
   * Callers must remove any existing ligand before calling this method.
   */
  async loadLigand(url: string): Promise<void> {
    const text = await fetchMolecule(url)
    this.ligandModel = this.raw.addModel(text, 'sdf')
    this.applyLigandStyle()
    this.scheduleRender()
  }

  /** Remove the ligand, leaving the receptor in place. */
  removeLigand(): void {
    if (this.ligandModel !== null) {
      this.raw.removeModel(this.ligandModel)
      this.ligandModel = null
      // Coalesced: callers (applyMolecules) follow up with a load in the same
      // tick, and one drawn frame beats two back-to-back full passes.
      this.scheduleRender()
    }
  }

  /**
   * Load a pose from an inline SDF string.
   *
   * This is used for docked poses which are extracted from the multi-molecule
   * posesSdf result. The SDF carries bond orders so the stick rendering is
   * chemically correct.
   *
   * Callers must remove any existing ligand before calling this method.
   */
  loadPoseFromSdf(sdfContent: string): void {
    this.ligandModel = this.raw.addModel(sdfContent, 'sdf')
    this.applyLigandStyle()
    this.scheduleRender()
  }

  /** Remove the receptor, its surface and any ligand bound to it. */
  removeReceptor(): void {
    this.removeLigand()
    this.removeSurface()
    if (this.receptorModel !== null) {
      this.raw.removeModel(this.receptorModel)
      this.receptorModel = null
      // Coalesced with the load that invariably follows in the same tick.
      this.scheduleRender()
    }
  }

  // -- interactions --------------------------------------------------------

  /**
   * Draw protein-ligand interactions as 3D annotations.
   *
   * Interaction types and their visual representation:
   * - hydrogen_bond: green dashed cylinder + sphere at receptor atom
   * - hydrophobic: purple dashed cylinder
   * - ionic: blue dashed cylinder
   *
   * The visualization follows standard structural biology conventions:
   * - Green for hydrogen bonds (N/O atoms within 3.5 Å)
   * - Purple for hydrophobic contacts (C-C/C-S within 4.0 Å)
   * - Blue for contacts with a charged side chain
   */
  drawInteractions(interactions: InteractionData[]): void {
    this.removeInteractions()
    const preset = RENDER_QUALITY_PRESETS[this.currentQuality]
    const shapes: $3Dmol.GLShape[] = []

    // Limit the number of interactions based on quality preset
    const toRender = interactions.slice(0, preset.maxInteractions)

    for (const inter of toRender) {
      const start = { x: inter.receptorX, y: inter.receptorY, z: inter.receptorZ }
      const end = { x: inter.ligandX, y: inter.ligandY, z: inter.ligandZ }

      switch (inter.type) {
        case 'hydrogen_bond':
          shapes.push(this.raw.addCylinder({
            start,
            end,
            color: '#22c55e',
            radius: 0.06,
            dashed: true,
            dashLength: 0.25,
            gapLength: 0.12,
            fromCap: 2,
            toCap: 2,
          }))
          shapes.push(this.raw.addSphere({
            center: start,
            color: '#22c55e',
            radius: 0.12,
            opacity: 0.5,
            quality: preset.shapeQuality,
          }))
          break

        case 'hydrophobic':
          shapes.push(this.raw.addCylinder({
            start,
            end,
            color: '#a855f7',
            radius: 0.05,
            dashed: true,
            dashLength: 0.18,
            gapLength: 0.08,
            fromCap: 2,
            toCap: 2,
          }))
          break

        case 'ionic':
          shapes.push(this.raw.addCylinder({
            start,
            end,
            color: '#3b82f6',
            radius: 0.06,
            dashed: true,
            dashLength: 0.2,
            gapLength: 0.1,
            fromCap: 2,
            toCap: 2,
          }))
          break
      }
    }
    this.pushResidueHighlight(interactions, shapes)
    this.interactionShapes = shapes
    // Coalesced: filtering reassigns the interactions array several times per
    // user action, and each reassign would otherwise cost a full AO frame.
    this.scheduleRender()
  }

  /**
   * Thick stick overlay for the residue every given row names.
   *
   * A uniform `chain|resSeq|resname` key across the rows is how the 2D map's
   * residue filter reaches this viewer — the selection state lives in an
   * out-of-reach component, so the row set is the only signal available. A
   * mixed set means "all interactions" and highlights nothing; missing key
   * fields or a residue the receptor does not contain mean no highlight
   * rather than a guessed one. The shapes join `interactionShapes`, so
   * removeInteractions() clears them together with the contact annotations.
   */
  private pushResidueHighlight(rows: InteractionData[], shapes: $3Dmol.GLShape[]): void {
    const receptor = this.receptorModel
    if (!receptor || rows.length === 0) {
      return
    }
    const first = rows[0]
    if (!first?.receptorChain || !first.receptorResSeq || !first.receptorResidue) {
      return
    }
    const key = contactResidueKey(first)
    if (!rows.every((row) => contactResidueKey(row) === key)) {
      return
    }
    // 3Dmol's resi selector takes a number; a residue key that is not a plain
    // number (insertion codes, SDF-ligand rows with no resSeq) cannot be
    // located here, so it gets no highlight instead of a wrong one.
    const resSeq = Number(first.receptorResSeq)
    if (!Number.isFinite(resSeq)) {
      return
    }
    const atoms = receptor.selectedAtoms({
      chain: first.receptorChain,
      resi: resSeq,
      resn: first.receptorResidue,
    })
    if (atoms.length === 0) {
      return
    }
    const preset = RENDER_QUALITY_PRESETS[this.currentQuality]
    const quality = preset.shapeQuality
    if (atoms.length === 1) {
      const only = atomCenter(atoms[0])
      if (!only) return
      shapes.push(
        this.raw.addSphere({
          center: only,
          color: HIGHLIGHT_COLOR,
          radius: 0.24,
          quality,
        }),
      )
      return
    }
    let drawn = 0
    for (let i = 0; i < atoms.length - 1; i++) {
      const a = atomCenter(atoms[i])
      const b = atomCenter(atoms[i + 1])
      if (!a || !b) continue
      if (Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) > HIGHLIGHT_MAX_BOND) continue
      shapes.push(
        this.raw.addCylinder({
          start: a,
          end: b,
          color: HIGHLIGHT_COLOR,
          radius: 0.1,
          fromCap: 2,
          toCap: 2,
        }),
      )
      drawn += 1
    }
    if (drawn === 0) {
      // No adjacent pair within bonding distance (unusual geometry): dot
      // every atom so the selection still shows instead of vanishing.
      for (const atom of atoms) {
        const center = atomCenter(atom)
        if (!center) continue
        shapes.push(
          this.raw.addSphere({
            center,
            color: HIGHLIGHT_COLOR,
            radius: 0.16,
            quality,
          }),
        )
      }
    }
  }

  /** Remove the interaction annotations drawn by this viewer. */
  removeInteractions(): void {
    // Removing every shape would take the search box, the reference frame and
    // the coordinate axes with it, and the axes cannot be restored from here.
    for (const shape of this.interactionShapes) {
      this.raw.removeShape(shape)
    }
    this.interactionShapes = []
    this.scheduleRender()
  }

  /** Frame the receptor if present, otherwise the ligand. */
  focus(): void {
    if (this.receptorModel !== null) {
      this.raw.zoomTo({ model: this.receptorModel })
    } else if (this.ligandModel !== null) {
      this.raw.zoomTo({ model: this.ligandModel })
    } else {
      this.raw.zoomTo()
    }
    this.raw.render()
  }

  /** True once anything other than the empty-state box is on screen. */
  get hasMolecule(): boolean {
    return this.receptorModel !== null || this.ligandModel !== null
  }

  dispose(): void {
    if (this.disposed) {
      return
    }
    this.disposed = true
    this.boxShapes = []
    this.surfaceId = null
    if (this.boxFrame !== null) {
      window.cancelAnimationFrame(this.boxFrame)
      this.boxFrame = null
    }
    if (this._renderFrame !== null) {
      window.cancelAnimationFrame(this._renderFrame)
      this._renderFrame = null
    }
    // Stop the auto-rotation animation before tearing down the GL context so
    // the frame callback does not fire on a disposed viewer.
    try {
      this.raw.spin(false)
    } catch {
      // Already torn down; ignore.
    }
    try {
      this.clear()
    } catch {
      // The context can already be gone during teardown; nothing to do.
    }
  }
}

/**
 * Element colours and a bond style for the ligand.
 *
 * `Jmol` is the conventional colourscheme for small molecules.  Stick radii
 * are slightly thicker than the receptor's so the ligand stands out inside
 * a pocket without obscuring the cartoon behind it.
 */
function ligandStyle(kind: LigandRepresentation): Record<string, unknown> {
  const colorscheme = 'Jmol'
  switch (kind) {
    case 'sphere':
      return {
        stick: { radius: 0.14, colorscheme },
        sphere: { scale: 0.28, colorscheme },
      }
    case 'line':
      return { line: { linewidth: 2, colorscheme } }
    default:
      return { stick: { radius: 0.16, colorscheme } }
  }
}

/**
 * A 3Dmol style spec for the receptor colour scheme chosen in the UI.
 *
 * 3Dmol spells the per-residue rainbow as `color: "spectrum"` — its own
 * docs example does the same. Under `colorscheme` the string matches no
 * builtin scheme, so every cartoon atom logs "Could not interpret colorscheme
 * spectrum" and the drawing keeps atom colours instead of the rainbow.
 * `ss` and `element` are our labels, not the library's: the builtin ids are
 * `ssPyMol` and `default`. Non-cartoon styles read `color` but skip the value
 * "spectrum", so they keep their atom-colour fallback without warning.
 */
function receptorColourSpec(scheme: ReceptorColourScheme): Record<string, unknown> {
  if (scheme === 'spectrum') return { color: 'spectrum' }
  if (scheme === 'ss') return { colorscheme: 'ssPyMol' }
  if (scheme === 'element') return { colorscheme: 'default' }
  return { colorscheme: 'chain' }
}

/** Fetch a molecule file, reporting the status when it fails. */
async function fetchMolecule(url: string): Promise<string> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`could not load ${url}: ${response.status} ${response.statusText}`)
  }
  return await response.text()
}

/**
 * Mount a viewer into `container` and dispose it with the component.
 *
 * 3Dmol builds its WebGL framebuffer from the container's size at construction
 * time and warns that a zero-sized start leaves rendering broken, so creation
 * waits for a non-zero, stable layout box.
 */
export function useMoleculeViewer(
  container: Ref<HTMLElement | null>,
  options: {
    background?: string
    autoReferenceFrame?: boolean
    /** Preset, or a getter so a rebuild picks up the latest selection. */
    quality?: RenderQuality | (() => RenderQuality)
  } = {},
) {
  const viewer = shallowRef<MoleculeViewer | null>(null)
  const ready = ref(false)
  const error = ref<string | null>(null)
  let framesWaited = 0
  let lastWidth = 0
  let lastHeight = 0
  let rafId: number | null = null

  function resolvedOptions(): { background?: string; autoReferenceFrame?: boolean; quality?: RenderQuality } {
    const quality = typeof options.quality === 'function' ? options.quality() : options.quality
    return { background: options.background, autoReferenceFrame: options.autoReferenceFrame, quality }
  }

  function create(): void {
    const element = container.value
    if (!element) {
      return
    }

    const width = element.clientWidth
    const height = element.clientHeight
    // Require the same non-zero size on two consecutive frames: one frame is
    // not enough when the window is still being laid out.
    const stable = width > 0 && height > 0 && width === lastWidth && height === lastHeight
    lastWidth = width
    lastHeight = height

    if (!stable) {
      if (framesWaited < 60) {
        framesWaited += 1
        rafId = window.requestAnimationFrame(create)
      } else {
        error.value = 'viewport never reached a stable non-zero size'
      }
      return
    }

    try {
      const instance = new MoleculeViewer(element, resolvedOptions())
      if (options.autoReferenceFrame !== false) {
        instance.drawReferenceFrame()
      }
      viewer.value = instance
      ready.value = true
    } catch (cause) {
      // 3Dmol throws bare strings from its own factory, so log the raw value
      // and keep a readable message for the UI.
      console.error('[vinastudio] failed to create the 3Dmol viewer', cause)
      error.value = cause instanceof Error ? cause.message : String(cause)
    }
  }

  /**
   * Rebuild the viewer with the current options.
   *
   * Antialiasing and cartoon quality bind at construction time, so this is
   * the only way a quality-preset change takes full effect (setQuality alone
   * re-applies ambient occlusion). Callers re-assert theme, molecules and
   * annotations when `ready` flips back to true.
   */
  function recreate(): void {
    if (rafId !== null) {
      window.cancelAnimationFrame(rafId)
      rafId = null
    }
    viewer.value?.dispose()
    viewer.value = null
    ready.value = false
    const element = container.value
    if (element) {
      // GLViewer appends its canvas on construction and never removes it on
      // teardown — clear it or rebuilds stack canvases in the same box.
      for (const canvas of element.querySelectorAll('canvas')) {
        canvas.remove()
      }
    }
    framesWaited = 0
    lastWidth = 0
    lastHeight = 0
    error.value = null
    create()
  }

  onMounted(create)
  onBeforeUnmount(() => {
    // Cancel any pending rAF to prevent creating a viewer on a detached element
    if (rafId !== null) {
      window.cancelAnimationFrame(rafId)
      rafId = null
    }
    viewer.value?.dispose()
    viewer.value = null
    ready.value = false
  })

  return { viewer, ready, error, recreate }
}
