<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const props = defineProps<{ topic: string; label?: string }>()
const router = useRouter()
const { t } = useI18n()

function open(): void {
  void router.push({ name: 'help', query: { topic: props.topic } })
}
</script>

<template>
  <el-button text size="small" type="primary" @click="open">
    {{ label ?? t('help.jump') }}
  </el-button>
</template>
