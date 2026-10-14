/**
 * "Methods" paragraph generator.
 *
 * Turns the parameters a docking job **actually ran with** (persisted in
 * `job.json` and returned by `/api/docking/jobs/{id}/result`) plus the computed
 * results into a ready-to-paste Methods section for a report or paper.
 *
 * Deliberate rules:
 * - Every number comes from the run; nothing is defaulted into the text. A
 *   value that is missing is left out rather than guessed.
 * - Conditions are stated (random seed, community convention, prediction vs
 *   experiment) so the paragraph cannot be read as a stronger claim than the
 *   software makes.
 * - Pure module: no store, no DOM, so the wording can be checked by reading it.
 */

export type MethodsLang = 'zh' | 'en'

export interface MethodsInput {
  /** The job's request dict (snake_case, as persisted in job.json). */
  params: Record<string, unknown> | null
  receptorName: string | null
  ligandName: string | null
  versions: {
    app?: string | null
    vina?: string | null
    meeko?: string | null
    rdkit?: string | null
  }
  nPoses: number
  bestAffinity: number | null
  elapsedMs: number | null
  validation: { ok: number; warning: number; error: number } | null
  rmsd: { threshold: number; successRate: number } | null
  clusters: { nClusters: number; cutoff: number } | null
}

export interface MethodsText {
  /** The Methods section itself. */
  body: string
  /** Optional trailing note (may be pasted verbatim or dropped). */
  caveat: string
}

// -- readers (the params dict is `unknown` by contract) ----------------------

function readString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  return typeof value === 'string' && value.length > 0 ? value : null
}

