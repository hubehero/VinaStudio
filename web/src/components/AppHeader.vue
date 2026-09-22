<script setup lang="ts">
import { FolderOpened, Link, Setting } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import brandUrl from '@/assets/brand.svg'
import ProjectDialog from '@/components/ProjectDialog.vue'
import SettingsDialog from '@/components/SettingsDialog.vue'
import StatusPill from '@/components/StatusPill.vue'
import { useSystemStore } from '@/stores/system'
import { useUiStore } from '@/stores/ui'

const system = useSystemStore()
const ui = useUiStore()
const { t } = useI18n()

const projectDialogRef = ref<InstanceType<typeof ProjectDialog>>()
const settingsDialogRef = ref<InstanceType<typeof SettingsDialog>>()

function openProjectDialog(): void {
  projectDialogRef.value?.open()
}

function openSettings(): void {
  settingsDialogRef.value?.open()
}

const serviceState = computed<'ok' | 'warn' | 'error' | 'idle'>(() => {
  if (system.reachable) return 'ok'
  return system.error ? 'error' : 'warn'
})

const serviceLabel = computed(() => {
  if (system.reachable) return t('status.connected')
  return system.error ? t('status.disconnected') : t('status.connecting')
})

const channelState = computed<'ok' | 'warn' | 'idle'>(() =>
  ui.socketStatus === 'open' ? 'ok' : 'warn',
)

const channelLabel = computed(() => {
  switch (ui.socketStatus) {
    case 'open':
      return t('status.connected')
    case 'connecting':
      return t('status.connecting')
    default:
      return t('status.disconnected')
  }
})
</script>

<template>
  <header class="header">
    <div class="header__brand">
      <img class="header__logo" :src="brandUrl" :alt="t('app.name')" />
      <div class="header__titles">
        <div class="header__name">{{ t('app.name') }}</div>
        <div class="header__tagline">{{ t('app.tagline') }}</div>
      </div>
    </div>

    <div class="header__status">
      <StatusPill
        :state="channelState"
        :label="`${t('status.eventChannel')} · ${channelLabel}`"
        :pulse="ui.socketStatus !== 'open'"
      />
      <StatusPill :state="serviceState" :label="serviceLabel" />
    </div>

    <div class="header__actions">
      <a class="header__docs" href="/api/docs" target="_blank" rel="noreferrer">
        <el-icon><Link /></el-icon>
        <span>{{ t('header.documentation') }}</span>
      </a>
      <el-button text size="small" @click="openProjectDialog">
        <el-icon><FolderOpened /></el-icon>
        <span>{{ t('project.openProject') }}</span>
      </el-button>
      <el-tooltip :content="t('settings.title')" placement="bottom">
        <el-button text size="small" @click="openSettings">
          <el-icon><Setting /></el-icon>
        </el-button>
      </el-tooltip>
    </div>
  </header>

  <ProjectDialog ref="projectDialogRef" />
  <SettingsDialog ref="settingsDialogRef" />
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  gap: 18px;
  height: var(--vs-header-height);
  padding: 0 18px;
  background: var(--vs-bg-surface);
  border-bottom: 1px solid var(--vs-border);
  flex: none;
}

.header__brand {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.header__logo {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  flex: none;
}

.header__titles {
  min-width: 0;
}

.header__name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.header__tagline {
  font-size: 11.5px;
  color: var(--vs-text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header__status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.header__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.header__docs {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  font-size: 12.5px;
  color: var(--vs-text-muted);
}

.header__docs:hover {
  color: var(--vs-accent);
  text-decoration: none;
}

@media (max-width: 1180px) {
  .header__tagline {
    display: none;
  }
}
</style>
