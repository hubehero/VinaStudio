<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import BoxPanel from '@/components/panels/BoxPanel.vue'
import StylePanel from '@/components/panels/StylePanel.vue'
import ViewportCanvas from '@/components/viewer/ViewportCanvas.vue'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'

/**
 * Define and inspect the search box.
 *
 * The molecules come from the Molecule Manager: the stores are shared, so this
 * view shows the prepared receptor and ligand without loading anything itself.
 */
const box = useBoxStore()
const molecules = useMoleculeStore()
const { t } = useI18n()

const receptorUrl = computed(() => molecules.receptorPdbUrl)
const ligandUrl = computed(() => molecules.ligandSdfUrl)
const hasReceptor = computed(() => molecules.hasReceptor)

function onBoxMoved(center: [number, number, number]): void {
  box.setCenter(center)
}
</script>

<template>
  <div class="box-view">
    <section class="box-view__panels">
      <el-alert
        v-if="!hasReceptor"
        type="info"
        :closable="false"
        show-icon
        :title="t('box.needReceptor')"
      />
      <StylePanel />
      <BoxPanel />
    </section>

    <section class="box-view__stage">
      <div class="stage-header">
        <div>
          <div class="stage-header__title">{{ t('box.stageTitle') }}</div>
          <div class="stage-header__subtitle">{{ t('box.stageSubtitle') }}</div>
        </div>
      </div>
      <div class="box-view__viewport">
        <ViewportCanvas
          :receptor-url="receptorUrl"
          :ligand-url="ligandUrl"
          :box="box.geometry"
          :style="box.style"
          :orthographic="box.orthographic"
          :box-draggable="hasReceptor"
          @box-moved="onBoxMoved"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.box-view {
  display: grid;
  grid-template-columns: 400px minmax(0, 1fr);
  gap: 16px;
  padding: 16px 18px;
  height: 100%;
  min-height: 0;
}

.box-view__panels {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.box-view__stage {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
}

.stage-header__title {
  font-size: 13.5px;
  font-weight: 600;
}

.stage-header__subtitle {
  font-size: 12px;
  color: var(--vs-text-faint);
}

.box-view__viewport {
  flex: 1;
  min-height: 0;
}

@media (max-width: 1180px) {
  .box-view {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(280px, 1fr);
  }
}
</style>
