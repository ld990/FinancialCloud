<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <div class="filters">
        <el-input v-model="keyword" placeholder="搜索命名空间..." style="width: 240px" clearable />
        <el-select v-model="statusFilter" placeholder="合规状态" style="width: 200px" clearable>
          <el-option label="全部" value="" />
          <el-option label="✅ 合规" value="✅ 合规" />
          <el-option label="❌ 风险" value="❌ 风险" />
        </el-select>
        <el-button :loading="loading" type="primary" @click="refresh">刷新</el-button>
      </div>

      <el-card shadow="never" class="finance-audit-card">
        <div class="finance-title">金融合规留痕要点</div>
        <div class="finance-desc">
          当前共检测到 <b>{{ riskCount }}</b> 个高风险容器组。建议以“控制-证据-回溯”的方式形成整改记录，便于后续审计复核。
        </div>
        <div class="finance-tags">
          <el-tag v-if="riskCount > 0" type="warning">资源限制差异证据</el-tag>
          <el-tag>修复建议与变更工单联动</el-tag>
          <el-tag>事件告警回溯（审计可追溯性）</el-tag>
        </div>
      </el-card>

      <el-table
        class="audit-table"
        :data="filteredRows"
        :row-key="rowKey"
        border
        style="width: 100%"
      >
        <el-table-column type="expand">
          <template #default="props">
            <div class="expand">
              <div class="expand-shell">
                <div class="expand-head">
                  <div class="expand-title">明细信息</div>
                  <div class="expand-sub">包含容器资源、违规证据与修复建议</div>
                </div>

              <div class="expand-block">
                <div class="sub-title">容器资源限制与镜像</div>
                <el-table :data="props.row.containers" border size="small">
                <el-table-column prop="name" label="容器" width="140" />
                <el-table-column prop="image" label="镜像" />
                <el-table-column label="资源限制是否完整" width="170">
                  <template #default="scope">
                    <span v-if="scope.row.has_limits" class="badge ok">✅ 合规</span>
                    <span v-else class="badge risk">❌ 风险</span>
                  </template>
                </el-table-column>
                </el-table>
              </div>

              <div class="expand-block">
                <div class="sub-title">违规详情（规则 + 证据）</div>
                <div v-if="props.row.violations?.length" class="violation-wrap">
                <div v-for="(v, idx) in props.row.violations" :key="`${v.rule}-${idx}`" class="violation-item">
                  <div class="violation-head">
                    <el-tag size="small" :type="tagType(v.level)" effect="light">{{ v.rule }}</el-tag>
                    <span class="violation-target">{{ v.scope === 'container' ? '容器' : '容器组' }}：{{ v.target || '-' }}</span>
                  </div>
                  <div class="violation-evidence">{{ formatEvidence(v.evidence) }}</div>
                </div>
                </div>
                <div v-else class="no-yaml">未发现违规详情。</div>
              </div>

              <div class="expand-block">
                <div class="sub-title">修复建议 YAML（示例）</div>
                <div v-if="props.row.repair_suggestions_yamls?.length" class="yaml-wrap">
                <div
                  v-for="(y, idx) in props.row.repair_suggestions_yamls"
                  :key="idx"
                  class="yaml-block"
                >
                  <div class="yaml-label">YAML {{ idx + 1 }}</div>
                  <pre class="yaml"><code>{{ y }}</code></pre>
                </div>
                </div>
                <div v-else class="no-yaml">当前无修复建议（可能未发现需要修复的资源限制）。</div>
              </div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="namespace" label="命名空间" width="170" />
        <el-table-column prop="pod_name" label="容器组名称" />
        <el-table-column prop="phase" label="运行阶段" width="120" />
        <el-table-column label="合规状态" width="170">
          <template #default="scope">
            <span v-if="scope.row.overall_status === '✅ 合规'" class="badge ok">✅ 合规</span>
            <span v-else class="badge risk">❌ 风险</span>
          </template>
        </el-table-column>
        <el-table-column label="风险容器数量" width="160">
          <template #default="scope">
            <span class="subtle">
              {{
                (scope.row.containers || []).filter((c) => !c.has_limits).length
              }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="违规条目" width="120">
          <template #default="scope">
            <span class="subtle">{{ (scope.row.violations || []).length }}</span>
          </template>
        </el-table-column>
      </el-table>
      <ExpertAdvice title="专家建议" :content="expertContent" />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onActivated, onDeactivated, ref } from 'vue'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import { fetchAudit } from '../api/client'
