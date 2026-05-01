<template>
  <div class="users-page">
    <div class="toolbar">
      <el-button type="primary" @click="showCreate = true">新建账号</el-button>
      <el-button @click="loadUsers">刷新</el-button>
    </div>

    <el-alert
      v-if="forbidden"
      title="仅管理员可访问人员管理页面"
      type="warning"
      :closable="false"
      show-icon
      class="mb12"
    />

    <el-table v-else :data="users" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" width="140" />
      <el-table-column prop="display_name" label="显示名称" width="160" />
      <el-table-column prop="role" label="角色" width="120">
        <template #default="{ row }">
          <el-tag>{{ roleText(row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.status === 'approved' ? 'success' : row.status === 'pending' ? 'warning' : 'danger'">
            {{ statusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="审核" width="210">
        <template #default="{ row }">
          <el-button size="small" type="success" @click="changeStatus(row, 'approved')">通过</el-button>
          <el-button size="small" type="danger" @click="changeStatus(row, 'rejected')">拒绝</el-button>
        </template>
      </el-table-column>
      <el-table-column label="角色分配" width="240">
        <template #default="{ row }">
          <el-select :model-value="row.role" style="width: 120px" @change="(v) => changeRole(row, v)">
            <el-option label="管理员" value="admin" />
            <el-option label="审计员" value="auditor" />
            <el-option label="只读用户" value="viewer" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showCreate" title="新建账号" width="460px">
      <el-form :model="createForm" label-width="90px">
        <el-form-item label="用户名">
          <el-input v-model="createForm.username" />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="createForm.display_name" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="createForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="审计员" value="auditor" />
            <el-option label="只读用户" value="viewer" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="createForm.status" style="width: 100%">
            <el-option label="已通过" value="approved" />
            <el-option label="待审核" value="pending" />
            <el-option label="已拒绝" value="rejected" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createUser, fetchUsers, updateUserRole, updateUserStatus } from '../api/client'

const users = ref([])
const forbidden = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const createForm = reactive({
  username: '',
  display_name: '',
  password: '',
  role: 'viewer',
  status: 'approved'
})

function roleText(role) {
  const map = {
    admin: '管理员',
    auditor: '审计员',
    viewer: '只读用户'
  }
  return map[role] || role
}

function statusText(status) {
  const map = {
    approved: '已通过',
    pending: '待审核',
    rejected: '已拒绝'
  }
  return map[status] || status
}

async function loadUsers() {
  forbidden.value = false
  try {
    const resp = await fetchUsers()
    users.value = resp?.users || []
  } catch (err) {
    if (err?.response?.status === 403) {
      forbidden.value = true
      users.value = []
      return
    }
    ElMessage.error(err?.response?.data?.detail || '加载用户失败')
  }
}

async function changeStatus(row, status) {
  try {
    await updateUserStatus(row.id, status)
    ElMessage.success('审核状态已更新')
    await loadUsers()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '更新状态失败')
  }
}

async function changeRole(row, role) {
  try {
    await updateUserRole(row.id, role)
    ElMessage.success('角色已更新')
    await loadUsers()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '更新角色失败')
  }
}

async function submitCreate() {
  creating.value = true
  try {
    await createUser(createForm)
    ElMessage.success('账号创建成功')
    showCreate.value = false
    createForm.username = ''
    createForm.display_name = ''
    createForm.password = ''
    createForm.role = 'viewer'
    createForm.status = 'approved'
    await loadUsers()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 10px;
}
.mb12 {
  margin-bottom: 12px;
}
</style>
