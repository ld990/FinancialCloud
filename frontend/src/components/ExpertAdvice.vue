<template>
  <el-alert
    class="advice"
    :title="title"
    type="info"
    show-icon
    :closable="false"
  >
    <div class="content">{{ content }}</div>
  </el-alert>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  content: { type: String, required: true }
})
</script>

<style scoped>
.advice {
  border-radius: 8px;
  margin-top: 16px;
}
.content {
  color: #4b5563;
  line-height: 1.6;
  font-weight: 600;
}
</style>

