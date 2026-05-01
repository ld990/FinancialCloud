<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">
      <el-card shadow="never" class="ext-links-card">
        <div class="ext-head">
          <div class="ext-title-group">
            <div class="ext-title">扩展连接</div>
            <div class="ext-sub">快速跳转到外部观测系统</div>
          </div>
        </div>
        <div class="ext-grid">
          <div
            v-for="item in externalLinks"
            :key="item.key"
            class="ext-item"
            @click="openLink(item)"
          >
            <div class="ext-icon">{{ item.icon }}</div>
            <div class="ext-content">
              <div class="ext-name">{{ item.name }}</div>
              <div class="ext-url">{{ item.url || '点击配置地址' }}</div>
            </div>
            <div class="ext-arrow">↗</div>
          </div>
        </div>
      </el-card>

      <div class="cards">
        <el-card shadow="never" class="metric-card">
          <div class="metric-label">总容器组</div>
          <div class="metric-value">{{ metrics.total }}</div>
        </el-card>
        <el-card shadow="never" class="metric-card">
          <div class="metric-label">合规容器组</div>
          <div class="metric-value">{{ metrics.compliant }}</div>
        </el-card>
        <el-card shadow="never" class="metric-card">
          <div class="metric-label">风险容器组</div>
          <div class="metric-value">{{ metrics.risk }}</div>
        </el-card>
        <el-card shadow="never" class="metric-card">
          <div class="metric-label">合规率</div>
          <div class="metric-value">{{ metrics.ratio }}%</div>
        </el-card>
      </div>

      <div class="charts-grid">
        <el-card shadow="never" class="chart-card">
          <template #header>命名空间 CPU 请求/限制</template>
          <div ref="cpuBarEl" class="chart" />
        </el-card>

        <el-card shadow="never" class="chart-card">
          <template #header>命名空间内存占比（前六）</template>
          <div ref="memPieEl" class="chart" />
        </el-card>

        <el-card shadow="never" class="chart-card">
          <template #header>资源限制缺口（前八）</template>
          <div ref="gapLineEl" class="chart" />
        </el-card>

        <el-card shadow="never" class="chart-card">
          <template #header>最近告警等级分布</template>
          <div ref="alertDonutEl" class="chart" />
        </el-card>
      </div>
    </el-main>
  </el-container>

  <el-dialog v-model="dialogVisible" :title="'配置 ' + currentItem?.name + ' 地址'" width="500px">
    <el-form :model="urlForm" label-width="80px">
      <el-form-item label="地址">
        <el-input v-model="urlForm.url" :placeholder="'例如：http://192.168.3.254:' + currentItem?.defaultPort" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="saveAndOpen">保存并跳转</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import SideNav from '../components/SideNav.vue'
import { ElMessage } from 'element-plus'
import { fetchOverview, fetchResourcesUsage, fetchTopAlerts } from '../api/client'

const router = useRouter()
const metrics = ref({
  total: 0,
  compliant: 0,
  risk: 0,
  ratio: '0.00'
})

const cpuBarEl = ref(null)
const memPieEl = ref(null)
const gapLineEl = ref(null)
const alertDonutEl = ref(null)

let cpuBarChart = null
let memPieChart = null
let gapLineChart = null
let alertDonutChart = null

const dialogVisible = ref(false)
const currentItem = ref(null)
const urlForm = ref({ url: '' })

const externalLinks = ref([
  { key: 'kiali', name: 'Kiali', icon: '🕸️', defaultPort: '31523' },
  { key: 'grafana', name: 'Grafana', icon: '📈', defaultPort: '31765' },
  { key: 'prometheus', name: 'Prometheus', icon: '🔥', defaultPort: '32558' },
  { key: 'alertmanager', name: 'Alertmanager', icon: '🚨', defaultPort: '' }
])

function loadSavedUrls() {
  try {
    const saved = localStorage.getItem('external_links_config')
    if (saved) {
      const urls = JSON.parse(saved)
      externalLinks.value.forEach(item => {
        if (urls[item.key]) {
          item.url = urls[item.key]
        }
      })
    }
  } catch (e) {
    console.error('加载链接配置失败:', e)
  }
}

function openLink(item) {
  currentItem.value = item
  if (item.url) {
    window.open(item.url, '_blank', 'noopener')
  } else {
    urlForm.value = { url: '' }
    dialogVisible.value = true
  }
}

