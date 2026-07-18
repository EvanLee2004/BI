/**
 * 双入口：/admin* → 管理端 Vue（动态加载 Element Plus）
 * 其余 → 看端驾驶舱（零 Element Plus 污染包体）
 */
const path = location.pathname

if (path === '/admin' || path.startsWith('/admin/')) {
  import('./admin/bootstrap').then((m) => m.bootAdmin())
} else {
  import('./boot-cockpit').then((m) => m.bootCockpit())
}
