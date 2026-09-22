<script setup lang="ts">
import en from 'element-plus/es/locale/lang/en'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import AppHeader from '@/components/AppHeader.vue'
import AppSidebar from '@/components/AppSidebar.vue'
import WorkspaceWizard from '@/components/WorkspaceWizard.vue'
import { clearNativeCommands, registerNativeCommands } from '@/api/native'
import { pickFiles, pickSaveFile } from '@/api/bridge'
import { eventSocket, type ServerEvent } from '@/api/ws'
import { useDockingStore } from '@/stores/docking'
import { useProjectStore } from '@/stores/project'
import { useSystemStore } from '@/stores/system'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'

const ui = useUiStore()
const system = useSystemStore()
const docking = useDockingStore()
const workspace = useWorkspaceStore()
const project = useProjectStore()
const router = useRouter()
const { t } = useI18n()

const elementLocale = computed(() => (ui.locale === 'zh-CN' ? zhCn : en))

const uptime = computed(() => {
  const seconds = system.health?.uptimeSeconds
  if (seconds === undefined) {
    return '—'
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}${t('common.seconds')}`
  }
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${Math.round(seconds % 60)}s`
})

let healthTimer: ReturnType<typeof setInterval> | null = null
let disposeStatus: (() => void) | null = null
let disposeEvents: (() => void) | null = null

function onServerEvent(event: ServerEvent): void {
  // Job events carry a jobId and the worker's kind in `type`; control frames
  // (hello/pong) have no jobId and are ignored by the store.
  docking.handleWsEvent(event as Record<string, unknown>)
}

function startServices() {
  // Only connect WebSocket and start health timer after workspace is confirmed
  if (disposeStatus === null) {
    disposeStatus = eventSocket.onStatus((status) => ui.setSocketStatus(status))
    disposeEvents = eventSocket.onEvent(onServerEvent)
    eventSocket.connect()
  }
  if (healthTimer === null) {
    healthTimer = setInterval(() => void system.refreshHealth(), 10_000)
  }
}

function stopServices() {
  if (healthTimer !== null) {
    clearInterval(healthTimer)
    healthTimer = null
  }
  // Both subscriptions must be released: the socket is a module singleton, so
  // a stale listener would fire again after a remount.
  disposeStatus?.()
  disposeStatus = null
  disposeEvents?.()
  disposeEvents = null
  eventSocket.close()
}

onMounted(async () => {
  // Vue has rendered its first frame, so the inline splash can go. A timer
  // would either flash a blank window or outlive the first paint.
  document.getElementById('boot-splash')?.remove()

  // Parallelize independent init calls
  await Promise.allSettled([
    ui.init(),
    workspace.fetchWorkspace(),
  ])

  // Only proceed with system refresh + services if workspace is configured
  if (workspace.isConfigured) {
    await system.refresh()
    startServices()
  }

  registerNativeCommands({
    newProject: () => {
      project.newProject()
      ElMessage.info(t('common.success'))
    },
    openProject: async () => {
      const paths = await pickFiles({
        title: t('project.openProject'),
        filters: 'VinAStudio Project (*.vinaproj)',
      })
      if (paths.length > 0) {
        const ok = await project.loadProject(paths[0]!)
        if (ok) {
          ElMessage.success(t('project.loadedSuccess'))
        } else {
          ElMessage.error(t('project.loadedFailed'))
        }
      }
    },
    saveProject: async () => {
      const path = await project.saveProject()
      if (path) {
        ElMessage.success(t('project.savedSuccess'))
      } else {
        ElMessage.error(t('project.savedFailed'))
      }
    },
    saveProjectAs: async () => {
      const path = await pickSaveFile(
        t('project.saveAs'),
        `${project.projectName}.vinaproj`,
        'VinAStudio Project (*.vinaproj)',
      )
      if (path) {
        const result = await project.saveProjectAs(path)
        if (result) {
          ElMessage.success(t('project.savedSuccess'))
        } else {
          ElMessage.error(t('project.savedFailed'))
        }
      }
    },
    setLocale: (locale) => {
      void ui.setLocalePreference(locale)
    },
  })
  void router.isReady()
})

onBeforeUnmount(() => {
  stopServices()
  clearNativeCommands()
})

function onWorkspaceComplete() {
  // No reload needed — workspace store is already updated reactively
  // Just need to fetch system data and start services
  void system.refresh().then(() => startServices())
}
</script>

<template>
  <el-config-provider v-cloak :locale="elementLocale">
    <!-- Loading splash while workspace is being checked -->
    <div v-if="workspace.loading" class="workspace-loading">
      <div class="workspace-loading__spinner"></div>
    </div>

    <!-- Show workspace wizard on first launch -->
    <WorkspaceWizard
      v-else-if="!workspace.isConfigured"
      @complete="onWorkspaceComplete"
    />

    <!-- Main shell -->
    <div v-else class="shell">
      <AppHeader />

      <div class="shell__body">
        <AppSidebar />
        <main class="shell__main">
          <router-view v-slot="{ Component }">
            <transition name="vs-fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </main>
      </div>

      <footer class="shell__statusbar">
        <span class="vs-mono">{{ t('app.name') }} {{ system.info?.app.version ?? '' }}</span>
        <span class="sep">·</span>
        <span>{{ t('status.uptime') }} {{ uptime }}</span>
        <span class="sep">·</span>
        <span>{{ t('status.clients') }} {{ system.health?.eventClients ?? 0 }}</span>
        <span class="shell__home vs-mono" :title="workspace.workspacePath">
          {{ workspace.workspaceName || (system.info?.home ?? '') }}
        </span>
      </footer>
    </div>
  </el-config-provider>
</template>

<style scoped>
.workspace-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: var(--vs-bg-app, #0d1526);
}

.workspace-loading__spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--vs-border, #30363d);
  border-top-color: var(--accent-primary, #4fd1c5);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--vs-bg-app);
}

.shell__body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.shell__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.shell__statusbar {
  display: flex;
  align-items: center;
  gap: 7px;
  height: var(--vs-statusbar-height);
  padding: 0 14px;
  flex: none;
  border-top: 1px solid var(--vs-border);
  background: var(--vs-bg-surface);
  font-size: 11.5px;
  color: var(--vs-text-faint);
}

.shell__home {
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 40%;
}

.sep {
  opacity: 0.5;
}
</style>
