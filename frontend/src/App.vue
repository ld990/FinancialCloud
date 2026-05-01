<template>
  <el-config-provider :size="'default'" :z-index="3000" :button="{ autoInsertSpace: true }">
    <div v-if="isAuthedPage" class="shell" :class="{ collapsed: isCollapsed }">
      <aside class="shell-aside">
        <div class="brand">金融云安全监查平台</div>
        <el-scrollbar height="calc(100vh - 56px)">
          <el-menu class="menu" :default-active="activeMenu" router>
            <el-menu-item index="/home">🏠 首页</el-menu-item>
            <el-sub-menu index="monitor">
              <template #title>📊 监控中心</template>
              <el-menu-item index="/dashboard">实时概览</el-menu-item>
              <el-menu-item index="/monitor/board">监控看板</el-menu-item>
              <el-menu-item index="/resources">资源分布</el-menu-item>
            </el-sub-menu>
            <el-sub-menu index="audit">
              <template #title>🛡️ 安全审计</template>
              <el-menu-item index="/audit">合规扫描</el-menu-item>
              <el-menu-item index="/security/advanced">风险分析</el-menu-item>
              <el-menu-item index="/security/supply">供应链扫描</el-menu-item>
            </el-sub-menu>
            <el-sub-menu index="ops">
              <template #title>🧰 运维工具</template>
              <el-menu-item index="/tools/fix">修复助手</el-menu-item>
              <el-menu-item index="/tools/report">报告导出</el-menu-item>
            </el-sub-menu>
            <el-sub-menu index="sys">
              <template #title>⚙️ 系统中心</template>
              <el-menu-item index="/events">事件日志</el-menu-item>
              <el-menu-item index="/account">个人中心</el-menu-item>
              <el-menu-item v-if="isAdmin" index="/users">人员管理</el-menu-item>
            </el-sub-menu>
          </el-menu>
        </el-scrollbar>
      </aside>

      <header class="shell-header">
        <div class="header-left">
          <el-button link @click="toggleSidebar">{{ isCollapsed ? '☰' : '☰' }}</el-button>
          <span class="header-title">{{ pageTitle }}</span>
        </div>
        <div class="header-right">
          <el-dropdown trigger="click" @command="onClusterCommand">
            <span class="cluster-wrap">
              <span class="cluster-label">集群：</span>
              <span class="cluster-name">{{ currentClusterName }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  切换当前集群（影响监控/审计/事件数据源）
                </el-dropdown-item>
                <el-dropdown-item divided command="__goto_clusters__">管理/选择集群</el-dropdown-item>
                <el-dropdown-item command="__reset_default__">切回默认集群</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-dropdown>
            <span class="avatar-wrap">
              <el-avatar size="small">{{ userInitial }}</el-avatar>
              <span class="username">{{ username }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="goAccount">个人中心</el-dropdown-item>
                <el-dropdown-item divided @click="doLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="shell-content">
        <router-view />
      </main>
    </div>

    <router-view v-else />
  </el-config-provider>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiLogout, fetchMe, resetClusterToDefault } from './api/client'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const isCollapsed = ref(false)

const isAuthedPage = computed(() => route.path !== '/login' && !!localStorage.getItem('fc_token'))
const activeMenu = computed(() => route.path)
const username = computed(() => localStorage.getItem('fc_username') || '用户')
const userInitial = computed(() => username.value.slice(0, 1).toUpperCase())
const isAdmin = computed(() => (localStorage.getItem('fc_role') || '') === 'admin')
const currentClusterName = ref('未选择')

const pageTitleMap = {
  '/home': '首页',
  '/dashboard': '实时概览',
  '/monitor/board': '监控看板',
  '/resources': '资源分布',
  '/audit': '安全审计',
  '/security/advanced': '风险分析',
  '/security/supply': '供应链扫描',
  '/tools/fix': '修复助手',
  '/tools/report': '报告导出',
  '/events': '事件日志',
  '/account': '个人中心',
  '/users': '人员管理'
}

const pageTitle = computed(() => pageTitleMap[route.path] || '金融云安全监查平台')

function toggleSidebar() {
  isCollapsed.value = !isCollapsed.value
}

function goAccount() {
  router.push('/account')
}

async function doLogout() {
  try {
    await apiLogout()
  } catch (_) {
    // ignore
  } finally {
    localStorage.removeItem('fc_token')
    localStorage.removeItem('fc_username')
    localStorage.removeItem('fc_role')
    localStorage.removeItem('fc_status')
    router.push('/login')
  }
}

onMounted(async () => {
  if (!localStorage.getItem('fc_token')) return
  try {
    const me = await fetchMe()
    localStorage.setItem('fc_username', me?.display_name || me?.username || '用户')
    localStorage.setItem('fc_role', me?.role || '')
    localStorage.setItem('fc_status', me?.status || '')
    const cid = me?.cluster_id ?? null
    currentClusterName.value = cid ? `ID:${cid}` : '默认'
    if (!cid && route.path !== '/clusters') {
      ElMessage.info('请先在“集群管理”中选择一个集群')
      router.push('/clusters')
    }
  } catch (_) {
    // ignore
  }
})

async function onClusterCommand(cmd) {
  if (cmd === '__goto_clusters__') {
    router.push('/clusters')
    return
  }
  if (cmd === '__reset_default__') {
    try {
      await resetClusterToDefault()
      currentClusterName.value = '默认'
      ElMessage.success('已切回默认集群')
    } catch (e) {
      ElMessage.error(e?.response?.data?.detail || '切回默认集群失败')
    }
  }
}
</script>

<style>
html, body, #app {
  height: 100%;
}
body {
  margin: 0;
  background: #f5f6f8;
  color: #111111;
}
* {
  box-sizing: border-box;
}

