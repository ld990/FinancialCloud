<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <el-card shadow="never" class="card">
        <el-tabs v-model="activeTab" class="tabs">
          <el-tab-pane label="镜像来源" name="source">
            <div class="filters">
              <el-input v-model="keyword" placeholder="搜索镜像/容器组/命名空间..." style="width: 340px" clearable />
              <el-checkbox v-model="onlyInsecure">仅显示不安全公有仓库镜像</el-checkbox>
              <el-button type="primary" :loading="loadingSource" @click="refreshSource">刷新</el-button>
            </div>

            <el-table :data="filteredRows" border style="width: 100%; margin-top: 12px;">
              <el-table-column prop="namespace" label="命名空间" width="160" />
              <el-table-column prop="pod_name" label="容器组" />
              <el-table-column prop="container_name" label="容器" width="160" />
              <el-table-column prop="image" label="镜像" min-width="260">
                <template #default="scope">
                  <div class="mono">{{ scope.row.image }}</div>
                </template>
              </el-table-column>
              <el-table-column prop="image_registry" label="镜像仓库" width="200" />
              <el-table-column label="来源合规" width="160">
                <template #default="scope">
                  <span v-if="scope.row.image_insecure" class="badge risk">❌ 风险</span>
                  <span v-else class="badge ok">✅ 合规</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="残留镜像" name="unused">
            <div class="unused-head">
              <div class="unused-title">残留/无用镜像识别</div>
              <div class="unused-sub">规则：节点镜像列表存在，但当前运行 Pod 未使用</div>
            </div>

            <div class="filters">
              <el-input v-model="unusedKeyword" placeholder="搜索镜像/节点..." style="width: 340px" clearable />
              <el-button :loading="loadingUnused" type="primary" @click="refreshUnused">刷新扫描</el-button>
              <el-button :disabled="!filteredUnused.length" @click="exportUnusedCsv">导出 CSV</el-button>
              <span class="meta">最近扫描：{{ unusedScannedAt || '-' }}</span>
            </div>

            <el-alert
              v-if="unusedError"
              type="warning"
              :closable="false"
              show-icon
              style="margin-bottom: 12px;"
            >
              {{ unusedError }}
            </el-alert>

            <el-table :data="filteredUnused" border style="width: 100%; margin-top: 12px;">
              <el-table-column prop="image" label="镜像" min-width="320">
                <template #default="scope">
                  <div class="mono">{{ scope.row.image }}</div>
                </template>
              </el-table-column>
              <el-table-column label="所在节点" min-width="200">
                <template #default="scope">
                  <div class="nodes">
                    <el-tag v-for="n in (scope.row.nodes || [])" :key="n" size="small" effect="plain" class="node-tag">
                      {{ n }}
                    </el-tag>
                    <span v-if="!(scope.row.nodes || []).length" class="muted">-</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="估算大小" width="140">
                <template #default="scope">
                  <span class="muted">{{ formatBytes(scope.row.size_bytes || 0) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="清理建议" min-width="320">
                <template #default="scope">
                  <div class="cmds">
                    <div class="cmd" v-for="(c, idx) in (scope.row.recommend_commands || [])" :key="idx">
                      <span class="cmd-text mono">{{ c }}</span>
                      <el-button link type="primary" @click="copyCmd(c)">复制</el-button>
                    </div>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <ExpertAdvice title="专家建议" :content="expertContent" />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import ExpertAdvice from '../components/ExpertAdvice.vue'
import { fetchSupplyChain, fetchUnusedImages } from '../api/client'
import { ElMessage } from 'element-plus'

const router = useRouter()
const activeTab = ref('source')
const keyword = ref('')
const onlyInsecure = ref(true)
const loadingSource = ref(false)
const rows = ref([])

const unusedKeyword = ref('')
const loadingUnused = ref(false)
const unusedScannedAt = ref('')
const unusedError = ref('')
const unusedRows = ref([])

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

async function refreshSource() {
  loadingSource.value = true
  try {
    const resp = await fetchSupplyChain()
    rows.value = resp.images || []
  } finally {
    loadingSource.value = false
  }
}

async function refreshUnused() {
  loadingUnused.value = true
  unusedError.value = ''
  try {
    const resp = await fetchUnusedImages()
    if (resp?.error) {
      unusedError.value = `残留镜像扫描失败：${resp.error}`
      unusedRows.value = []
      return
    }
    unusedRows.value = resp.unused_images || []
    unusedScannedAt.value = resp.scanned_at || ''
  } catch (e) {
    unusedError.value = '残留镜像扫描失败（请检查集群权限/连通性）。'
    unusedRows.value = []
  } finally {
    loadingUnused.value = false
  }
}

onMounted(() => {
  refreshSource()
  // 周期刷新，尽量保持页面热状态
})

onBeforeUnmount(() => {})

const filteredRows = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  return (rows.value || []).filter((r) => {
    const text = `${r.namespace || ''} ${r.pod_name || ''} ${r.container_name || ''} ${r.image || ''}`.toLowerCase()
    const kwOk = !k || text.includes(k)
    const riskOk = !onlyInsecure.value || !!r.image_insecure
    return kwOk && riskOk
  })
})

