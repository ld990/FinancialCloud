<template>
  <span :class="['badge', variant]">{{ text }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  text: { type: String, required: true },
  variant: { type: String, default: 'risk' } // 'ok' | 'risk'
})
</script>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 900;
  font-size: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  white-space: nowrap;
}
.ok {
  background: rgba(31, 157, 85, 0.18);
  color: #5ef2a0;
  border-color: rgba(31, 157, 85, 0.35);
}
.risk {
  background: rgba(192, 57, 43, 0.20);
  color: #ff8a80;
  border-color: rgba(192, 57, 43, 0.40);
}
</style>

