<script setup lang="ts">
import { ArrowDown } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { SUPPORTED_LOCALES, type AppLocale } from '@/i18n'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const { t } = useI18n()

const current = computed<AppLocale>(() => ui.locale)
const currentLabel = computed(
  () => SUPPORTED_LOCALES.find((item) => item.value === current.value)?.label ?? current.value,
)

function change(command: unknown): void {
  void ui.setLocalePreference(String(command))
}
</script>

<template>
  <el-dropdown trigger="click" @command="change">
    <el-button text :title="t('header.language')">
      {{ currentLabel }}
      <el-icon class="caret"><ArrowDown /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="item in SUPPORTED_LOCALES"
          :key="item.value"
          :command="item.value"
          :class="{ 'is-current': item.value === current }"
        >
          {{ item.label }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.caret {
  margin-left: 4px;
  font-size: 11px;
}

:deep(.el-dropdown-menu__item.is-current) {
  color: var(--vs-accent);
  font-weight: 600;
}
</style>
