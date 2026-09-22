<script setup lang="ts">
import { Cpu, Crop, Expand, Files, Fold, Grid, InfoFilled, Position, List } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { t } = useI18n()

interface NavItem {
  to: string
  icon: typeof Grid
  key: string
}

const items: NavItem[] = [
  { to: '/workbench', icon: Grid, key: 'nav.workbench' },
  { to: '/molecules', icon: Files, key: 'nav.molecules' },
  { to: '/box', icon: Crop, key: 'nav.box' },
  { to: '/docking', icon: Position, key: 'nav.docking' },
  { to: '/batch', icon: List, key: 'nav.batch' },
  { to: '/environment', icon: Cpu, key: 'nav.environment' },
  { to: '/about', icon: InfoFilled, key: 'nav.about' },
]

const collapsed = computed(() => ui.sidebarCollapsed)
</script>

<template>
  <aside class="sidebar" :class="{ 'is-collapsed': collapsed }">
    <nav class="sidebar__nav">
      <router-link
        v-for="item in items"
        :key="item.to"
        class="sidebar__item"
        :to="item.to"
        :title="collapsed ? t(item.key) : undefined"
      >
        <el-icon class="sidebar__icon"><component :is="item.icon" /></el-icon>
        <span class="sidebar__label">{{ t(item.key) }}</span>
      </router-link>
    </nav>

    <button
      class="sidebar__toggle"
      type="button"
      :title="collapsed ? '展开 / Expand' : '收起 / Collapse'"
      @click="ui.toggleSidebar()"
    >
      <el-icon><component :is="collapsed ? Expand : Fold" /></el-icon>
    </button>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  width: var(--vs-sidebar-width);
  flex: none;
  padding: 12px 10px;
  background: var(--vs-bg-surface);
  border-right: 1px solid var(--vs-border);
  transition: width 0.16s ease;
}

.sidebar.is-collapsed {
  width: var(--vs-sidebar-width-collapsed);
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
}

.sidebar__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  border-radius: var(--vs-radius);
  color: var(--vs-text-muted);
  font-size: 13.5px;
  text-decoration: none;
  transition:
    background 0.14s ease,
    color 0.14s ease;
}

.sidebar__item:hover {
  background: var(--vs-bg-sunken);
  color: var(--vs-text);
  text-decoration: none;
}

.sidebar__item.router-link-active {
  background: var(--vs-accent-soft);
  color: var(--vs-accent);
  font-weight: 600;
}

.sidebar__icon {
  font-size: 16px;
  flex: none;
}

.sidebar.is-collapsed .sidebar__label {
  display: none;
}

.sidebar.is-collapsed .sidebar__item {
  justify-content: center;
  padding: 9px 0;
}

.sidebar__toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  background: transparent;
  color: var(--vs-text-faint);
  cursor: pointer;
}

.sidebar__toggle:hover {
  color: var(--vs-text);
  border-color: var(--vs-border-strong);
}
</style>
