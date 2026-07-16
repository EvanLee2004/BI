# 甲骨易智能经营罗盘 · Windows 从零部署手册

> **状态：legacy（2026-07-16 起）**  
> 主部署线已迁 **Ubuntu 22.04**，见 `docs/Ubuntu部署手册.md`。本手册与根目录 `*.bat` / schtasks **保留不删**，作 Windows 回退保险。  
>
> **适用**：部署机旧程序已清空，在 **Windows · D 盘** 全新安装后上线。  
> **产品目录约定**：`D:\看板\看板正式程序\`（路径勿含空格；示例一律 `D:\…`）。  
> **形态**：FastAPI 同端口双端（用户 `/` + 管理 `/admin`）+ 看门狗常驻 + 计划任务定时更新 + 智云/台账抓数。  
> **修订**：2026-07-16 任务书36（从零 checklist 重写；审计见 `docs/20260716_任务书36交付报告.md`）；任务书40 标 legacy。

---

## 0. 你需要准备什么

| 项 | 说明 |
|----|------|
| 机器 | 财务部 Windows，内网，建议常开 |
| 权限 | 本机管理员（装 Python/Git、注册计划任务、开防火墙） |
| 账号 | 智云**全量只读**号（非个人「我的任务」号）；看板管理员口令 |
| 网络 | 能访问智云内网、收单台账共享盘 `\\192.168.10.151\…`、Gitee（或 GitHub） |
| 代码 | **git clone**（一键更新才可用）；勿只拷文件夹长期用 |

---

## 1. 装 Python（管理员 · 约 10 分钟 · 需联网）

1. 打开 https://www.python.org/downloads/ 下载 **Python 3.10+**（推荐 3.12）。
2. 安装时**务必勾选** `Add python.exe to PATH`。
3. 新开 **cmd** 验证：

```bat
python --version
```

应显示 3.10 及以上。

---

## 2. 装 Git 并 clone 到 D 盘（推荐 Gitee）

1. 安装 Git：https://git-scm.com/  
2. 在 cmd：

```bat
mkdir D:\看板
cd /d D:\看板
git clone https://gitee.com/Lee157/oracleeasy--bi.git 看板正式程序
cd /d D:\看板\看板正式程序
```

- 公开库 clone **免密**。`origin` = Gitee → 管理端一键更新默认对标 Gitee。  
- **不要**从 Mac 拷 `.venv`（跨系统无效，有则删掉重建）。  
- 真实业务数据**不要**指望从公开库带出；clone 后按第 4 节放 `数据\`。

若必须从 GitHub clone、更新想走 Gitee：

```bat
cd /d D:\看板\看板正式程序
git remote add gitee https://gitee.com/Lee157/oracleeasy--bi.git
```

然后在 `D:\看板\看板正式程序\数据\本地配置.json` 写（**不要改 config.json**）：

```json
{"update_remote": "gitee"}
```

---

## 3. 建虚拟环境 + 装依赖（清华镜像）

在 **`D:\看板\看板正式程序\`** 打开 cmd：

```bat
cd /d D:\看板\看板正式程序
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv\Scripts\pip install playwright -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv\Scripts\playwright install chromium
```

最后一步下载无头浏览器（约 150MB，智云自动登录用），**必须做**。

---

## 4. 数据目录从零清单（`D:\看板\看板正式程序\数据\`）

`数据\` 在 git 里通常只有 `README.md`。下列文件按场景放置；**缺关键源时**管道/体检会黄或红，但**空库起服务应能开管理端引导页、不崩**。

| 文件 | 必须？ | 来源 / 说明 |
|------|--------|-------------|
| `收单台账.xlsx` | 首次取数后应有 | 共享盘自动拉；或手工放一份。**须含当年 sheet 名**（如 `2026`/`2027`），缺 sheet 会报错指路「请建 yyyy sheet」，**不会静默算 0** |
| `下单.xlsx` `回款记录.xlsx` `项目明细.xlsx` `内部译员.xlsx` | 首次取数后应有 | 智云在线抓覆盖；失败则 `local_fallback`+体检黄 |
| `手填与调整.xlsx` | 建议有 | 无则手填按 0 + 警告 |
| `看板账号.json` | 可缺 | 缺则服务 **seed** 默认（管理员 `lushasha` / 初始口令见样例；查看号初始 `8888`）。样例：`docs\看板账号样例.json` |
| `智云配置.json` | 可缺 | 连接默认已内置；**账号密码**在管理端设置页填后写入本文件（`md_pss_id` 可留空，登录后自动写） |
| `BU配置.json` | 建议有 | 管理端「BU 数据归属」维护；样例 `docs\BU配置样例.json` |
| `本地配置.json` | 可缺 | 机器专属：台账路径、更新时间、备份天数、`update_remote` 等。**程序只写这里，绝不写脏 config.json** |
| `管理员密钥.json` | 可缺 | 首次启动自动生成 cookie 签名密钥 |
| `看板.db` | 可缺 | 首次更新后生成 |

⚠ **铁律**：`config.json` 是出厂默认、git 追踪——**部署机永远不要手改**。台账路径/时间点一律设置页或 `本地配置.json`。

---

## 5. 起服务（先空跑通）

```bat
cd /d D:\看板\看板正式程序
看门狗启动.bat
```

或资源管理器双击 `D:\看板\看板正式程序\看门狗启动.bat`。

- 用户端：`http://本机IP:8018/`  
- 管理端：`http://本机IP:8018/admin`  
- 空数据时管理员登录应进入**引导页**（填智云账号 → 保存 → 立即更新），不是死报错页。

