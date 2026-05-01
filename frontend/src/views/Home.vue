<template>
  <el-container class="layout">
    <el-aside width="220">
      <SideNav @logout="logout" />
    </el-aside>

    <el-main class="main">

      <el-card shadow="never" class="welcome-card">
        <h3>欢迎使用金融云安全监查平台</h3>
        <p>聚焦 Kubernetes 集群安全监控、事件追踪与合规治理，帮助团队快速构建可持续的安全运维闭环。</p>
      </el-card>

      <div class="section-head">
        <div class="section-title">轮播图管理</div>
        <div>
          <el-button @click="showAddDialog = true" type="primary">添加轮播图</el-button>
        </div>
      </div>
      <el-carousel class="carousel" height="300px">
        <el-carousel-item v-for="img in carouselImages" :key="img.id">
          <div class="carousel-item">
            <img :src="getFullImageUrl(img.url)" :alt="img.name" class="carousel-image" />
            <div class="carousel-delete" @click="deleteCarouselItem(img.id)">
              <el-icon><Delete /></el-icon>
            </div>
          </div>
        </el-carousel-item>
      </el-carousel>

      <div class="section-head">
        <div class="section-title">平台简介</div>
        <el-button @click="saveIntro">保存简介</el-button>
      </div>
      <el-card shadow="never" class="intro-card">
        <el-input v-model="platformIntro" :rows="4" type="textarea" placeholder="请输入平台简介..." />
      </el-card>

      <div class="section-title">功能模块</div>
      <div class="module-grid">
        <el-card v-for="item in moduleBlocks" :key="item.title" shadow="hover" class="module-card">
          <div class="module-icon">{{ item.icon }}</div>
          <div class="module-title">{{ item.title }}</div>
          <div class="module-desc">{{ item.desc }}</div>
        </el-card>
      </div>

      <div class="section-title">平台特性</div>
      <div class="module-grid">
        <el-card v-for="item in featureBlocks" :key="item.title" shadow="hover" class="module-card">
          <div class="module-icon">{{ item.icon }}</div>
          <div class="module-title">{{ item.title }}</div>
          <div class="module-desc">{{ item.desc }}</div>
        </el-card>
      </div>
    </el-main>
  </el-container>

  <el-dialog v-model="showAddDialog" title="添加轮播图" width="500px">
    <el-form label-width="80px">
      <el-form-item label="名称">
        <el-input v-model="newCarousel.name" placeholder="请输入轮播图名称" />
      </el-form-item>
      <el-form-item label="上传图片">
        <el-upload
          class="carousel-uploader"
          :show-file-list="false"
          :on-success="handleUploadSuccess"
          :before-upload="beforeUpload"
          :http-request="handleUpload"
          action="#"
        >
          <img v-if="newCarousel.url" :src="getFullImageUrl(newCarousel.url)" class="carousel-image-preview" />
          <el-icon v-else class="carousel-uploader-icon"><Upload /></el-icon>
        </el-upload>
        <div class="upload-tip">或直接输入图片URL</div>
        <el-input v-model="newCarousel.url" placeholder="请输入图片链接" style="margin-top: 8px;" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showAddDialog = false">取消</el-button>
      <el-button type="primary" @click="addCarouselItem">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { Delete, Upload } from '@element-plus/icons-vue'
import SideNav from '../components/SideNav.vue'
import { uploadFile } from '../api/client'

const router = useRouter()

const INTRO_KEY = 'fc_home_intro'
const CAROUSEL_KEY = 'fc_home_carousel'

// 处理图片 URL
function getFullImageUrl(url) {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) {
    return url
  }
  // 相对路径保持不变，nginx 会处理
  return url
}

const showAddDialog = ref(false)
const newCarousel = ref({ name: '', url: '' })
const uploadLoading = ref(false)

const platformIntro = ref(
  '金融云安全监查平台面向金融行业容器场景，提供可视化监控、安全审计、风险预警与整改建议，支持团队按“监控-分析-修复-留痕”流程持续提升集群安全基线。'
)

const moduleBlocks = ref([
  { icon: '📊', title: '实时监控', desc: '聚合集群与命名空间视角的关键指标，快速识别异常波动。' },
  { icon: '🛡️', title: '安全审计', desc: '扫描高风险配置并输出可追溯清单，便于复核与整改。' },
  { icon: '🧰', title: '修复助手', desc: '根据风险类型生成修复建议，支持标准化变更落地。' }
])

const featureBlocks = ref([
  { icon: '🔔', title: '事件告警', desc: '实时订阅 K8s 事件流，形成告警链路闭环。' },
  { icon: '�', title: '持续巡检', desc: '按周期复核集群安全状态，减少配置漂移带来的风险。' },
  { icon: '�', title: '审计留痕', desc: '结合报告导出能力，为评审与审计提供证据支撑。' }
])

