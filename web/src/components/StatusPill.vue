<script setup lang="ts">
import { computed } from 'vue'

/** Small state pill used for service / channel / capability indicators. */
const props = withDefaults(
  defineProps<{
    /** Visual state driving colour. */
    state?: 'ok' | 'warn' | 'error' | 'idle'
    label: string
    /** Optional right-aligned detail, e.g. a version or duration. */
    detail?: string
    pulse?: boolean
  }>(),
  { state: 'idle', detail: undefined, pulse: false },
)

const stateClass = computed(() => `is-${props.state}`)
</script>

<template>
  <span class="pill" :class="stateClass">
    <span class="pill__dot" :class="{ 'is-pulsing': pulse }" />
    <span class="pill__label">{{ label }}</span>
    <span v-if="detail" class="pill__detail">{{ detail }}</span>
  </span>
</template>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px 3px 8px;
  border: 1px solid var(--vs-border);
  border-radius: 999px;
  background: var(--vs-bg-sunken);
  font-size: 12px;
  line-height: 1.5;
  color: var(--vs-text-muted);
  white-space: nowrap;
}

.pill__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--vs-text-faint);
  flex: none;
}

.pill.is-ok .pill__dot {
  background: var(--vs-success);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--vs-success) 18%, transparent);
}

.pill.is-warn .pill__dot {
  background: var(--vs-warning);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--vs-warning) 18%, transparent);
}

.pill.is-error .pill__dot {
  background: var(--vs-danger);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--vs-danger) 18%, transparent);
}

.pill.is-pulsing .pill__dot {
  animation: pill-pulse 1.6s ease-in-out infinite;
}

.pill__label {
  color: var(--vs-text);
}

.pill__detail {
  color: var(--vs-text-faint);
  font-variant-numeric: tabular-nums;
}

@keyframes pill-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
</style>
