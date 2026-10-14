/**
 * One-click setup of the bundled 1iep example.
 *
 * Loads imatinib + the c-Abl receptor, inspects and prepares both, picks them
 * as the pipeline receptor/ligand, and auto-boxes on the ligand — i.e. it runs
 * the whole setup chain a beginner would otherwise have to discover. The
 * docking run itself stays the user's click on the docking page, so the
 * expensive step is never started behind their back.
 */
import { computed, onMounted, ref } from 'vue'

import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'
import type { SampleFile } from '@/types/api'

const EXAMPLE_RECEPTOR = '1iep_receptorH.pdb'
const EXAMPLE_LIGAND = '1iep_ligand.sdf'
/** Same margin the box panel's autobox control defaults to. */
const EXAMPLE_EXTEND = 4.0

export interface ExampleSetupResult {
  ok: boolean
  /** Why it failed, for the caller to surface (already localised at the call site). */
  reason?: 'missing-samples' | 'load-failed' | 'prepare-failed' | 'box-failed'
}

export function useExampleSetup() {
  const molecules = useMoleculeStore()
  const box = useBoxStore()

  const running = ref(false)

  // The sample list arrives with the rest of the reference data, which only the
  // molecule panel used to request. The workbench needs it to know whether the
  // example is even present, so it asks for the same payload itself.
  onMounted(() => {
    if (!molecules.filters) void molecules.loadReferenceData()
  })

  function sampleNamed(name: string): SampleFile | null {
    return molecules.samples.find((sample) => sample.name === name) ?? null
  }

  /** The example is offered only when both input files are actually present. */
  const available = computed(
    () => sampleNamed(EXAMPLE_RECEPTOR) !== null && sampleNamed(EXAMPLE_LIGAND) !== null,
  )

  function itemIdFor(sample: SampleFile): string | null {
    return molecules.molecules.find((mol) => mol.path === sample.path)?.id ?? null
  }

  /** Load + inspect + prepare one sample file; returns its molecule id. */
  async function prepareSample(sample: SampleFile): Promise<string | null> {
    await molecules.loadSample(sample)
    const id = itemIdFor(sample)
    if (id === null) return null
    const item = molecules.molecules.find((mol) => mol.id === id)
    if (item?.status !== 'inspected' && item?.status !== 'prepared') return null
    if (item.status !== 'prepared') {
      await molecules.prepareMolecule(id)
    }
    const after = molecules.molecules.find((mol) => mol.id === id)
    return after?.status === 'prepared' ? id : null
  }

  async function setupExample(): Promise<ExampleSetupResult> {
    if (running.value) return { ok: false }
    const receptorSample = sampleNamed(EXAMPLE_RECEPTOR)
    const ligandSample = sampleNamed(EXAMPLE_LIGAND)
    if (!receptorSample || !ligandSample) return { ok: false, reason: 'missing-samples' }

    running.value = true
    try {
      const receptorId = await prepareSample(receptorSample)
      if (receptorId === null) return { ok: false, reason: 'prepare-failed' }
      const ligandId = await prepareSample(ligandSample)
      if (ligandId === null) return { ok: false, reason: 'prepare-failed' }

      // Picks are set after preparation on purpose: both setters only accept a
      // molecule that is already usable.
      molecules.setPipelineReceptor(receptorId)
      molecules.setPipelineLigand(ligandId)

      // Box on the prepared ligand when there is one, so the box matches the
      // geometry that will actually be docked; otherwise the sample's SDF.
      const ligand = molecules.molecules.find((mol) => mol.id === ligandId)
      const preparedSdf = ligand?.artifacts.find((artifact) => artifact.kind === 'sdf')?.path
      const boxed = await box.autoboxFromLigand(preparedSdf ?? ligandSample.path, EXAMPLE_EXTEND)
      if (!boxed) return { ok: false, reason: 'box-failed' }

      return { ok: true }
    } catch {
      return { ok: false, reason: 'load-failed' }
    } finally {
      running.value = false
    }
  }

  return { available, running, setupExample }
}
