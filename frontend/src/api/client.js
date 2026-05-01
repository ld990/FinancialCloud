import axios from 'axios'

const baseURL =
  import.meta.env.VITE_API_BASE_URL || ''

export function getApiBaseUrl() {
  const configured = String(import.meta.env.VITE_API_BASE_URL || '').trim()
  if (configured) {
    return configured.replace(/\/+$/, '')
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    return String(window.location.origin).replace(/\/+$/, '')
  }
  return ''
}

export const api = axios.create({
  baseURL,
  timeout: 30000
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('fc_token')
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 全局处理 401：清理登录态并回到登录页，避免页面静默显示初始空数据
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status
    if (status === 401) {
      try {
        localStorage.removeItem('fc_token')
      } catch (_) {}
      // 使用硬跳转确保路由守卫生效
      if (typeof window !== 'undefined') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export async function login(username, password) {
  const resp = await api.post('/auth/login', { username, password })
  return resp.data
}

export async function registerUser(payload) {
  const resp = await api.post('/auth/register', payload)
  return resp.data
}

export async function fetchOverview() {
  const resp = await api.get('/k8s/overview')
  return resp.data
}

export async function fetchOverviewComponents() {
  const resp = await api.get('/k8s/overview/components')
  return resp.data
}

export async function fetchAudit(params = {}) {
  const resp = await api.get('/k8s/audit', { params })
  return resp.data
}

export async function fetchResourcesUsage() {
  const resp = await api.get('/k8s/resources/usage')
  return resp.data
}

export async function fetchNodeTopUsage() {
  const resp = await api.get('/k8s/resources/node-top')
  return resp.data
}

export async function fetchAdvancedScan() {
  const resp = await api.get('/k8s/security/advanced-scan')
  return resp.data
}

export async function fetchSupplyChain() {
  const resp = await api.get('/k8s/security/supply-chain')
  return resp.data
}

export async function fetchUnusedImages() {
  const resp = await api.get('/k8s/security/supply-chain/unused')
  return resp.data
}

export async function fetchTopAlerts(limit = 5) {
  const resp = await api.get('/k8s/security/top-alerts', { params: { limit } })
  return resp.data
}

export async function fetchFixPatch(riskType, maxItems = 6) {
  const resp = await api.get('/k8s/fix/patch', { params: { risk_type: riskType, max_items: maxItems } })
  return resp.data
}

export async function fetchWeeklyReportPreview() {
  const resp = await api.get('/k8s/reports/weekly-preview')
  return resp.data
}

export async function fetchWeeklyReportCsv() {
  const resp = await api.get('/k8s/reports/weekly-csv')
  return resp.data
}

export async function fetchMe() {
  const resp = await api.get('/auth/me')
  return resp.data
}

export async function apiLogout() {
  const resp = await api.post('/auth/logout')
  return resp.data
}

export async function fetchEventsSnapshot(limit = 200) {
  const resp = await api.get('/k8s/events/snapshot', { params: { limit } })
  return resp.data
}

export async function fetchUsers() {
  const resp = await api.get('/users')
  return resp.data
}

export async function fetchClusters() {
  const resp = await api.get('/clusters')
  return resp.data
}

export async function createCluster(payload) {
  const resp = await api.post('/clusters', payload)
  return resp.data
}

export async function deleteCluster(clusterId) {
  const resp = await api.delete(`/clusters/${clusterId}`)
  return resp.data
}

export async function selectCluster(clusterId) {
  const resp = await api.post(`/clusters/${clusterId}/select`)
  return resp.data
}

export async function resetClusterToDefault() {
  const resp = await api.post('/clusters/0/select')
  return resp.data
}

export async function createUser(payload) {
  const resp = await api.post('/users', payload)
  return resp.data
}

export async function updateUserStatus(userId, status) {
  const resp = await api.patch(`/users/${userId}/status`, { status })
  return resp.data
}

export async function updateUserRole(userId, role) {
  const resp = await api.patch(`/users/${userId}/role`, { role })
  return resp.data
}

export async function uploadFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  const resp = await api.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return resp.data
}

export async function fetchExternalLinks() {
  const resp = await api.get('/config/external-links')
  return resp.data
}

export async function updateExternalLinks(links) {
  const resp = await api.post('/config/external-links', links)
  return resp.data
}
