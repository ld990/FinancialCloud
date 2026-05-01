<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <el-card shadow="never" class="card">
        <el-descriptions title="当前登录信息" :column="1" border>
          <el-descriptions-item label="用户名">{{ me.username }}</el-descriptions-item>
          <el-descriptions-item label="权限等级">{{ me.role }}</el-descriptions-item>
          <el-descriptions-item label="令牌状态">
            <span v-if="tokenPresent" class="badge ok">已登录</span>
            <span v-else class="badge risk">未登录</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="actions">
          <el-button type="danger" :disabled="!tokenPresent" @click="logout">
            安全退出
          </el-button>
        </div>
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
import { fetchMe } from '../api/client'

const router = useRouter()
const me = ref({ username: '', role: '' })
const tokenPresent = ref(!!localStorage.getItem('fc_token'))

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

async function loadMe() {
  const token = localStorage.getItem('fc_token')
  if (!token) return
  me.value = await fetchMe()
}

onMounted(() => {
  loadMe()
})

const expertContent = computed(() => {
  const role = me.value?.role || ''
  if (!role) return '建议检查登录态与后端鉴权是否生效，确保高权限操作仅对管理员开放，并启用审计追踪。'
  return `当前账号权限为「${role}」。建议严格控制权限变更流程，结合最小权限原则与操作留痕策略，确保金融 SOC 内部审计可追溯。`
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
.actions {
  margin-top: 14px;
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

