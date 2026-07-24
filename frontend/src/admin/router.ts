import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { fetchSession } from './api'

/** 2.5.0：无独立管理员登录页；未登录整页跳统一 /login?next= */
function goUnifiedLogin(nextPath: string) {
  const n = nextPath && nextPath.startsWith('/') ? nextPath : '/admin'
  location.replace('/login?next=' + encodeURIComponent(n))
}

const routes: RouteRecordRaw[] = [
  {
    path: '/admin/login',
    name: 'admin-login-compat',
    // 兼容：组件不加载，进守卫前 beforeEach 会 replace 到 /login
    redirect: () => {
      goUnifiedLogin('/admin')
      return '/admin'
    },
    meta: { public: true },
  },
  {
    path: '/admin',
    component: () => import('./layout/AdminLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'admin-console', component: () => import('./views/ConsoleView.vue'), meta: { group: 'see', title: '控制台' } },
      { path: 'edit/detail', name: 'admin-detail', component: () => import('./views/DetailView.vue'), meta: { group: 'edit', title: '数据调整' } },
      { path: 'edit/manual', name: 'admin-manual', component: () => import('./views/ManualView.vue'), meta: { group: 'edit', title: '人工填写' } },
      { path: 'edit/budget', name: 'admin-budget', component: () => import('./views/BudgetView.vue'), meta: { group: 'edit', title: '业绩目标' } },
      { path: 'review/overview', name: 'admin-overview', component: () => import('./views/ExceptionOverview.vue'), meta: { group: 'review', title: '异常总览' } },
      { path: 'review/ledger', name: 'admin-ledger', component: () => import('./views/LedgerView.vue'), meta: { group: 'review', title: '数据修正' } },
      { path: 'review/orderdept', name: 'admin-orderdept', component: () => import('./views/OrderDeptView.vue'), meta: { group: 'review', title: '下单未填部门' } },
      { path: 'review/unclassified', name: 'admin-unclassified', component: () => import('./views/UnclassifiedView.vue'), meta: { group: 'review', title: '费用未分类' } },
      { path: 'review/history', name: 'admin-history', component: () => import('./views/HistoryView.vue'), meta: { group: 'review', title: '历史快照' } },
      { path: 'review/audit', name: 'admin-audit', component: () => import('./views/AuditView.vue'), meta: { group: 'review', title: '配置变更记录' } },
      { path: 'settings', name: 'admin-settings', component: () => import('./views/SettingsView.vue'), meta: { group: 'cfg', title: '设置' } },
    ],
  },
  { path: '/admin/:pathMatch(.*)*', redirect: '/admin' },
]

export const adminRouter = createRouter({
  history: createWebHistory('/'),
  routes,
})

adminRouter.beforeEach(async (to) => {
  // 书签 /admin/login → 统一登录（后端也会 303；双保险）
  if (to.path === '/admin/login' || to.name === 'admin-login-compat') {
    goUnifiedLogin('/admin')
    return false
  }
  if (!to.path.startsWith('/admin')) return true
  try {
    const sess = (await fetchSession()) as { is_admin?: boolean; perm?: string }
    if (sess.is_admin || sess.perm === '管理员') return true
    // 有会话但非管理员 → 统一登录（不可进管理端）
    goUnifiedLogin('/admin')
    return false
  } catch {
    goUnifiedLogin(to.fullPath.startsWith('/admin') ? to.fullPath : '/admin')
    return false
  }
})