普通启动（无自动重启）：`启动看板服务.bat`。生产请用**看门狗**。

---

## 6. 防火墙放行 8018（管理员）

右键 **`开启内网访问.bat`** → **以管理员身份运行**（内部 `netsh advfirewall` 放行 TCP 8018）。

或手工：

```bat
netsh advfirewall firewall add rule name="甲骨易经营罗盘-8018" dir=in action=allow protocol=TCP localport=8018 profile=private,domain
```

---

## 7. 管理端：智云账号 + 台账路径 + 首次取数

1. 浏览器打开 `http://127.0.0.1:8018/admin`  
2. 登录：`lushasha` + 初始密码（见 `docs\看板账号样例.json` / 部署交接；**上线前必改**）  
3. **设置 → 智云账号**：填**全量只读**账号密码并保存  
4. **台账路径**：核对默认共享盘路径；不对就在设置页改（写入 `数据\本地配置.json`）  
5. 顶栏 **「立即更新」**，等 2～3 分钟：台账 + 智云三源宜 `fetched`；内部译员权限不足时黄灯降级属已知  
6. 打开用户端核对页面有数

命令行等价更新（排障）：

```bat
cd /d D:\看板\看板正式程序
.venv\Scripts\python.exe run.py
```

---

## 8. 注册每日自动更新（管理员）

右键 **`注册每日更新.bat`** → **以管理员身份运行**。

- 读取**合并配置**（`config.json` + `数据\本地配置.json`）里的 `schedule_times`  
- 每个时间点一个计划任务：主名 `经营驾驶舱每日更新` + `_2`…  
- 查询：

```bat
schtasks /Query /TN "经营驾驶舱每日更新"
```

之后改时间点：管理端「设置 → 自动更新」保存；若同步失败，再管理员重跑本 bat。

---

## 9. 开机自启看门狗

1. `Win+R` → 输入 `shell:startup` → 回车  
2. 把 **`D:\看板\看板正式程序\看门狗启动.bat`** 的**快捷方式**放进该文件夹  
3. 重启验证服务自动起来  

（计划任务 `/SC ONSTART` 也可，但 startup 快捷方式足够且好卸。）

---

## 10. 三账号验收清单

| 账号类型 | 期望 |
|----------|------|
| 管理员 `lushasha` | 进 `/admin`；改手填/设置/立即更新 |
| 整体权限 | `/` 整体页 + BU 入口条；无管理写接口 |
| BU / 多 BU | 只见绑定 BU；顶栏切换条**不列他 BU**；全公司 API 401 |

错密 401；改密后旧会话失效策略以现网为准。手机同 WiFi 打开用户端扫一眼。

---

## 11. 回滚方法

**代码坏版本（一键更新后启动即崩）**  
看门狗若见 `.update_rollback` 会自动 `git reset --hard` 回滚一次。手工：

```bat
cd /d D:\看板\看板正式程序
git log --oneline -5
git reset --hard <已知好的commit>
看门狗启动.bat
```

**数据库**  
`数据\备份\看板_YYYYMMDD.db` 拷回 `数据\看板.db`（先停服务；当前库另存 `看板.db.pre-restore`）。

**装依赖失败**  
一键更新会自动回滚本次 pull；也可：

```bat
cd /d D:\看板\看板正式程序
git reset --hard HEAD
.venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 12. 上线前安全 checklist（必做）

- [ ] **改掉所有初始密码**（管理员 + 所有查看号）；勿复用个人常用密码（管理员可见看板明文口令）  
- [ ] 智云抓数账号 = **全量只读**号（勿用仅「我的任务」权限号，否则内部译员行数门槛会降级）  
- [ ] `config.json` 的 `git status` 干净（无本地脏改）  
- [ ] 看门狗在跑；计划任务已注册；防火墙 8018 已放行  
- [ ] 三账号分流与一次「立即更新」成功  
- [ ] （建议）恢复演练：用昨日备份拷回测一次  

---

## 13. 脚本一览（均在 `D:\看板\看板正式程序\`）

| 脚本 | 权限 | 作用 |
|------|------|------|
| `看门狗启动.bat` | 普通 | 常驻 serve；码 42 更新重启；坏版本回滚一次 |
| `启动看板服务.bat` | 普通 | 单次 serve，无看门狗 |
| `更新看板.bat` | 普通 | 跑一次 `run.py`（优先 `.venv`） |
| `注册每日更新.bat` | **管理员** | 注册/覆盖 `schedule_times` 计划任务 |
| `开启内网访问.bat` | **管理员** | 防火墙放行 8018 |

编码：含中文 bat 均为 UTF-8 + 首行附近 `chcp 65001`，在现代 Windows cmd 下使用。  
`findstr` 仅匹配英文 `IPv4`（避免历史中文编码误报）。

---

## 14. 附：数据库与备份（运维摘要）

- 连接 **WAL + busy_timeout**；金额库内**整数分**，页面显示不变。  
- 每日备份：`数据\备份\`；保留天数设置页可改。  
- 详细恢复步骤见交付报告 / 任务书33 章节；`ingest.archive.restore_db_from_backup` 有单测覆盖。

---

## 15. 部署机复验（Windows 特有 · 开发机代不了）

- [ ] 首次取数：共享盘 + 智云 fetched  
- [ ] Playwright 在 serve 进程内登录智云一次成功  
- [ ] `schtasks` 次日真跑  
- [ ] 一键更新：pull →（可选 pip）→ 码 42 → 看门狗拉起  
- [ ] 手机打开用户端  

完成以上即视为 **D 盘从零部署可上线**。