function saveAndOpen() {
  if (!urlForm.value.url.trim()) {
    ElMessage.warning('请输入地址')
    return
  }
  
  let url = urlForm.value.url.trim()
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    url = 'http://' + url
  }
  
  try {
    const saved = localStorage.getItem('external_links_config')
    const urls = saved ? JSON.parse(saved) : {}
    urls[currentItem.value.key] = url
    localStorage.setItem('external_links_config', JSON.stringify(urls))
    
    currentItem.value.url = url
    ElMessage.success('地址已保存')
    dialogVisible.value = false
    window.open(url, '_blank', 'noopener')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

function toNumber(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function toNamespaceLabel(name) {
  const raw = String(name || '-')
  if (raw === 'default') return '默认（default）'
  if (raw === 'kube-system') return '系统（kube-system）'
  if (raw === 'kube-public') return '公共（kube-public）'
  if (raw === 'kube-node-lease') return '节点租约（kube-node-lease）'
  return raw
}

function buildCharts(namespaces = [], alerts = []) {
  const top = [...namespaces]
    .sort((a, b) => toNumber(b.memory_limits_gib) - toNumber(a.memory_limits_gib))
    .slice(0, 8)

  const x = top.map((n) => toNamespaceLabel(n.namespace))
  const cpuReq = top.map((n) => toNumber(n.cpu_requests_cores))
  const cpuLim = top.map((n) => toNumber(n.cpu_limits_cores))
  const memLim = top.map((n) => toNumber(n.memory_limits_gib))
  const memReq = top.map((n) => toNumber(n.memory_requests_gib))
  const memPieTop = [...top].slice(0, 6)

  const levelCount = { critical: 0, high: 0, medium: 0, low: 0 }
  for (const a of alerts || []) {
    const s = String(a?.severity || '').toLowerCase()
    if (s.includes('critical')) levelCount.critical += 1
    else if (s.includes('high')) levelCount.high += 1
    else if (s.includes('medium')) levelCount.medium += 1
    else levelCount.low += 1
  }

  cpuBarChart?.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 42, right: 18, top: 40, bottom: 36 },
    xAxis: { type: 'category', data: x, axisLabel: { rotate: 25 } },
    yAxis: { type: 'value' },
    series: [
      { name: 'CPU 请求', type: 'bar', data: cpuReq, itemStyle: { color: '#3b82f6' } },
      { name: 'CPU 限制', type: 'bar', data: cpuLim, itemStyle: { color: '#22c55e' } }
    ]
  })

  memPieChart?.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        name: '内存占比',
        type: 'pie',
        radius: ['38%', '66%'],
        data: memPieTop.map((n) => ({
          name: toNamespaceLabel(n.namespace),
          value: toNumber(n.memory_limits_gib)
        })),
        label: { formatter: '{b}\n{d}%' }
      }
    ]
  })

  gapLineChart?.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 42, right: 18, top: 40, bottom: 36 },
    xAxis: { type: 'category', data: x, axisLabel: { rotate: 25 } },
    yAxis: { type: 'value' },
    series: [
      { name: '内存请求', type: 'line', smooth: true, data: memReq, itemStyle: { color: '#0ea5e9' } },
      { name: '内存限制', type: 'line', smooth: true, data: memLim, itemStyle: { color: '#8b5cf6' } }
    ]
  })

  alertDonutChart?.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        name: '告警等级',
        type: 'pie',
        radius: ['40%', '72%'],
        data: [
          { name: '严重', value: levelCount.critical },
          { name: '高危', value: levelCount.high },
          { name: '中危', value: levelCount.medium },
          { name: '低危', value: levelCount.low }
        ]
      }
    ]
  })
}

function onResize() {
  cpuBarChart?.resize()
  memPieChart?.resize()
  gapLineChart?.resize()
  alertDonutChart?.resize()
}

onMounted(async () => {
  cpuBarChart = cpuBarEl.value ? echarts.init(cpuBarEl.value) : null
  memPieChart = memPieEl.value ? echarts.init(memPieEl.value) : null
  gapLineChart = gapLineEl.value ? echarts.init(gapLineEl.value) : null
  alertDonutChart = alertDonutEl.value ? echarts.init(alertDonutEl.value) : null

  const [ov, usage, alertResp] = await Promise.all([
    fetchOverview().catch(() => ({})),
    fetchResourcesUsage().catch(() => ({})),
    fetchTopAlerts(50).catch(() => ({ alerts: [] }))
  ])

  metrics.value = {
    total: toNumber(ov?.total_pod_count || ov?.totalPods),
    compliant: toNumber(ov?.compliant_pod_count || ov?.normalPods),
    risk: toNumber(ov?.risk_pod_count || ov?.riskPods),
    ratio: toNumber(ov?.compliance_ratio || ov?.score).toFixed(2)
  }

  loadSavedUrls()

  buildCharts(usage?.namespaces || usage?.items || [], alertResp?.alerts || [])
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  cpuBarChart?.dispose()
  memPieChart?.dispose()
  gapLineChart?.dispose()
  alertDonutChart?.dispose()
})
</script>

<style scoped>
.layout {
  min-height: 100vh;
  height: 100vh;
}
.main {
  padding: 18px 22px;
  height: 100%;
  overflow-y: auto;
}
.ext-links-card {
  border: 1px solid #e5e7eb;
  margin-bottom: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
}
.ext-head {
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
}
.ext-title-group {
  flex: 1;
}
.ext-title {
  font-size: 16px;
  font-weight: 900;
  color: #111827;
}
.ext-sub {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
}
.ext-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.ext-item {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  border: 1px solid #dbe4f2;
  border-radius: 10px;
  background: #ffffff;
  padding: 10px 12px;
  transition: all 0.18s ease;
  cursor: pointer;
}
.ext-item:hover {
  transform: translateY(-1px);
  border-color: #93c5fd;
  box-shadow: 0 8px 18px rgba(59, 130, 246, 0.12);
}
.ext-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #eff6ff;
  font-size: 16px;
}
.ext-content {
  flex: 1;
  min-width: 0;
}
.ext-name {
  color: #111827;
  font-weight: 800;
  font-size: 13px;
}
.ext-url {
  margin-top: 2px;
  color: #6b7280;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ext-arrow {
  color: #9ca3af;
  font-weight: 900;
}
.cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.metric-card {
  border: 1px solid #e5e7eb;
}
.metric-label {
  color: #6b7280;
  font-size: 13px;
}
.metric-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 800;
}
.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.chart-card {
  border: 1px solid #e5e7eb;
}
.chart {
  height: 320px;
}
@media (max-width: 1100px) {
  .ext-grid {
    grid-template-columns: 1fr 1fr;
  }
  .cards {
    grid-template-columns: 1fr 1fr;
  }
  .charts-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 680px) {
  .ext-grid {
    grid-template-columns: 1fr;
  }
}
</style>
