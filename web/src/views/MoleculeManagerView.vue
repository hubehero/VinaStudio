<script setup lang="ts">
import MoleculeDetail from '@/components/panels/MoleculeDetail.vue'
import MoleculePanel from '@/components/panels/MoleculePanel.vue'
</script>

<template>
  <div class="mol-manager">
    <MoleculePanel class="mol-manager__panel" />
    <MoleculeDetail class="mol-manager__detail" />
  </div>
</template>

<style scoped>
.mol-manager {
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: 14px;
  padding: 14px 16px;
  height: 100%;
  min-height: 0;
}

.mol-manager__panel,
.mol-manager__detail {
  min-height: 0;
}

@media (max-width: 1100px) {
  .mol-manager {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(220px, 38%) minmax(0, 1fr);
  }
}
</style>
