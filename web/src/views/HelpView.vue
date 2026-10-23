<script setup lang="ts">
/**
 * In-app user guide / FAQ.
 *
 * Short, task-oriented answers to the questions the interface itself provokes
 * ("why did my atom count drop?", "which pose should I trust?"), each linking
 * to the page where the action happens. Deep technical material stays in
 * `docs/`; this page only covers what someone hits while working.
 */
import { ElButton, ElInput } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import GlossaryDialog from '@/components/common/GlossaryDialog.vue'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const glossaryOpen = ref(false)
const query = ref('')
const openKey = ref<string | null>(null)

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
      { key: 'commandPalette' },
      { key: 'undoShortcuts' },
    ],
  },
  {
    key: 'input',
    items: [
      { key: 'typeWrong', to: '/molecules', navKey: 'nav.molecules' },
      { key: 'prepFailed', to: '/molecules', navKey: 'nav.molecules' },
      { key: 'prepDecisions', to: '/molecules', navKey: 'nav.molecules' },
      { key: 'fileMissing', to: '/molecules', navKey: 'nav.molecules' },
      { key: 'atomCount' },
    ],
  },
  {
    key: 'run',
    items: [
      { key: 'boxSize', to: '/box', navKey: 'nav.box' },
      { key: 'noSiteFound', to: '/box', navKey: 'nav.box' },
      { key: 'siteScreen', to: '/box', navKey: 'nav.box' },
      { key: 'ad4Maps', to: '/docking', navKey: 'nav.docking' },
      { key: 'dockingFailed', to: '/docking', navKey: 'nav.docking' },
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
      { key: 'interactionTypes' },
      { key: 'exportBundle' },
      { key: 'importBundle', to: '/report', navKey: 'nav.report' },
      { key: 'figureCaption' },
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
    items: [
      { key: 'windows' },
      { key: 'smartScreen' },
      { key: 'aaFlicker' },
      { key: 'updateCheck' },
      { key: 'offline' },
    ],
  },
]
const filteredSections = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return SECTIONS
  return SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) =>
      `${t(`help.items.${item.key}.q`)} ${t(`help.items.${item.key}.a`)}`
        .toLowerCase()
        .includes(needle),
    ),
  })).filter((section) => section.items.length > 0)
})

function openTopic(topic: string): void {
  const exists = SECTIONS.some((section) => section.items.some((item) => item.key === topic))
  if (!exists) return
  query.value = ''
  openKey.value = topic
  void nextTick(() => {
    document.getElementById(`help-${topic}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  })
}

function applyRouteTopic(): void {
  const topic = typeof route.query.topic === 'string' ? route.query.topic : ''
  if (topic) openTopic(topic)
}

onMounted(applyRouteTopic)
watch(() => route.query.topic, applyRouteTopic)
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

    <section class="vs-card help-view__search-card">
      <el-input
        v-model="query"
        clearable
        :placeholder="t('help.searchPlaceholder')"
        :aria-label="t('help.searchPlaceholder')"
      />
    </section>

    <section v-for="section in filteredSections" :key="section.key" class="vs-card">
      <div class="vs-card__header">
        <div class="vs-card__title">{{ t(`help.sections.${section.key}`) }}</div>
      </div>
      <div class="vs-card__body">
        <details
          v-for="item in section.items"
          :id="`help-${item.key}`"
          :key="item.key"
          class="help-item"
          :open="openKey === item.key || undefined"
        >
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

    <p v-if="filteredSections.length === 0" class="help-view__empty">
      {{ t('help.noResults') }}
    </p>

    <GlossaryDialog v-model="glossaryOpen" />
  </div>
</template>

<style scoped>
.help-view__search-card {
  padding: 12px 18px;
}

.help-view__empty {
  padding: 12px 4px;
  font-size: 13px;
  color: var(--vs-text-faint);
}

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
