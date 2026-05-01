<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <el-card shadow="never" class="card">
        <div class="filters">
          <div class="label">风险类型</div>
          <el-select v-model="riskType" placeholder="请选择" style="width: 220px">
            <el-option label="资源限制缺失" value="resource_limits" />
            <el-option label="特权容器" value="privileged" />
            <el-option label="主机路径挂载风险" value="hostpath" />
          </el-select>

          <div class="label">最多生成</div>
          <el-input-number v-model="maxItems" :min="1" :max="15" />

          <el-button type="primary" :loading="loading" @click="generate">
            一键生成 YAML 补丁
          </el-button>
        </div>

        <el-divider />

        <div class="code-wrap">
          <pre class="yaml" v-if="bundle">{{ bundle }}</pre>
          <div v-else class="empty">点击生成后，这里会展示后端生成的修复 YAML 示例。</div>
        </div>
      </el-card>

      <ExpertAdvice title="专家建议" :content="expertContent" />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import ExpertAdvice from '../components/ExpertAdvice.vue'
import { fetchFixPatch } from '../api/client'

const router = useRouter()
const riskType = ref('resource_limits')
const maxItems = ref(6)
const loading = ref(false)
const bundle = ref('')

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

async function generate() {
  loading.value = true
  try {
    const resp = await fetchFixPatch(riskType.value, maxItems.value)
    bundle.value = resp.bundle || ''
    if (!bundle.value) {
      ElMessage({
        type: 'warning',
        message: '未生成任何 YAML（可能当前集群未检测到该类风险或接口返回空）'
      })
    } else {
      ElMessage({
        type: 'success',
        message: '已生成 YAML 示例，请下拉查看'
      })
    }
  } catch (err) {
    const msg =
      (err?.response?.data?.error) ||
      (err?.message) ||
      '生成失败：网络或后端错误'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}

onMounted(() => {})

const expertContent = computed(() => {
  if (!bundle.value) {
    return '建议先选择风险类型并生成 YAML 示例，再在测试/预生产环境中验证变更效果。上线前请结合变更审批与回滚策略，确保加固不会引入业务不可用风险。'
  }
  return `已为当前风险类型生成修复 YAML 示例（包含最多 ${maxItems.value} 组）。建议将 YAML 纳入基于 Git 的变更流程，配合准入控制与持续监控事件告警反馈闭环。`
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
.filters {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.label {
  color: #374151;
  font-weight: 900;
}
.code-wrap {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
  overflow: auto;
  max-height: 560px;
}
.yaml {
  margin: 0;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
  color: #111827;
  font-size: 12px;
}
.empty {
  color: #6b7280;
  font-weight: 900;
  padding: 16px 0;
  text-align: center;
}
</style>

