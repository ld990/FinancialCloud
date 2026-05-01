<template>
  <el-card class="metric-card" shadow="never">
    <div class="metric-title">{{ title }}</div>
    <div class="metric-value">{{ value }}</div>
    <div class="metric-subtitle">{{ subtitle }}</div>
  </el-card>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  value: { type: [String, Number], required: true },
  subtitle: { type: String, default: '' }
})
</script>

<style scoped>
.metric-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}
.metric-title {
  color: #5b6470;
  font-size: 14px;
  margin-bottom: 10px;
}
.metric-value {
  font-weight: 900;
  font-size: 28px;
  color: #111111;
  margin-bottom: 8px;
}
.metric-subtitle {
  color: #5b6470;
  font-size: 13px;
}
</style>