function readNumber(source: Record<string, unknown>, key: string): number | null {
  const value = source[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function readBoolean(source: Record<string, unknown>, key: string): boolean {
  return source[key] === true
}

function readTriple(source: Record<string, unknown>, key: string): [number, number, number] | null {
  const value = source[key]
  if (!Array.isArray(value) || value.length !== 3) return null
  const [x, y, z] = value
  if (typeof x !== 'number' || typeof y !== 'number' || typeof z !== 'number') return null
  return [x, y, z]
}

function baseName(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path
}

function formatElapsed(ms: number | null): string | null {
  if (ms === null) return null
  const seconds = ms / 1000
  return seconds < 60 ? `${seconds.toFixed(1)} s` : `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`
}

function scoringLabel(scoring: string | null): string {
  if (scoring === 'vinardo') return 'Vinardo'
  if (scoring === 'ad4') return 'AutoDock4'
  return 'Vina'
}

// -- builder -----------------------------------------------------------------

export function buildMethodsText(input: MethodsInput, lang: MethodsLang): MethodsText {
  const params = input.params ?? {}
  const vina = input.versions.vina ?? null
  const meeko = input.versions.meeko ?? null
  const rdkit = input.versions.rdkit ?? null
  const app = input.versions.app ?? null

  const center = readTriple(params, 'center')
  const size = readTriple(params, 'size')
  const scoring = readString(params, 'scoring')
  const exhaustiveness = readNumber(params, 'exhaustiveness')
  const nPoses = readNumber(params, 'n_poses')
  const energyRange = readNumber(params, 'energy_range')
  const minRmsd = readNumber(params, 'min_rmsd')
  const spacing = readNumber(params, 'spacing')
  const cpu = readNumber(params, 'cpu')
  const seed = readNumber(params, 'seed')
  const noRefine = readBoolean(params, 'no_refine')
  const mapPaths = Array.isArray(params['map_paths']) ? params['map_paths'].length > 0 : false
  const flexPath = readString(params, 'flex_pdbqt_path')

  const zh = lang === 'zh'
  const sentences: string[] = []

  // ① software + engines
  const engines: string[] = []
  if (meeko) engines.push(`Meeko ${meeko}`)
  if (rdkit) engines.push(`RDKit ${rdkit}`)
  const engineClause = engines.length > 0 ? `（参数化：${engines.join('、')}）` : ''
  const appClause = app ? `，操作平台 VinaStudio ${app}` : ''
  sentences.push(
    zh
      ? `分子对接采用 AutoDock Vina${vina ? ` ${vina}` : ''} 完成${engineClause}${appClause}。`
      : `Molecular docking was performed with AutoDock Vina${vina ? ` ${vina}` : ''}${engines.length > 0 ? ` (parameterisation: ${engines.join(', ')})` : ''}${app ? `, driven by VinaStudio ${app}` : ''}.`,
  )

  // ② molecules (+ flexible side chains)
  if (input.receptorName || input.ligandName) {
    const receptor = input.receptorName ?? (zh ? '（未记录）' : '(not recorded)')
    const ligand = input.ligandName ?? (zh ? '（未记录）' : '(not recorded)')
    const flexClause = flexPath
      ? zh
        ? `；受体柔性侧链拆分为独立 PDBQT（${baseName(flexPath)}）`
        : `; flexible side chains were split into a separate PDBQT (${baseName(flexPath)})`
      : ''
    sentences.push(
      zh
        ? `受体文件为 ${receptor}，配体为 ${ligand}${flexClause}。`
        : `The receptor was ${receptor} and the ligand ${ligand}${flexClause}.`,
    )
  }

  // ③ search box
  if (center && size) {
    const spacingClause = spacing !== null ? (zh ? `，网格间距 ${spacing} Å` : `, grid spacing ${spacing} Å`) : ''
    sentences.push(
      zh
        ? `对接盒中心为 (${center.map((v) => v.toFixed(3)).join(', ')}) Å，边长 ${size.map((v) => v.toFixed(1)).join(' × ')} Å${spacingClause}。`
        : `The search box was centred at (${center.map((v) => v.toFixed(3)).join(', ')}) Å with edge lengths ${size.map((v) => v.toFixed(1)).join(' × ')} Å${spacingClause}.`,
    )
  }

  // ④ sampling parameters
  const paramBits: string[] = []
  paramBits.push(zh ? `打分函数 ${scoringLabel(scoring)}` : `scoring function ${scoringLabel(scoring)}`)
  if (exhaustiveness !== null) paramBits.push(`exhaustiveness = ${exhaustiveness}`)
  if (nPoses !== null) paramBits.push(zh ? `输出构象数 ${nPoses}` : `up to ${nPoses} poses`)
  if (energyRange !== null) paramBits.push(zh ? `能量窗口 ${energyRange} kcal/mol` : `energy range ${energyRange} kcal/mol`)
  if (minRmsd !== null) paramBits.push(zh ? `最小 RMSD ${minRmsd} Å` : `minimum RMSD ${minRmsd} Å`)
  if (cpu !== null) paramBits.push(zh ? `CPU 核心 ${cpu}（0 表示全部）` : `CPU cores ${cpu} (0 = all)`)
  sentences.push(zh ? `采样参数：${paramBits.join('，')}。` : `Sampling: ${paramBits.join(', ')}.`)

  // ⑤ seed (a reproducibility statement, not a parameter dump)
  if (seed !== null) {
    sentences.push(
      seed === 0
        ? zh
          ? '随机种子取 0，即每次运行的初始状态随机，结果不可逐位复现。'
          : 'The random seed was left at 0, i.e. randomised per run, so results are not exactly reproducible.'
        : zh
          ? `随机种子固定为 ${seed}，本次运行可复现。`
          : `The random seed was fixed at ${seed}, making this run reproducible.`,
    )
  }
  if (noRefine) {
    sentences.push(
      zh
        ? '本轮关闭了局域精修（no_refine），打分时不使用显式受体原子。'
        : 'Local refinement was disabled (no_refine), so explicit receptor atoms were not used in scoring.',
    )
  }
  if (scoring === 'ad4') {
    sentences.push(
      mapPaths
        ? zh
          ? 'AutoDock4 打分使用外部提供的 AutoGrid4 亲和力图（而非现场生成）。'
          : 'AutoDock4 scoring used externally supplied AutoGrid4 affinity maps (not generated on the fly).'
        : zh
          ? '注意：本次为 AutoDock4 打分，需外部 AutoGrid4 亲和力图；记录中未见地图路径。'
          : 'Note: AutoDock4 scoring requires external AutoGrid4 maps; no map path was recorded.',
    )
  }

  // ⑥ results
  const elapsed = formatElapsed(input.elapsedMs)
  const best = input.bestAffinity
  sentences.push(
    zh
      ? `共获得 ${input.nPoses} 个输出构象${best !== null ? `，最优结合自由能为 ${best.toFixed(2)} kcal/mol` : ''}${elapsed ? `，单次对接用时 ${elapsed}` : ''}。`
      : `${input.nPoses} pose(s) were output${best !== null ? `, with a best binding free energy of ${best.toFixed(2)} kcal/mol` : ''}${elapsed ? `, in ${elapsed}` : ''}.`,
  )

  // ⑦ geometry check (only when it was actually run)
  if (input.validation) {
    const { ok, warning, error } = input.validation
    sentences.push(
      zh
        ? `输出构象经内置几何体检（盒内、键长、键角、平面性、手性一致性）：${ok} 个通过、${warning} 个警告、${error} 个错误；该检查只做几何审查，不重新打分、不修改坐标。`
        : `Each pose was checked geometrically (inside the box, bond lengths, bond angles, planarity, chirality consistency): ${ok} passed, ${warning} warned, ${error} failed. This check only inspects geometry — it neither rescores nor edits coordinates.`,
    )
  }

  // ⑧ redocking RMSD (only when it was actually run)
  if (input.rmsd) {
    const rate = Math.round(input.rmsd.successRate * 100)
    sentences.push(
      zh
        ? `以参考配体做重对接 RMSD 对照，成功率 ${rate}%（阈值 ${input.rmsd.threshold} Å）。该阈值是社区惯例，不是硬性标准。`
        : `Redocking RMSD against the reference ligand gave a ${rate}% success rate (threshold ${input.rmsd.threshold} Å). That threshold is a community convention, not a rule.`,
    )
  }

  // ⑨ clustering (only when it was actually run)
  if (input.clusters) {
    sentences.push(
      zh
        ? `按 ${input.clusters.cutoff} Å 阈值对输出构象聚类，得到 ${input.clusters.nClusters} 个构象簇。`
        : `Poses were clustered at a ${input.clusters.cutoff} Å cutoff, yielding ${input.clusters.nClusters} cluster(s).`,
    )
  }

  const caveat = zh
    ? '注：以上为打分函数给出的预测值，不等同于实验测定的结合自由能；对接结果应结合对照实验审慎解读。'
    : 'Note: the values above are scoring-function predictions, not experimentally measured binding free energies; docking results should be interpreted with caution alongside experimental data.'

  // Chinese runs sentences together; English needs the separating space.
  return { body: sentences.join(zh ? '' : ' '), caveat }
}
