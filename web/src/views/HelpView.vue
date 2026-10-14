<script setup lang="ts">
/**
 * In-app user guide / FAQ.
 *
 * Short, task-oriented answers to the questions the interface itself provokes
 * ("why did my atom count drop?", "which pose should I trust?"), each linking
 * to the page where the action happens. Deep technical material stays in
 * `docs/`; this page only covers what someone hits while working.
 */
import { ElButton } from 'element-plus'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import GlossaryDialog from '@/components/common/GlossaryDialog.vue'

const { t } = useI18n()
const router = useRouter()
const glossaryOpen = ref(false)

interface HelpItem {
  key: string
  /** Where the answer's action lives, when there is one. */
  to?: string
  navKey?: string
}

interface HelpSection {
  key: string
  items: HelpItem[]
}

const SECTIONS: HelpSection[] = [
  {
    key: 'start',
    items: [
      { key: 'whereToStart', to: '/workbench', navKey: 'nav.workbench' },
      { key: 'example', to: '/workbench', navKey: 'nav.workbench' },
    ],
  },
  {
    key: 'input',
    items: [
      { key: 'typeWrong', to: '/molecules', navKey: 'nav.molecules' },
      { key: 'prepFailed', to: '/molecules', navKey: 'nav.molecules' },
      { key: 'atomCount' },
    ],
  },
  {
    key: 'run',
    items: [
      { key: 'boxSize', to: '/box', navKey: 'nav.box' },
      { key: 'noSiteFound', to: '/box', navKey: 'nav.box' },
      { key: 'siteScreen', to: '/box', navKey: 'nav.box' },
      { key: 'exhaustiveness', to: '/docking', navKey: 'nav.docking' },
      { key: 'reproduce' },
    ],
  },
  {
    key: 'results',
    items: [
      { key: 'trustPose', to: '/report', navKey: 'nav.report' },
      { key: 'zeroEnergy' },
      { key: 'compareEnergy' },
    ],
  },
  {
    key: 'report',
    items: [
      { key: 'methods', to: '/report', navKey: 'nav.report' },
      { key: 'dataLocation', to: '/environment', navKey: 'nav.environment' },
    ],
  },
  {
    key: 'platform',
    items: [{ key: 'windows' }, { key: 'offline' }],
  },
]
</script>

<template>
  <div class="vs-page help-view">
    <div class="vs-page__head">
      <div>
        <h1 class="vs-page__title">{{ t('help.title') }}</h1>
        <p class="vs-page__subtitle">{{ t('help.subtitle') }}</p>
      </div>
      <ElButton size="small" @click="glossaryOpen = true">{{ t('glossary.button') }}</ElButton>
    </div>

    <section v-for="section in SECTIONS" :key="section.key" class="vs-card">
      <div class="vs-card__header">
        <div class="vs-card__title">{{ t(`help.sections.${section.key}`) }}</div>
      </div>
      <div class="vs-card__body">
        <details v-for="item in section.items" :key="item.key" class="help-item">
          <summary class="help-item__q">{{ t(`help.items.${item.key}.q`) }}</summary>
          <div class="help-item__panel">
            <p class="help-item__a">{{ t(`help.items.${item.key}.a`) }}</p>
            <ElButton
              v-if="item.to && item.navKey"
              text
              size="small"
              type="primary"
              @click="router.push(item.to)"
            >
              {{ t('help.open') }} · {{ t(item.navKey) }}
            </ElButton>
          </div>
        </details>
      </div>
    </section>

    <GlossaryDialog v-model="glossaryOpen" />
  </div>
</template>

<style scoped>
.help-item {
  border-bottom: 1px solid var(--vs-border);
  padding: 2px 0;
}

.help-item:last-child {
  border-bottom: none;
}

.help-item__q {
  padding: 9px 4px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--vs-text);
  list-style: none;
}

.help-item__q::-webkit-details-marker {
  display: none;
}

.help-item__q::before {
  content: '▸';
  display: inline-block;
  width: 14px;
  font-size: 10px;
  color: var(--vs-text-faint);
  transition: transform 0.15s ease;
}

.help-item[open] > .help-item__q::before {
  transform: rotate(90deg);
}

.help-item__q:hover {
  color: var(--vs-accent);
}

.help-item__panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 0 4px 12px 18px;
}

.help-item__a {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--vs-text-muted);
}
</style>
