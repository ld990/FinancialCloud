<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <el-card shadow="never" class="card">
        <div class="toolbar">
          <el-button :loading="loading" type="primary" @click="refresh">扫描镜像来源</el-button>
          <el-checkbox v-model="onlyInsecure">仅显示不安全公有仓库（如 Docker Hub）</el-checkbox>
        </div>

        <el-table :data="filteredRows" border style="width: 100%; margin-top: 14px;">
          <el-table-column prop="namespace" label="命名空间" width="160" />
          <el-table-column prop="pod_name" label="容器组" />
          <el-table-column prop="container_name" label="容器" width="150" />
          <el-table-column prop="image" label="镜像" />
          <el-table-column label="来源合规" width="160">
            <template #default="scope">
              <span v-if="scope.row.image_insecure" class="badge risk">❌ 风险</span>
              <span v-else class="badge ok">✅ 合规</span>
            </template>
          </el-table-column>
          <el-table-column prop="image_registry" label="镜像仓库" width="200" />
        </el-table>
      </el-card>
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import { fetchAudit } from '../api/client'

const router = useRouter()
const loading = ref(false)
const onlyInsecure = ref(true)
const rows = ref([])

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

const filteredRows = computed(() => {
  if (!onlyInsecure.value) return rows.value
  return rows.value.filter((r) => r.image_insecure)
})

async function refresh() {
  loading.value = true
  try {
    const audit = await fetchAudit({}) // 直接复用 audit 的容器镜像数据
    const next = []
    for (const p of audit || []) {
      const ns = p.namespace || ''
      const pod = p.pod_name || ''
      for (const c of p.containers || []) {
        next.push({
          namespace: ns,
          pod_name: pod,
          container_name: c.name || '',
          image: c.image || '',
          image_insecure: !!c.image_insecure,
          image_registry: c.image_registry || ''
        })
      }
    }
    rows.value = next
  } finally {
    loading.value = false
  }
}

let timer = null
onMounted(() => {
  refresh()
  timer = setInterval(refresh, 180000)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.layout {
  min-height: 100vh;
  height: 100vh;
  background: #101014;
}
.main {
  padding: 18px 22px;
  height: 100%;
  overflow-y: auto;
}
.card {
  background: #18181c;
  border: 1px solid #2d2d30;
  border-radius: 8px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
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

