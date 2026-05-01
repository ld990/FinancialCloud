<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <el-card shadow="never" class="card">
        <div class="toolbar">
          <div class="toolbar-left">
            <div class="title">风险分析（主动扫描）</div>
            <div class="sub">最近扫描时间：{{ scannedAt || '-' }}</div>
          </div>
          <div class="toolbar-right">
            <el-button type="primary" :loading="loading" @click="refresh(true)">立即扫描</el-button>
          </div>
        </div>
        <el-tabs v-model="activeTab" class="tabs">
          <el-tab-pane label="特权容器扫描" name="privileged">
            <el-table
              v-if="privileged_risks.length"
              :data="privileged_risks"
              border
              style="width: 100%"
              row-key="pod_name"
            >
              <el-table-column prop="namespace" label="命名空间" width="160" />
              <el-table-column prop="pod_name" label="容器组名称" />
              <el-table-column prop="phase" label="运行阶段" width="120" />
              <el-table-column prop="restart_count" label="重启次数" width="110" />
              <el-table-column label="风险等级" width="120">
                <template #default="scope">
                  <el-tag size="small" type="danger" effect="light">严重</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="特权容器（容器列表）">
                <template #default="scope">
                  <div class="container-list">
                    <div v-for="c in scope.row.containers" :key="c.name" class="container-item">
                      <span class="mono">{{ c.name }}</span>
                      <span class="subtle">({{ c.image }})</span>
                      <span class="pill">重启 {{ c.restart_count || 0 }}</span>
                    </div>
                  </div>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="empty">未发现处于特权模式的容器。</div>
          </el-tab-pane>

          <el-tab-pane label="主机路径挂载风险" name="hostpath">
            <el-table
              v-if="hostpath_risks.length"
              :data="hostpath_risks"
              border
              style="width: 100%"
              row-key="pod_name"
            >
              <el-table-column prop="namespace" label="命名空间" width="160" />
              <el-table-column prop="pod_name" label="容器组名称" />
              <el-table-column prop="phase" label="运行阶段" width="120" />
              <el-table-column prop="restart_count" label="重启次数" width="110" />
              <el-table-column label="风险等级" width="120">
                <template #default>
                  <el-tag size="small" type="warning" effect="light">高危</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="主机路径卷与挂载容器">
                <template #default="scope">
                  <div class="container-list">
                    <div class="sub-title2">主机路径卷</div>
                    <div v-for="v in scope.row.volumes" :key="v.name" class="line">
                      <span class="mono">{{ v.name }}</span> <span class="subtle">{{ v.path }}</span>
                    </div>
                    <div class="sub-title2" style="margin-top:10px;">挂载容器</div>
                    <div v-for="c in scope.row.mount_containers" :key="c.name" class="line">
                      <span class="mono">{{ c.name }}</span>
                      <span class="pill">重启 {{ c.restart_count || 0 }}</span>
                    </div>
                  </div>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="empty">未发现主机路径挂载风险。</div>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <ExpertAdvice title="专家建议" :content="expertContent" />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onActivated, onDeactivated, ref } from 'vue'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import ExpertAdvice from '../components/ExpertAdvice.vue'
import { fetchAdvancedScan } from '../api/client'
import { ElMessage } from 'element-plus'

const router = useRouter()
const activeTab = ref('privileged')
const privileged_risks = ref([])
const hostpath_risks = ref([])
const scannedAt = ref('')
const loading = ref(false)

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

const expertContent = computed(() => {
  const p = privileged_risks.value.length || 0
  const h = hostpath_risks.value.length || 0
  if (p === 0 && h === 0) {
    return '系统当前未发现特权容器与主机路径风险，建议继续保持容器组安全策略（PSA）与镜像安全治理，并对关键命名空间进行周期性复核。'
  }
  return `检测到 ${p} 处特权容器风险与 ${h} 处主机路径挂载风险。建议优先通过准入控制（PSA/OPA）禁止特权与主机路径；对存量容器组建立分批整改计划，并在整改后持续观察事件告警链路。`
})

let timer = null
async function refresh(manual = false) {
  loading.value = !!manual
  try {
    const resp = await fetchAdvancedScan()
    privileged_risks.value = resp.privileged_risks || []
    hostpath_risks.value = resp.hostpath_risks || []
    scannedAt.value = resp.scanned_at || ''
    if (manual) ElMessage.success('扫描完成')
  } catch (e) {
    if (manual) ElMessage.error('扫描失败（请检查集群连通性/权限）')
  } finally {
    loading.value = false
  }
}

onActivated(() => {
  refresh()
  if (timer) clearInterval(timer)
  timer = setInterval(refresh, 180000)
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
.card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 12px 4px;
}
.title {
  font-weight: 900;
  color: #111827;
  font-size: 14px;
}
.sub {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
}
.pill {
  margin-left: 8px;
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #374151;
  font-size: 12px;
  font-weight: 800;
}
.empty {
  padding: 18px 0;
  color: #6b7280;
  font-weight: 900;
  text-align: center;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
}
.subtle {
  color: #6b7280;
  font-weight: 800;
  margin-left: 8px;
}
.container-list {
  line-height: 1.8;
}
.container-item {
  margin-bottom: 6px;
}
.sub-title2 {
  color: #374151;
  font-weight: 900;
  margin-bottom: 8px;
}
.line {
  margin-bottom: 6px;
}
</style>

