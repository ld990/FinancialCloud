<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">
      <div class="stream-status">SSE 状态：{{ streamStatus }}</div>

      <el-alert
        v-if="errorText"
        type="warning"
        :closable="false"
        show-icon
        class="mb14"
      >
        {{ errorText }}
      </el-alert>

      <el-scrollbar height="720px">
        <table class="events-table">
          <thead>
            <tr>
              <th style="width: 190px;">时间</th>
              <th style="width: 110px;">类型</th>
              <th style="width: 180px;">原因</th>
              <th style="width: 240px;">涉及对象</th>
              <th>消息</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(e, idx) in pagedEvents" :key="`${currentPage}-${idx}`">
              <td>{{ formatTime(e.timestamp) }}</td>
              <td>
                <span v-if="e.event_type === 'Warning'" class="badge risk">告警</span>
                <span v-else class="badge ok">正常</span>
              </td>
              <td>{{ e.reason }}</td>
              <td>{{ formatInvolved(e) }}</td>
              <td class="msg">{{ e.message }}</td>
            </tr>
          </tbody>
        </table>
      </el-scrollbar>
      <div class="pager-wrap">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next, jumper"
          :total="events.length"
          :current-page="currentPage"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          @update:current-page="onCurrentPageChange"
          @update:page-size="onPageSizeChange"
        />
      </div>

      <ExpertAdvice title="专家建议" :content="expertContent" />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import SideNav from '../components/SideNav.vue'
import ExpertAdvice from '../components/ExpertAdvice.vue'
import { fetchEventsSnapshot, getApiBaseUrl } from '../api/client'

const router = useRouter()

const events = ref([])
const errorText = ref('')
const streamStatus = ref('未连接')
const currentPage = ref(1)
const pageSize = ref(20)
let es = null
let reconnectTimer = null
const reconnectAttempt = ref(0)
const reconnecting = ref(false)
const maxReconnectDelayMs = 15000

const baseURL = getApiBaseUrl()

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

function formatInvolved(e) {
  const io = e.involved_object || {}
  const kind = io.kind || ''
  const ns = io.namespace ? `/${io.namespace}` : ''
  const name = io.name || ''
  return `${kind}${ns}/${name}`.replace(/\/+/g, '/')
}

function formatTime(ts) {
  if (!ts) return ''
  try {
    // 后端格式是 "YYYY-MM-DD HH:mm:ss+00:00"，浏览器更稳妥解析为 ISO
    const normalized = String(ts).replace(' ', 'T')
    const d = new Date(normalized)
    if (Number.isNaN(d.getTime())) return String(ts)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    return `${hh}:${mm}`
  } catch (_) {
    return String(ts)
  }
}

function startStream() {
  if (es) return
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  errorText.value = ''
  streamStatus.value = reconnecting.value ? '重连中' : '连接中'
  const token = localStorage.getItem('fc_token')
  if (!token) {
    router.push('/login')
    return
  }

  es = new EventSource(`${baseURL}/k8s/events?token=${encodeURIComponent(token)}&limit=200`)
  es.onopen = () => {
    reconnecting.value = false
    reconnectAttempt.value = 0
    streamStatus.value = '已连接'
  }
  es.onmessage = (evt) => {
    try {
      const payload = JSON.parse(evt.data)
      // 前端倒序展示：最新 push 到顶部
      events.value.unshift(payload)
      // 防止无限增长导致卡顿
      if (events.value.length > 500) events.value.pop()
    } catch (err) {
      // ignore
    }
  }
  es.onerror = () => {
    scheduleReconnect()
    streamStatus.value = '连接异常'
    errorText.value = '事件流连接异常（可能是后端暂时无响应）。'
  }
}

async function loadSnapshot() {
  try {
    const resp = await fetchEventsSnapshot(200)
    if (resp?.error) {
      errorText.value = `事件快照加载失败：${resp.error}`
      return
    }
    const list = resp?.events || []
    events.value = list
  } catch (err) {
    errorText.value = '事件快照加载失败（可能是后端暂时无响应）。'
  }
}

function stopStream() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  try {
    es?.close()
  } catch (e) {
    // ignore
  }
  es = null
  streamStatus.value = '未连接'
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnecting.value = true
  reconnectAttempt.value += 1
  const delay = Math.min(1000 * (2 ** (reconnectAttempt.value - 1)), maxReconnectDelayMs)
  stopStream()
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    startStream()
  }, delay)
}

function onCurrentPageChange(page) {
  currentPage.value = Number(page) || 1
}

function onPageSizeChange(size) {
  pageSize.value = Number(size) || 20
  currentPage.value = 1
}

const pagedEvents = computed(() => {
  const list = events.value || []
  const start = (currentPage.value - 1) * pageSize.value
  return list.slice(start, start + pageSize.value)
})

watch(
  () => events.value.length,
  (len) => {
    const totalPages = Math.max(1, Math.ceil(len / pageSize.value))
    if (currentPage.value > totalPages) currentPage.value = totalPages
  }
)

onActivated(() => {
  loadSnapshot()
  startStream()
})

onDeactivated(() => {
  stopStream()
})

onMounted(() => {
  loadSnapshot()
  startStream()
})

onUnmounted(() => {
  stopStream()
})

const expertContent = computed(() => {
  const list = events.value || []
  const warnCount = list.filter((x) => x.event_type === 'Warning').length
  if (warnCount === 0) {
    return '当前告警事件指标较低。建议保持安全基线，定期复核资源限制、特权容器与主机路径风险，并在变更后重点关注告警是否收敛。'
  }
  return `当前已捕获到 ${warnCount} 条告警事件。建议从原因入手定位根因（如资源不足、镜像拉取失败、安全策略拒绝），并与审计清单联动制定处置动作与回归验证。`
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
.mb14 {
  margin-bottom: 14px;
}
.stream-status {
  color: #374151;
  font-weight: 900;
  margin-bottom: 10px;
}
.events-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  overflow: hidden;
}
.events-table thead th {
  background: #f3f4f6;
  color: #111827;
  text-align: left;
  padding: 12px 10px;
  font-weight: 900;
}
.events-table tbody td {
  padding: 10px 10px;
  border-bottom: 1px solid #e5e7eb;
  vertical-align: top;
  color: #111827;
  font-weight: 600;
}
.events-table tbody tr:last-child td {
  border-bottom: none;
}
.msg {
  max-width: 520px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1f2937;
}
.badge {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 900;
  font-size: 12px;
  border: 1px solid transparent;
}
.ok {
  background: #dbeafe;
  color: #1d4ed8;
  border-color: #93c5fd;
}
.risk {
  background: #fee2e2;
  color: #b91c1c;
  border-color: #fca5a5;
}
.pager-wrap {
  margin: 12px 0 14px;
  display: flex;
  justify-content: flex-end;
}
</style>

