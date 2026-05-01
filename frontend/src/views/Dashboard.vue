<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>
    <el-main class="main">

      <div class="cards">
        <MetricCard title="总容器组" :value="overview.total_pod_count" subtitle="跨命名空间汇总" />
        <MetricCard title="合规容器组" :value="overview.compliant_pod_count" subtitle="已配置 CPU/MEM 资源限制" />
        <MetricCard title="风险容器组" :value="overview.risk_pod_count" subtitle="存在未配置资源限制" />
        <MetricCard title="合规率" :value="overview.compliance_ratio.toFixed(2) + '%'" subtitle="全量计算结果" />
      </div>

      <el-card shadow="never" class="card section-card">
        <div class="section-title">核心组件运行状态</div>
        <div class="status-updated">最近更新时间：{{ componentsUpdatedAt || '-' }}</div>
        <div class="component-grid">
          <div
            v-for="item in componentStatus"
            :key="item.name"
            class="component-item"
            :class="[cardClass(item.status_level), nameClass(item.name)]"
          >
            <div class="component-name">{{ item.name }}</div>
            <div class="component-state">
              <span class="status-dot" :class="dotClass(item.status_level)" />
              <span class="status-text">{{ item.status_text || '未知' }}</span>
            </div>
            <div class="component-meta" :class="metaClass(item)">
              <template v-if="Number(item.total_count || 0) === 0">未检测到实例</template>
              <template v-else>可用实例 {{ item.ready_count || 0 }} / {{ item.total_count || 0 }}</template>
            </div>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="card section-card">
        <div class="section-title">最近 5 条高危安全预警</div>
        <el-table :data="topAlerts" border style="width: 100%">
          <el-table-column prop="timestamp" label="时间" width="190" />
          <el-table-column prop="severity" label="等级" width="100" />
          <el-table-column prop="title" label="告警要点" />
          <el-table-column prop="namespace" label="命名空间" width="150" />
          <el-table-column prop="pod_name" label="容器组" />
          <el-table-column prop="reason" label="原因" />
        </el-table>
      </el-card>

      <ExpertAdvice title="专家建议" :content="expertContent" />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import MetricCard from '../components/MetricCard.vue'
import ExpertAdvice from '../components/ExpertAdvice.vue'
import { fetchOverview, fetchOverviewComponents, fetchTopAlerts } from '../api/client'

const router = useRouter()
const topAlerts = ref([])
const componentStatus = ref([])
const componentsUpdatedAt = ref('')
const overview = ref({
  total_pod_count: 0,
  compliant_pod_count: 0,
  risk_pod_count: 0,
  compliance_ratio: 0
})

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

onMounted(async () => {
  const [ov, alertResp, compResp] = await Promise.all([
    fetchOverview(),
    fetchTopAlerts(5),
    fetchOverviewComponents().catch(() => ({ components: [], updated_at: '' }))
  ])
  overview.value = ov || overview.value
  topAlerts.value = alertResp?.alerts || []
  componentStatus.value = compResp?.components || []
  componentsUpdatedAt.value = compResp?.updated_at || ''
})

function dotClass(level) {
  const lv = String(level || '').toLowerCase()
  if (lv === 'healthy') return 'dot-green'
  if (lv === 'degraded') return 'dot-yellow'
  if (lv === 'down') return 'dot-red'
  return 'dot-gray'
}

function metaClass(item) {
  const total = Number(item?.total_count || 0)
  if (total === 0) return 'meta-unknown'
  const ready = Number(item?.ready_count || 0)
  return ready === total ? 'meta-ok' : 'meta-risk'
}

function cardClass(level) {
  const lv = String(level || '').toLowerCase()
  if (lv === 'healthy') return 'card-healthy'
  if (lv === 'degraded') return 'card-degraded'
  if (lv === 'down') return 'card-down'
  return 'card-unknown'
}

function nameClass(name) {
  const n = String(name || '').toLowerCase()
  if (n === 'etcd') return 'name-etcd'
  if (n === 'kube-apiserver') return 'name-apiserver'
  if (n === 'controller-manager') return 'name-controller'
  if (n === 'scheduler') return 'name-scheduler'
  if (n === 'kube-proxy') return 'name-proxy'
  if (n === 'kubelet') return 'name-kubelet'
  return 'name-default'
}

const expertContent = computed(() => {
  const ratio = Number(overview.value?.compliance_ratio || 0)
  if (ratio < 70) {
    return `当前合规率 ${ratio.toFixed(2)}%，建议优先处置未设置资源限制与高危策略配置，避免对核心业务造成影响。`
  }
  return `当前合规率 ${ratio.toFixed(2)}%，建议持续保持巡检频率，并结合事件日志验证治理效果。`
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
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}
.section-card {
  margin-bottom: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
}
.section-title {
  font-size: 16px;
  font-weight: 900;
  color: #111827;
  margin-bottom: 10px;
}
.status-updated {
  margin-top: -4px;
  margin-bottom: 10px;
  color: #6b7280;
  font-size: 12px;
}
.component-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
}
.component-item {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 12px;
  background: #f9fafb;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}
.component-item:hover {
  border-color: #cbd5e1;
  background: #ffffff;
}
.card-healthy { box-shadow: inset 0 0 0 1px rgba(16, 185, 129, 0.26); }
.card-degraded { box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.28); }
.card-down { box-shadow: inset 0 0 0 1px rgba(239, 68, 68, 0.28); }
.card-unknown { box-shadow: inset 0 0 0 1px rgba(107, 114, 128, 0.20); }
.name-etcd {
  background: #eff6ff;
}
.name-apiserver {
  background: #eef2ff;
}
.name-controller {
  background: #f5f3ff;
}
.name-scheduler {
  background: #fff7ed;
}
.name-proxy {
  background: #ecfeff;
}
.name-kubelet {
  background: #ecfdf5;
}
.name-default {
  background: #f9fafb;
}
.component-name {
  color: #111827;
  font-size: 13px;
  font-weight: 900;
}
.component-state {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.status-text {
  color: #1f2937;
  font-weight: 800;
  font-size: 13px;
}
.component-meta {
  margin-top: 6px;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
}
.meta-ok {
  color: #047857;
}
.meta-risk {
  color: #b45309;
}
.meta-unknown {
  color: #6b7280;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot-green {
  background: #10b981;
}
.dot-yellow {
  background: #f59e0b;
}
.dot-red {
  background: #ef4444;
}
.dot-gray {
  background: #9ca3af;
}
</style>

