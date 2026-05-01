import { createRouter, createWebHistory } from 'vue-router'

import Login from '../views/Login.vue'
import Home from '../views/Home.vue'
import Dashboard from '../views/Dashboard.vue'
import MonitorBoard from '../views/MonitorBoard.vue'
import Audit from '../views/Audit.vue'
import Events from '../views/Events.vue'
import Resources from '../views/Resources.vue'
import AdvancedScan from '../views/AdvancedScan.vue'
import SupplyChain from '../views/SupplyChain.vue'
import FixAssistant from '../views/FixAssistant.vue'
import ReportExport from '../views/ReportExport.vue'
import Account from '../views/Account.vue'
import Users from '../views/Users.vue'
import Clusters from '../views/Clusters.vue'

function hasToken() {
  return !!localStorage.getItem('fc_token')
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/login', component: Login, meta: { public: true } },
    { path: '/home', component: Home },
    { path: '/dashboard', component: Dashboard },
    { path: '/monitor/board', component: MonitorBoard },
    { path: '/audit', component: Audit },
    { path: '/resources', component: Resources },
    { path: '/security/advanced', component: AdvancedScan },
    { path: '/security/supply', component: SupplyChain },
    { path: '/tools/fix', component: FixAssistant },
    { path: '/tools/report', component: ReportExport },
    { path: '/account', component: Account },
    { path: '/users', component: Users },
    { path: '/clusters', component: Clusters },
    { path: '/events', component: Events },
    { path: '/tools', redirect: '/tools/fix' }
  ]
})

router.beforeEach((to) => {
  const isPublic = to.meta?.public
  if (isPublic) return true
  if (!hasToken()) return { path: '/login' }
  if (to.path === '/users' && localStorage.getItem('fc_role') !== 'admin') {
    return { path: '/home' }
  }
  return true
})

export default router

