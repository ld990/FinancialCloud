<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <el-card shadow="never" class="card">
        <div class="toolbar">
          <el-button type="primary" :loading="loading" @click="loadPreview">刷新预览</el-button>
          <el-button :disabled="!html" @click="printAsPdf">打印导出 PDF</el-button>
          <el-button type="success" :loading="loadingCsv" @click="exportCsv">导出 CSV</el-button>
        </div>

        <iframe class="preview" v-if="html" :srcdoc="html" />
        <div v-else class="empty">正在加载周报预览...</div>
      </el-card>

      <ExpertAdvice title="专家建议" :content="expertContent" />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import ExpertAdvice from '../components/ExpertAdvice.vue'
import { fetchWeeklyReportPreview, fetchWeeklyReportCsv } from '../api/client'
import { ElMessage } from 'element-plus'

const router = useRouter()
const loading = ref(false)
const loadingCsv = ref(false)
const html = ref('')

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

async function loadPreview() {
  loading.value = true
  try {
    const resp = await fetchWeeklyReportPreview()
    html.value = resp.html || ''
  } finally {
    loading.value = false
  }
}

function printAsPdf() {
  if (!html.value) return
  const w = window.open('', '_blank')
  if (!w) return
  w.document.open()
  w.document.write(html.value)
  w.document.close()
  w.focus()
  setTimeout(() => w.print(), 300)
}

async function exportCsv() {
  loadingCsv.value = true
  try {
    const resp = await fetchWeeklyReportCsv()
    const csvText = resp?.csv || ''
    if (!csvText) {
      ElMessage.warning('当前暂无可导出的 CSV 数据')
      return
    }

    // Prepend UTF-8 BOM so Excel opens Chinese text correctly.
    const blob = new Blob(['\ufeff', csvText], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `weekly_report_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('CSV 已导出')
  } catch (e) {
    ElMessage.error('导出 CSV 失败，请检查后端权限/连通性')
  } finally {
    loadingCsv.value = false
  }
}

onMounted(() => {
  loadPreview()
})

const expertContent = computed(() => {
  if (!html.value) return '建议确保周报生成所依赖的集群权限齐全，并在导出前检查告警事件与风险容器组数据一致性。'
  return '建议将周报与整改工单联动：对“特权/主机路径/资源限制缺失/镜像来源风险”进行分级处置，并在下一周期复盘事件告警的收敛情况，形成闭环。'
})
</script>

<style scoped>
.layout {
  min-height: 100vh;
  height: 100vh;
  background: #f5f7fb;
}
.main {
  padding: 18px 22px;
  height: 100%;
  overflow-y: auto;
}
.card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.preview {
  background: #ffffff;
  color: #111;
  border-radius: 8px;
  width: 100%;
  height: 640px;
  border: none;
}
.empty {
  color: #6b7280;
  font-weight: 900;
  padding: 18px 0;
  text-align: center;
}
</style>