const defaultCarouselImages = [
  { id: 'banner-1', name: '平台概览', url: new URL('../static/qw.png', import.meta.url).href },
  { id: 'banner-2', name: '态势感知', url: new URL('../static/ee.png', import.meta.url).href },
  { id: 'banner-3', name: '治理闭环', url: new URL('../static/we.png', import.meta.url).href }
]

const carouselImages = ref([...defaultCarouselImages])

function logout() {
  localStorage.removeItem('fc_token')
  router.push('/login')
}

function saveIntro() {
  localStorage.setItem(INTRO_KEY, platformIntro.value || '')
  ElMessage.success('平台简介已保存')
}

function saveCarousel() {
  localStorage.setItem(CAROUSEL_KEY, JSON.stringify(carouselImages.value))
}

function deleteCarouselItem(id) {
  ElMessageBox.confirm('确定要删除这个轮播图吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    carouselImages.value = carouselImages.value.filter(img => img.id !== id)
    saveCarousel()
    ElMessage.success('删除成功')
  }).catch(() => {})
}

function beforeUpload(file) {
  const isImage = file.type.startsWith('image/')
  const isLt5M = file.size / 1024 / 1024 < 5
  if (!isImage) {
    ElMessage.error('只允许上传图片文件!')
    return false
  }
  if (!isLt5M) {
    ElMessage.error('图片大小不能超过 5MB!')
    return false
  }
  return true
}

async function handleUpload(options) {
  const { file } = options
  uploadLoading.value = true
  try {
    const res = await uploadFile(file)
    newCarousel.value.url = res.url
    ElMessage.success('上传成功')
  } catch (err) {
    ElMessage.error('上传失败')
    console.error(err)
  } finally {
    uploadLoading.value = false
  }
}

function handleUploadSuccess() {
  // 自定义上传处理，这个函数保留即可
}

function addCarouselItem() {
  if (!newCarousel.value.name || !newCarousel.value.url) {
    ElMessage.warning('请填写完整的轮播图信息')
    return
  }
  const newItem = {
    id: `banner-${Date.now()}`,
    name: newCarousel.value.name,
    url: newCarousel.value.url
  }
  carouselImages.value.push(newItem)
  saveCarousel()
  showAddDialog.value = false
  newCarousel.value = { name: '', url: '' }
  ElMessage.success('添加成功')
}

onMounted(() => {
  const savedIntro = localStorage.getItem(INTRO_KEY)
  if (savedIntro) platformIntro.value = savedIntro
  
  const savedCarousel = localStorage.getItem(CAROUSEL_KEY)
  if (savedCarousel) {
    try {
      carouselImages.value = JSON.parse(savedCarousel)
    } catch (e) {
      carouselImages.value = [...defaultCarouselImages]
    }
  }
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
.page-title {
  font-size: 24px;
  font-weight: 800;
  margin: 4px 0 14px;
}
.welcome-card {
  margin-bottom: 14px;
}
.welcome-card h3 {
  margin: 0 0 8px;
  font-size: 20px;
}
.welcome-card p {
  margin: 0;
  line-height: 1.7;
  color: #5b6470;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 0px 0 10px;
}
.section-title {
  font-size: 16px;
  font-weight: 800;
  margin: 16px 0 10px;
}
.carousel {
  margin-bottom: 0;
  border-radius: 12px;
  overflow: hidden;
}
.carousel :deep(.el-carousel__container) {
  aspect-ratio: 16 / 9;
  height: auto !important;
}
.carousel-item {
  position: relative;
  height: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: hidden;
  background: #f0f2f5;
}
.carousel-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
}
.carousel-delete {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 32px;
  height: 32px;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  cursor: pointer;
  transition: all 0.3s;
  z-index: 10;
}
.carousel-delete:hover {
  background: rgba(239, 68, 68, 0.9);
  transform: scale(1.1);
}
.intro-card {
  margin-bottom: 12px;
}
.module-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.module-card {
  border: 1px solid #e5e7eb;
}
.module-icon {
  font-size: 24px;
  margin-bottom: 8px;
}
.module-title {
  font-weight: 700;
  margin-bottom: 8px;
}
.module-desc {
  color: #5b6470;
  line-height: 1.6;
}
@media (max-width: 1000px) {
  .module-grid {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 720px) {
  .module-grid {
    grid-template-columns: 1fr;
  }
}
.carousel-uploader {
  width: 100%;
}
.carousel-uploader :deep(.el-upload) {
  width: 100%;
}
.carousel-uploader :deep(.el-upload-dragger) {
  width: 100%;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.carousel-image-preview {
  width: 100%;
  height: 200px;
  object-fit: cover;
  border-radius: 6px;
}
.carousel-uploader-icon {
  font-size: 40px;
  color: #8c939d;
}
.upload-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
  text-align: center;
}
</style>