import ExpertAdvice from '../components/ExpertAdvice.vue'

const router = useRouter()
const keyword = ref('')
const statusFilter = ref('')
const loading = ref(false)
const rows = ref([])

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

function tagType(level) {
  const lv = String(level || '').toLowerCase()
  if (lv === 'critical') return 'danger'
  if (lv === 'high') return 'warning'
  return 'info'
}

function formatEvidence(evidence) {
  if (!evidence || typeof evidence !== 'object') return '-'
  const parts = []
  for (const [k, v] of Object.entries(evidence)) {
    if (Array.isArray(v)) {
      parts.push(`${k}: ${v.filter(Boolean).join(', ') || '-'}`)
    } else {
      parts.push(`${k}: ${v ?? '-'}`)
    }
  }
  return parts.join(' | ')
}

function rowKey(row) {
  return `${row?.namespace || ''}/${row?.pod_name || ''}`
}

const filteredRows = computed(() => {
  const k = keyword.value.trim()
  return (rows.value || []).filter((r) => {
    const nsOk = !k || (r.namespace || '').includes(k)
    const stOk = !statusFilter.value || r.overall_status === statusFilter.value
    return nsOk && stOk
  })
})

const riskCount = computed(() => {
  const list = rows.value || []
  return list.filter((r) => r.overall_status === '❌ 风险').length
})

const expertContent = computed(() => {
  const list = rows.value || []
  const risk = list.filter((r) => r.overall_status === '❌ 风险').length
  if (risk === 0) {
    return '资源限制合规状态良好。建议继续保持资源限制配置标准化（例如基线模板/准入策略），并在每次版本发布前进行差异审计，确保资产长期处于安全基线。'
  }
  return `审计结果显示当前存在 ${risk} 个 ❌ 风险容器组（未完整设置 CPU/MEM 资源限制）。建议优先生成修复 YAML 并纳入变更审批流程，同时结合回滚预案，避免整改影响金融关键业务链路。`
})

async function refresh() {
  loading.value = true
  try {
    rows.value = await fetchAudit()
  } finally {
    loading.value = false
  }
}

let timer = null
onActivated(() => {
  refresh()
  if (timer) clearInterval(timer)
  timer = setInterval(refresh, 120000)
})

onDeactivated(() => {
  if (timer) clearInterval(timer)
  timer = null
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
.filters {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.finance-audit-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 14px;
}
.finance-title {
  color: #1f2937;
  font-weight: 900;
  font-size: 16px;
  margin-bottom: 8px;
}
.finance-desc {
  color: #6b7280;
  font-weight: 800;
  line-height: 1.7;
  margin-bottom: 10px;
}
.finance-tags {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.audit-table :deep(.el-table) {
  background: transparent;
}
.subtle {
  color: #6b7280;
  font-weight: 800;
}
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 900;
  font-size: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
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
.expand {
  padding: 12px 6px;
}
.expand-shell {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  padding: 12px 12px;
}
.expand-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px dashed #e5e7eb;
  margin-bottom: 12px;
}
.expand-title {
  color: #111827;
  font-weight: 900;
  font-size: 14px;
}
.expand-sub {
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
}
.expand-block {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #ffffff;
  padding: 10px 10px;
  margin-bottom: 10px;
}
.expand-block:last-child {
  margin-bottom: 0;
}
.sub-title {
  color: #374151;
  font-weight: 900;
  margin: 6px 0;
}
.yaml-wrap {
  margin-top: 8px;
}
.violation-wrap {
  margin-top: 8px;
}
.violation-item {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.violation-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.violation-target {
  color: #374151;
  font-weight: 700;
  font-size: 12px;
}
.violation-evidence {
  color: #4b5563;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}
.yaml-block {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
  margin: 10px 0;
  overflow: hidden;
}
.yaml-label {
  padding: 10px 12px;
  color: #6b7280;
  font-weight: 900;
  border-bottom: 1px solid #e5e7eb;
}
.yaml {
  margin: 0;
  padding: 12px;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  color: #111827;
  font-size: 12px;
}
.no-yaml {
  color: #6b7280;
  padding: 10px 0;
}
</style>

