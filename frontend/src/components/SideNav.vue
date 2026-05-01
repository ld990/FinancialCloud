<template>
  <div class="sidenav">
    <div class="brand">
      <div class="shield">🛡️</div>
      <div class="name">金融云安全监查平台</div>
    </div>

    <el-menu
      class="menu"
      :default-active="active"
      router
      background-color="#ffffff"
      text-color="#374151"
      active-text-color="#111111"
      unique-opened
    >
      <el-sub-menu index="monitor">
        <template #title>
          <i class="fa-solid fa-server menu-icon" /> <span>📊 监控中心</span>
        </template>
        <el-menu-item index="/home">
          <i class="fa-solid fa-house menu-icon" /> <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/dashboard">
          <i class="fa-solid fa-chart-line menu-icon" /> <span>实时概览</span>
        </el-menu-item>
        <el-menu-item index="/resources">
          <i class="fa-solid fa-chart-column menu-icon" /> <span>资源分布</span>
        </el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="audit">
        <template #title>
          <i class="fa-solid fa-shield menu-icon" /> <span>🛡️ 安全审计</span>
        </template>
        <el-menu-item index="/audit">
          <i class="fa-solid fa-list-check menu-icon" /> <span>合规扫描</span>
        </el-menu-item>
        <el-menu-item index="/security/advanced">
          <i class="fa-solid fa-user-shield menu-icon" /> <span>风险分析</span>
        </el-menu-item>
        <el-menu-item index="/security/supply">
          <i class="fa-solid fa-diagram-project menu-icon" /> <span>供应链扫描</span>
        </el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="ops">
        <template #title>
          <i class="fa-solid fa-wrench menu-icon" /> <span>🛠️ 运维工具</span>
        </template>
        <el-menu-item index="/tools/fix">
          <i class="fa-solid fa-clipboard-check menu-icon" /> <span>修复助手</span>
        </el-menu-item>
        <el-menu-item index="/tools/report">
          <i class="fa-solid fa-file-export menu-icon" /> <span>报告导出</span>
        </el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="sys">
        <template #title>
          <i class="fa-solid fa-user-shield menu-icon" /> <span>📜 系统中心</span>
        </template>
        <el-menu-item index="/events">
          <i class="fa-solid fa-list menu-icon" /> <span>事件日志</span>
        </el-menu-item>
        <el-menu-item index="/clusters">
          <i class="fa-solid fa-network-wired menu-icon" /> <span>集群管理</span>
        </el-menu-item>
        <el-menu-item index="/account">
          <i class="fa-solid fa-user-tie menu-icon" /> <span>账户管理</span>
        </el-menu-item>
      </el-sub-menu>
    </el-menu>

    <div class="spacer" />

    <el-button class="logout-btn" type="danger" @click="onLogout">
      注销退出
    </el-button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { apiLogout } from '../api/client'

const route = useRoute()
const active = computed(() => route.path)

const emit = defineEmits(['logout'])

async function onLogout() {
  try {
    await apiLogout()
  } catch (e) {
    // ignore: token 可能已过期或网络临时失败
  } finally {
		emit('logout')
  }
}
</script>

<style scoped>
.sidenav {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 14px 10px;
  background: #ffffff;
  border-right: 1px solid #e5e7eb;
}

.brand {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px 6px;
}
.shield {
  font-size: 22px;
}
.name {
  font-weight: 800;
  color: #111111;
  font-size: 13px;
  line-height: 1.35;
  word-break: break-all;
}

.menu {
  border-right: none;
}

.spacer {
  flex: 1;
}

.logout-btn {
  border-radius: 8px;
  font-weight: 900;
}

.menu-icon {
  width: 20px;
  text-align: center;
  color: #6b7280;
  margin-right: 8px;
}
</style>

