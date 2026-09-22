<script setup lang="ts">
import { Monitor, Moon, Sunny } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useUiStore, type ThemeMode } from '@/stores/ui'

const ui = useUiStore()
const { t } = useI18n()

const OPTIONS: ReadonlyArray<{ value: ThemeMode; icon: typeof Moon; key: string }> = [
  { value: 'dark', icon: Moon, key: 'header.themeDark' },
  { value: 'light', icon: Sunny, key: 'header.themeLight' },
  { value: 'system', icon: Monitor, key: 'header.themeSystem' },
]

const active = computed(() => OPTIONS.find((option) => option.value === ui.theme))
</script>

<template>
  <el-dropdown trigger="click" @command="(value: unknown) => ui.setTheme(String(value) as ThemeMode)">
    <el-button text :title="t('header.theme')">
      <el-icon><component :is="active?.icon ?? Moon" /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="option in OPTIONS"
          :key="option.value"
          :command="option.value"
          :class="{ 'is-current': option.value === ui.theme }"
        >
          <el-icon><component :is="option.icon" /></el-icon>
          {{ t(option.key) }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
:deep(.el-dropdown-menu__item.is-current) {
  color: var(--vs-accent);
  font-weight: 600;
}

:deep(.el-dropdown-menu__item .el-icon) {
  margin-right: 6px;
}
</style>
