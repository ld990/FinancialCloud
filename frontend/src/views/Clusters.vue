<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">
      <el-card shadow="never" class="mb14">
        <template #header>
          <div class="card-title">集群管理</div>
        </template>
        <div class="card-tip">
          管理可接入的 Kubernetes 集群信息，并支持“设为当前集群”。你在这里选择的集群会作用于平台的监控/审计/事件等数据来源。
        </div>
        <div class="current-line">
          当前集群：<b>{{ currentClusterLabel }}</b>
        </div>
      </el-card>

      <el-alert
        v-if="errorText"
        type="warning"
        :closable="false"
        show-icon
        class="mb14"
      >
        {{ errorText }}
      </el-alert>

      <el-card shadow="never" class="mb14">
        <template #header>
          <div class="card-title">添加集群</div>
        </template>
        <el-form :model="form" label-width="110px">
          <el-form-item label="集群名称">
            <el-input v-model="form.name" placeholder="例如：生产集群" :disabled="!isAdmin" />
          </el-form-item>
          <el-form-item label="API 地址">
            <el-input
              v-model="form.api_server"
              placeholder="例如：https://10.0.0.1:6443"
              :disabled="!isAdmin"
            />
          </el-form-item>
          <el-form-item label="描述">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              placeholder="可选：集群用途、所属环境等"
              :disabled="!isAdmin"
            />
          </el-form-item>
          <el-form-item label="kubeconfig">
            <el-input
              v-model="form.kubeconfig_yaml"
              type="textarea"
              :rows="6"
              placeholder="粘贴 kubeconfig YAML（建议使用只读权限账号）"
              :disabled="!isAdmin"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :disabled="!isAdmin || submitting" @click="onCreateCluster">
              添加集群
            </el-button>
            <span v-if="!isAdmin" class="muted">当前账号非管理员，仅可查看。</span>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-title">集群列表</div>
        </template>
        <el-table :data="clusters" stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="api_server" label="API 地址" min-width="260" />
          <el-table-column prop="description" label="描述" min-width="220" />
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button
                type="primary"
                link
                :disabled="selecting || String(currentClusterId) === String(row.id)"
                @click="onSelectCluster(row.id)"
              >
                设为当前
              </el-button>
              <el-button
                type="danger"
                link
                :disabled="!isAdmin"
                @click="onDeleteCluster(row.id)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-main>
  </el-container>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import { createCluster, deleteCluster, fetchClusters, fetchMe, selectCluster } from '../api/client'

const router = useRouter()
const clusters = ref([])
const errorText = ref('')
const submitting = ref(false)
const selecting = ref(false)
const isAdmin = ref(localStorage.getItem('fc_role') === 'admin')
const currentClusterId = ref(null)
const currentClusterLabel = ref('默认集群')

const form = reactive({
  name: '',
  api_server: '',
  description: '',
  kubeconfig_yaml: ''
})

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

async function loadClusters() {
  try {
    errorText.value = ''
    const resp = await fetchClusters()
    clusters.value = resp?.clusters || []
  } catch (err) {
    errorText.value = err?.response?.data?.detail || '集群列表加载失败'
  }
}

async function loadMe() {
  try {
    const me = await fetchMe()
    currentClusterId.value = me?.cluster_id ?? null
    if (!currentClusterId.value) {
      currentClusterLabel.value = '默认集群'
      return
    }
    const hit = (clusters.value || []).find((c) => String(c.id) === String(currentClusterId.value))
    currentClusterLabel.value = hit ? `${hit.name}（ID:${hit.id}）` : `已选择集群（ID:${currentClusterId.value}）`
  } catch (_) {
    // ignore
  }
}

async function onCreateCluster() {
  if (!form.name.trim() || !form.api_server.trim()) {
    ElMessage.warning('请填写集群名称和 API 地址')
    return
  }
  if (!form.kubeconfig_yaml.trim()) {
    ElMessage.warning('请粘贴 kubeconfig YAML')
    return
  }
  try {
    submitting.value = true
    errorText.value = ''
    await createCluster({
      name: form.name,
      api_server: form.api_server,
      description: form.description,
      kubeconfig_yaml: form.kubeconfig_yaml
    })
    ElMessage.success('集群添加成功')
    form.name = ''
    form.api_server = ''
    form.description = ''
    form.kubeconfig_yaml = ''
    await loadClusters()
    await loadMe()
  } catch (err) {
    errorText.value = err?.response?.data?.detail || '添加集群失败'
  } finally {
    submitting.value = false
  }
}

async function onSelectCluster(clusterId) {
  try {
    selecting.value = true
    errorText.value = ''
    await selectCluster(clusterId)
    ElMessage.success('已切换当前集群')
    await loadMe()
  } catch (err) {
    errorText.value = err?.response?.data?.detail || '切换集群失败'
  } finally {
    selecting.value = false
  }
}

async function onDeleteCluster(clusterId) {
  try {
    await ElMessageBox.confirm('确认删除该集群吗？', '提示', {
      type: 'warning'
    })
    await deleteCluster(clusterId)
    ElMessage.success('删除成功')
    await loadClusters()
    await loadMe()
  } catch (err) {
    if (err === 'cancel') return
    errorText.value = err?.response?.data?.detail || '删除集群失败'
  }
}

onMounted(() => {
  loadClusters().then(loadMe)
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
.mb14 {
  margin-bottom: 14px;
}
.card-title {
  font-weight: 800;
}
.card-tip {
  color: #5b6470;
  line-height: 1.7;
}
.current-line {
  margin-top: 8px;
  color: #374151;
}
.muted {
  margin-left: 10px;
  color: #909399;
  font-size: 13px;
}
</style>