.shell {
  --aside-width: 220px;
  position: relative;
  min-height: 100vh;
  padding-left: var(--aside-width);
  padding-top: 56px;
  transition: padding-left 0.2s ease;
}
.shell.collapsed {
  --aside-width: 0px;
}

.shell-aside {
  position: fixed;
  left: 0;
  top: 0;
  width: 220px;
  height: 100vh;
  background: linear-gradient(180deg, #123b6d 0%, #0f2f57 100%);
  color: #d9e6ff;
  border-right: 1px solid #1a4b82;
  z-index: 1200;
  transition: transform 0.2s ease;
}
.shell.collapsed .shell-aside {
  transform: translateX(-100%);
}
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 14px;
  font-size: 14px;
  font-weight: 800;
  color: #ffffff;
  border-bottom: 1px solid #2b5f96;
  background: rgba(6, 24, 47, 0.28);
}
.menu {
  border-right: none;
  background: transparent;
}
.menu.el-menu {
  background: transparent;
}
.shell-aside .el-sub-menu .el-menu {
  background: rgba(4, 19, 38, 0.22) !important;
}
.shell-aside .el-menu-item,
.shell-aside .el-sub-menu__title {
  color: #e2edff !important;
}
.shell-aside .el-menu-item.is-active {
  color: #ffffff !important;
  background: #2c68b0 !important;
}
.shell-aside .el-menu-item:hover,
.shell-aside .el-sub-menu__title:hover {
  background: rgba(54, 124, 195, 0.42) !important;
}

.shell-header {
  position: fixed;
  left: var(--aside-width);
  right: 0;
  top: 0;
  height: 56px;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;
  z-index: 1100;
  transition: left 0.2s ease;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-title {
  font-weight: 700;
  color: #111111;
}
.avatar-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.cluster-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 999px;
  cursor: pointer;
  user-select: none;
}
.cluster-label {
  color: #6b7280;
  font-size: 12px;
}
.cluster-name {
  color: #111111;
  font-weight: 800;
  font-size: 12px;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.username {
  color: #374151;
  font-size: 13px;
}

.shell-content {
  min-height: calc(100vh - 56px);
  padding: 12px;
}

/* 兼容旧页面：隐藏各页面自带侧栏，保留内容区 */
.shell-content .layout > .el-aside {
  display: none !important;
}
.shell-content .layout > .el-main.main {
  padding: 0 !important;
  height: auto !important;
  overflow: visible !important;
}
.shell-content .layout {
  min-height: auto !important;
  height: auto !important;
  background: transparent !important;
}

/* 全局浅色基调 */
body {
  --el-text-color-primary: #111111;
  --el-text-color-regular: #1f2329;
  --el-text-color-secondary: #5b6470;
  --el-border-color: #e5e7eb;
  --el-bg-color: #ffffff;
}
</style>

