<template>
  <div class="page">
    <div class="login-card">
      <div class="header">
        <div class="shield"></div>
        <div class="title">金融云安全监查平台</div>
        <div class="subtitle">欢迎登录，请使用账号和密码登录系统</div>
      </div>

      <el-form :model="form" label-position="left" label-width="80px" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="admin" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="admin123" show-password />
        </el-form-item>
        <el-checkbox v-model="remember">记住密码</el-checkbox>
      </el-form>

      <el-button class="login-btn fancy" type="primary" :loading="loading" @click="doLogin">
        登 录
      </el-button>
      <div class="register-entry">
        还没有账号？
        <el-button link type="primary" @click="showRegister = true">立即注册</el-button>
      </div>

      <div class="footer">© 2026 金融云安全监查平台.</div>
    </div>

    <el-dialog v-model="showRegister" title="用户注册" width="420px">
      <el-form :model="registerForm" label-width="90px">
        <el-form-item label="用户名">
          <el-input v-model="registerForm.username" placeholder="至少3位" />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="registerForm.display_name" placeholder="请输入姓名或昵称" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="registerForm.password" type="password" show-password placeholder="至少6位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRegister = false">取消</el-button>
        <el-button type="primary" :loading="registerLoading" @click="doRegister">提交注册</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { login, registerUser } from '../api/client'

const router = useRouter()
const form = reactive({
  username: 'admin',
  password: 'admin123'
})
const loading = ref(false)
const remember = ref(false)
const showRegister = ref(false)
const registerLoading = ref(false)
const registerForm = reactive({
  username: '',
  display_name: '',
  password: ''
})

function toZhErrorMessage(msg, fallback) {
  if (!msg) return fallback
  const map = {
    'Account is pending approval': '账号待审核，请联系管理员审批后登录',
    'Invalid credentials': '用户名或密码错误',
    'Username already exists': '用户名已存在'
  }
  return map[msg] || msg
}

async function doLogin() {
  loading.value = true
  try {
    const res = await login(form.username, form.password)
    localStorage.setItem('fc_token', res.token)
    localStorage.setItem('fc_username', res.username || form.username)
    localStorage.setItem('fc_role', res.role || '')
    localStorage.setItem('fc_status', res.status || '')
    router.push('/home')
  } catch (err) {
    const msg = err?.response?.data?.detail
    ElMessage.error(toZhErrorMessage(msg, '登录失败'))
  } finally {
    loading.value = false
  }
}

async function doRegister() {
  registerLoading.value = true
  try {
    await registerUser(registerForm)
    ElMessage.success('注册成功，等待管理员审核后可登录')
    showRegister.value = false
    registerForm.username = ''
    registerForm.display_name = ''
    registerForm.password = ''
  } catch (err) {
    const msg = err?.response?.data?.detail
    ElMessage.error(toZhErrorMessage(msg, '注册失败'))
  } finally {
    registerLoading.value = false
  }
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #eceef2;
}
.login-card {
  width: 420px;
  max-width: 96vw;
  background: #ffffff;
  border: 1px solid #e6e8ed;
  border-radius: 8px;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
  padding: 28px 28px 22px;
}
.header {
  text-align: center;
  margin-bottom: 20px;
}
.shield {
  font-size: 32px;
  margin-bottom: 8px;
}
.title {
  font-weight: 700;
  color: #111827;
  font-size: 30px;
  margin-bottom: 8px;
}
.subtitle {
  color: #6b7280;
  font-size: 13px;
}
.login-card :deep(.el-form-item) {
  margin-bottom: 16px;
}
.login-card :deep(.el-form-item__label) {
  color: #374151 !important;
  font-weight: 600;
  line-height: 40px;
  padding-right: 10px;
}
.login-card :deep(.el-input__wrapper) {
  height: 40px;
  background: #ffffff !important;
  border: 1px solid #d1d5db !important;
  box-shadow: none !important;
  border-radius: 3px;
}
.login-card :deep(.el-input__inner) {
  color: #111827 !important;
}
.login-card :deep(.el-input__inner::placeholder) {
  color: #9ca3af !important;
}
.login-btn {
  width: 100%;
  border-radius: 4px;
  margin-top: 16px;
  font-weight: 700;
}
.login-btn.fancy {
  height: 40px;
  border: none;
  background: #2f8ef7;
  box-shadow: none;
  letter-spacing: 4px;
}
.login-btn.fancy:hover {
  background: #4a9fff;
  transform: none;
}
.login-btn.fancy:active {
  transform: none;
  box-shadow: none;
}
.register-entry {
  margin-top: 10px;
  font-size: 13px;
  color: #6b7280;
  text-align: center;
}
.footer {
  text-align: center;
  margin-top: 16px;
  color: #9ca3af;
  font-size: 12px;
}
</style>

