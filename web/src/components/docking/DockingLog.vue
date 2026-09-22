<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { useDockingStore } from '@/stores/docking'

const { t } = useI18n()
const docking = useDockingStore()
</script>

<template>
  <div v-if="docking.logLines.length > 0 || docking.isRunning" class="vs-card">
    <div class="vs-card__header">
      <div><div class="vs-card__title">{{ t('docking.log') }}</div></div>
    </div>
    <div class="vs-card__body">
      <div class="log-box">
        <div v-for="(line, i) in docking.logLines" :key="i" class="log-line">{{ line }}</div>
        <div v-if="docking.logLines.length === 0" class="log-placeholder">{{ t('docking.logPlaceholder') }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-box {
  max-height: 200px;
  overflow: auto;
  background: var(--vs-bg-sunken);
  border-radius: var(--vs-radius);
  padding: 8px 10px;
  font-family: var(--vs-font-mono);
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--vs-text-muted);
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
}

.log-placeholder {
  font-style: italic;
  opacity: 0.6;
}
</style>