const expertContent = computed(() => {
  const all = rows.value || []
  const insecure = all.filter((x) => x.image_insecure).length
  if (insecure === 0) {
    return '镜像来源整体合规，建议继续执行镜像签名/校验、采用私有镜像仓库，并在 CI/CD 中强化 SBOM 与漏洞扫描，确保供应链安全可持续。'
  }
  return `检测到 ${insecure} 条不安全（公有仓库）镜像。建议将敏感业务镜像私有化（镜像拉取策略/准入控制），并对来源镜像做签名校验与漏洞治理，同时建立镜像基线与变更审批流程。`
})

const filteredUnused = computed(() => {
  const k = unusedKeyword.value.trim().toLowerCase()
  return (unusedRows.value || []).filter((r) => {
    const nodes = (r.nodes || []).join(' ')
    const text = `${r.image || ''} ${nodes}`.toLowerCase()
    return !k || text.includes(k)
  })
})

function formatBytes(bytes) {
  const n = Number(bytes || 0)
  if (!Number.isFinite(n) || n <= 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let idx = 0
  while (v >= 1024 && idx < units.length - 1) {
    v /= 1024
    idx += 1
  }
  return `${v.toFixed(idx === 0 ? 0 : 2)} ${units[idx]}`
}

async function copyCmd(cmd) {
  try {
    await navigator.clipboard.writeText(String(cmd || ''))
    ElMessage.success('已复制清理命令')
  } catch (e) {
    ElMessage.warning('复制失败：请手动复制')
  }
}

function exportUnusedCsv() {
  const rows = filteredUnused.value || []
  const header = ['image', 'nodes', 'size_bytes', 'recommend_commands']
  const lines = [header.join(',')]
  for (const r of rows) {
    const nodes = (r.nodes || []).join(' ')
    const cmds = (r.recommend_commands || []).join(' && ')
    const values = [
      String(r.image || '').replaceAll('"', '""'),
      String(nodes || '').replaceAll('"', '""'),
      String(r.size_bytes || 0),
      String(cmds || '').replaceAll('"', '""')
    ].map((x) => `"${x}"`)
    lines.push(values.join(','))
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `unused_images_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
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
.unused-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 2px 2px;
}
.unused-title {
  font-weight: 900;
  color: #111827;
  font-size: 14px;
}
.unused-sub {
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
}
.meta {
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
}
.muted {
  color: #6b7280;
  font-weight: 700;
}
.nodes {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.node-tag {
  border-radius: 999px;
}
.cmds {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cmd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}
.cmd-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.filters {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
  color: #111827;
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
</style>

