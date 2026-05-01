<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <el-card shadow="never" class="card">
        <div class="sub-title">命名空间资源消耗（资源请求/资源限制对比）</div>
        <div class="charts-grid">
          <div ref="cpuEl" class="chart" />
          <div ref="memEl" class="chart" />
        </div>
      </el-card>

      <el-card shadow="never" class="card section-card">
        <div class="sub-title">节点实时资源（近似 kubectl top node）</div>
        <div v-if="nodeTopError" class="node-top-empty">
          {{ nodeTopError }}
        </div>
        <div v-else class="charts-grid">
          <div ref="nodeCpuEl" class="chart" />
          <div ref="nodeMemEl" class="chart" />
        </div>
      </el-card>

      <ExpertAdvice title="专家建议" :content="expertContent" />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import SideNav from '../components/SideNav.vue'
import ExpertAdvice from '../components/ExpertAdvice.vue'
import { fetchNodeTopUsage, fetchResourcesUsage } from '../api/client'

const router = useRouter()

const namespaces = ref([])
const nodeTop = ref([])
const nodeTopError = ref('')
const cpuEl = ref(null)
const memEl = ref(null)
const nodeCpuEl = ref(null)
const nodeMemEl = ref(null)
let cpuChart = null
let memChart = null
let nodeCpuChart = null
let nodeMemChart = null

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

const expertContent = computed(() => {
  const list = namespaces.value || []
  const top = list[0]
  if (nodeTopError.value) {
    return '当前未获取到节点实时资源指标。建议在集群中安装 metrics-server 后，再查看近似 kubectl top node 的节点资源视图。'
  }
  if (!top) return '建议优先核查资源配额策略，建立命名空间资源基线与告警阈值，确保金融工作负载稳定运行。'
  const maxMem = top.memory_limits_gib || 0
  return `资源分布中当前内存资源限制最高的命名空间为「${top.namespace}」（约 ${maxMem.toFixed(2)} GiB）。建议对高占用的命名空间开展容量规划与配额治理，并对超配或缺失资源限制的容器组进行整改。`
})

function initCharts() {
  if (cpuEl.value) cpuChart = echarts.init(cpuEl.value)
  if (memEl.value) memChart = echarts.init(memEl.value)
  if (nodeCpuEl.value) nodeCpuChart = echarts.init(nodeCpuEl.value)
  if (nodeMemEl.value) nodeMemChart = echarts.init(nodeMemEl.value)
}

function render() {
  const list = namespaces.value || []
  const x = list.map((n) => n.namespace)
  const cpuReq = list.map((n) => n.cpu_requests_cores)
  const cpuLim = list.map((n) => n.cpu_limits_cores)
  const memReq = list.map((n) => n.memory_requests_gib)
  const memLim = list.map((n) => n.memory_limits_gib)

  if (cpuChart) {
    cpuChart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: { textStyle: { color: '#9fa0a7' } },
      xAxis: { type: 'category', data: x, axisLabel: { color: '#9fa0a7' } },
      yAxis: { type: 'value', axisLabel: { color: '#9fa0a7' } },
      series: [
        { name: 'CPU 请求（核）', type: 'bar', data: cpuReq, itemStyle: { color: '#3b82f6' } },
        { name: 'CPU 限制（核）', type: 'bar', data: cpuLim, itemStyle: { color: '#2ecc71' } }
      ],
      grid: { left: 40, right: 20, top: 20, bottom: 40 }
    })
  }

  if (memChart) {
    memChart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: { textStyle: { color: '#9fa0a7' } },
      xAxis: { type: 'category', data: x, axisLabel: { color: '#9fa0a7' } },
      yAxis: { type: 'value', axisLabel: { color: '#9fa0a7' } },
      series: [
        { name: '内存请求（GiB）', type: 'bar', data: memReq, itemStyle: { color: '#3b82f6' } },
        { name: '内存限制（GiB）', type: 'bar', data: memLim, itemStyle: { color: '#2ecc71' } }
      ],
      grid: { left: 40, right: 20, top: 20, bottom: 40 }
    })
  }

  const nodeList = nodeTop.value || []
  const nx = nodeList.map((n) => n.node)
  const cpuUsage = nodeList.map((n) => Number(n.cpu_usage_ratio || 0).toFixed(2))
  const memUsage = nodeList.map((n) => Number(n.memory_usage_ratio || 0).toFixed(2))

  if (nodeCpuChart && !nodeTopError.value) {
    nodeCpuChart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', formatter: '{b}<br/>CPU 使用率: {c}%' },
      xAxis: { type: 'category', data: nx, axisLabel: { color: '#9fa0a7', rotate: 20 } },
      yAxis: { type: 'value', max: 100, axisLabel: { color: '#9fa0a7', formatter: '{value}%' } },
      series: [
        { name: 'CPU 使用率', type: 'bar', data: cpuUsage, itemStyle: { color: '#2563eb' } }
      ],
      grid: { left: 45, right: 20, top: 20, bottom: 50 }
    })
  }

  if (nodeMemChart && !nodeTopError.value) {
    nodeMemChart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', formatter: '{b}<br/>内存使用率: {c}%' },
      xAxis: { type: 'category', data: nx, axisLabel: { color: '#9fa0a7', rotate: 20 } },
      yAxis: { type: 'value', max: 100, axisLabel: { color: '#9fa0a7', formatter: '{value}%' } },
      series: [
        { name: '内存使用率', type: 'bar', data: memUsage, itemStyle: { color: '#7c3aed' } }
      ],
      grid: { left: 45, right: 20, top: 20, bottom: 50 }
    })
  }
}

onMounted(async () => {
  initCharts()
  const [resp, nodeResp] = await Promise.all([
    fetchResourcesUsage(),
    fetchNodeTopUsage().catch((e) => ({ nodes: [], error: e?.message || '获取失败' }))
  ])
  namespaces.value = resp.namespaces || []
  nodeTop.value = nodeResp?.nodes || []
  nodeTopError.value = nodeResp?.error || ''
  render()
  window.addEventListener('resize', render)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', render)
  cpuChart?.dispose()
  memChart?.dispose()
  nodeCpuChart?.dispose()
  nodeMemChart?.dispose()
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
.section-card {
  margin-top: 14px;
}
.sub-title {
  color: #374151;
  font-weight: 900;
  margin-bottom: 12px;
}
.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.chart {
  height: 360px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
}
.node-top-empty {
  color: #6b7280;
  font-weight: 800;
  padding: 20px 8px 8px;
}
@media (max-width: 1100px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
  .chart {
    height: 320px;
  }
}
</style>

