<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import StatusPill from '@/components/StatusPill.vue'
import { useSystemStore } from '@/stores/system'
import { useUiStore } from '@/stores/ui'

const system = useSystemStore()
const ui = useUiStore()
const { t } = useI18n()

onMounted(() => {
  if (!system.capabilities) {
    void system.refresh()
  }
})

const version = computed(() => system.info?.app.version ?? '—')
const hostLabel = computed(() => (ui.desktop ? t('about.hostDesktop') : t('about.hostBrowser')))
</script>

<template>
  <div class="vs-page">
    <div class="vs-page__head">
      <div>
        <h1 class="vs-page__title">{{ t('about.title') }}</h1>
        <p class="vs-page__subtitle">{{ t('about.subtitle') }}</p>
      </div>
      <StatusPill
        :state="ui.desktop ? 'ok' : 'warn'"
        :label="ui.desktop ? t('about.desktopHost') : t('about.browserHost')"
        :detail="version"
      />
    </div>

    <div class="vs-card">
      <div class="vs-card__body about__intro">
        <p class="about__lead">{{ t('app.tagline') }}</p>
        <p class="vs-muted">{{ hostLabel }}</p>
      </div>
    </div>

    <div v-if="system.capabilities" class="vs-card">
      <div class="vs-card__header">
        <div class="vs-card__title">{{ t('about.capabilities') }}</div>
      </div>
      <div class="vs-card__body about__caps">
        <div class="about__caps-block">
          <h4>{{ t('about.scoringFunctions') }}</h4>
          <el-table :data="system.capabilities.scoringFunctions" size="small" row-key="name">
            <el-table-column prop="label" min-width="120" :label="t('about.name')" />
            <el-table-column :label="t('about.weights')" width="130" align="right">
              <template #default="{ row }">
                <span class="vs-mono">{{ row.weights }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('about.nativeMaps')" min-width="230">
              <template #default="{ row }">
                <StatusPill
                  :state="row.nativeMaps ? 'ok' : 'warn'"
                  :label="row.nativeMaps ? t('about.nativeMaps') : t('about.needsExternalMaps')"
                />
              </template>
            </el-table-column>
            <el-table-column prop="notes" min-width="280">
              <template #default="{ row }">
                <span class="vs-faint note">{{ row.notes }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="about__caps-grid">
          <div>
            <h4>{{ t('about.ligandFormats') }}</h4>
            <div class="chips">
              <span v-for="fmt in system.capabilities.ligandInputFormats" :key="fmt" class="chip">
                {{ fmt }}
              </span>
            </div>
          </div>
          <div>
            <h4>{{ t('about.receptorFormats') }}</h4>
            <div class="chips">
              <span v-for="fmt in system.capabilities.receptorInputFormats" :key="fmt" class="chip">
                {{ fmt }}
              </span>
            </div>
          </div>
          <div>
            <h4>{{ t('about.outputFormats') }}</h4>
            <div class="chips">
              <span v-for="fmt in system.capabilities.outputFormats" :key="fmt" class="chip">
                {{ fmt }}
              </span>
            </div>
          </div>
          <div>
            <h4>{{ t('about.viewer') }}</h4>
            <div class="chips">
              <span class="chip is-accent">{{ system.capabilities.viewer.engine }}</span>
            </div>
            <p class="vs-faint note">{{ t('about.viewerNote') }}</p>
          </div>
        </div>
      </div>
    </div>

    <div class="vs-card">
      <div class="vs-card__header">
        <div class="vs-card__title">{{ t('about.citations') }}</div>
      </div>
      <div class="vs-card__body">
        <ol class="citations">
          <li v-for="entry in system.citations" :key="entry.doi" class="citations__item">
            <div class="citations__title">{{ entry.title }}</div>
            <div class="citations__meta">
              {{ entry.authors }} · {{ entry.venue }} · {{ entry.year }}
            </div>
            <div class="citations__doi vs-mono">doi:{{ entry.doi }}</div>
          </li>
        </ol>
        <el-empty
          v-if="!system.citations.length"
          :description="t('errors.loadFailed', { message: system.error ?? t('common.none') })"
          :image-size="64"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.about__intro {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.about__lead {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.about__intro p {
  margin: 0;
  font-size: 13px;
}

.about__caps {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.about__caps h4 {
  margin-bottom: 8px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--vs-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.about__caps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 18px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid var(--vs-border);
  background: var(--vs-bg-sunken);
  font-family: var(--vs-font-mono);
  font-size: 11.5px;
  color: var(--vs-text-muted);
}

.chip.is-accent {
  border-color: transparent;
  background: var(--vs-accent-soft);
  color: var(--vs-accent);
}

.note {
  font-size: 12px;
  line-height: 1.6;
}

.citations {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.citations__item {
  padding-left: 13px;
  border-left: 2px solid var(--vs-border);
}

.citations__title {
  font-size: 13.5px;
  font-weight: 600;
}

.citations__meta,
.citations__doi {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.citations__doi {
  color: var(--vs-text-faint);
}
</style>
