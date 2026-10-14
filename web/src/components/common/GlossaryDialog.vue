<script setup lang="ts">
/**
 * Glossary dialog: the docking vocabulary in one place.
 *
 * Deliberately read-only and short — each entry states the concept and, where
 * it matters, what it does *not* mean (energies are not comparable across
 * scoring functions, RMSD l.b./u.b. is relative to the top pose, a geometry
 * warning is not a verdict).
 */
import { ElDialog } from 'element-plus'
import { useI18n } from 'vue-i18n'

const open = defineModel<boolean>({ required: true })

const { t } = useI18n()

/** Ordered so a first-time reader meets the concepts in the order they appear. */
const TERM_KEYS = [
  'receptorLigand',
  'pdbqt',
  'box',
  'candidateSites',
  'scoringFunction',
  'affinity',
  'exhaustiveness',
  'seed',
  'rmsdBounds',
  'redockRmsd',
  'validation',
  'clustering',
  'ifp',
] as const
</script>

<template>
  <ElDialog v-model="open" :title="t('glossary.title')" width="min(720px, 92vw)">
    <p class="glossary__intro">{{ t('glossary.intro') }}</p>
    <dl class="glossary">
      <template v-for="key in TERM_KEYS" :key="key">
        <dt class="glossary__term">{{ t(`glossary.terms.${key}.term`) }}</dt>
        <dd class="glossary__desc">{{ t(`glossary.terms.${key}.desc`) }}</dd>
      </template>
    </dl>
  </ElDialog>
</template>

<style scoped>
.glossary__intro {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--vs-text-faint);
}

.glossary {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr);
  gap: 8px 16px;
  margin: 0;
  font-size: 12.5px;
}

.glossary__term {
  font-weight: 600;
  color: var(--vs-text);
}

.glossary__desc {
  margin: 0;
  line-height: 1.65;
  color: var(--vs-text-muted);
}

@media (max-width: 720px) {
  .glossary {
    grid-template-columns: minmax(0, 1fr);
  }

  .glossary__desc {
    margin-bottom: 6px;
  }
}
</style>
