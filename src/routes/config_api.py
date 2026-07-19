"""BU 配置/设置/版本更新 — 从 server.create_app 纯搬家。"""

from __future__ import annotations


from fastapi import Body, HTTPException, Query, Request, Response

import bu
import core
import db
import loaders
import updater
import version as product_version


def register(app, d):  # noqa: C901  # 路由表注册壳，复杂度在子 handler
    cfg = d.cfg
    root = d.root
    _user = d.user
    _vacct = d.vacct
    _vacc_row = d.vacc_row
    _can_view_main = d.can_view_main
    _can_view_bu = d.can_view_bu
    _bu_switcher_html = d.bu_switcher_html
    _set_vcookie = d.set_vcookie
    _set_acookie = d.set_acookie
    _main_shell = d.main_shell
    _bu_shell = d.bu_shell
    _view_login_file = d.view_login_file
    _admin_login_file = d.admin_login_file
    _admin_static_html = d.admin_static_html
    _bootstrap_page = d.bootstrap_page
    _manual_items_json = d.manual_items_json
    _html_doc = d.html_doc
    _file_html_doc = d.file_html_doc
    _audit = d.audit
    _diff_accounts = d.diff_accounts
    _diff_bu_config = d.diff_bu_config
    _run_reasons = d.run_reasons

    def start_refresh_async(cfg, root=None, trigger="manual"):
        import server as _srv

        return _srv.start_refresh_async(cfg, root, trigger)

    def recompute(cfg, root=None):
        import server as _srv

        return _srv.recompute(cfg, root)

    get_schedule_times = d.get_schedule_times
    save_settings = d.save_settings
    read_zhiyun_creds = d.read_zhiyun_creds
    read_zhiyun_conn = d.read_zhiyun_conn
    _screenshot_png = d.screenshot_png
    _HIDE_PW_STYLE = d.HIDE_PW_STYLE
    _WRAP_OPEN = d.WRAP_OPEN
    EDITABLE_SETTINGS = d.EDITABLE_SETTINGS

    def _require(request: Request) -> str:
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return user

    def _conn():
        return db.connect(cfg, root)

    @app.get("/api/bu_config")
    def api_bu_config_get(request: Request):
        """BU 配置（管理员会话）：BU 清单/负责人/销售名单/分摊比例 + 分摊总开关。"""
        _require(request)
        bucfg = bu.load_bu_config(cfg, root) or {"bus": [], "公共费用分摊启用": False}
        return {
            "bus": bucfg["bus"],
            "count": len(bucfg["bus"]),
            "公共费用分摊启用": bool(bucfg.get("公共费用分摊启用")),
        }

    @app.get("/api/sales_pool")
    def api_sales_pool(request: Request):
        """四源销售池（管理员·A1 归属页）：供批量/拖拽归属。含配置里有、库里暂无的名字（rows=0）。
        每人带当年下单笔数+金额参考串（服务端算好=铁律2）；顶层带 A3 未归属计数+当年未归属下单额。"""
        _require(request)
        today = loaders.pinned_today(cfg)
        conn = db.connect(cfg, root)
        try:
            from_db = db.list_salespeople(conn)
            ostats = db.order_stats_by_sales(conn, today.year)
            snap = core.unassigned_snapshot(cfg, conn, today, root)
        finally:
            conn.close()
        by = {x["name"]: x["rows"] for x in from_db}
        bucfg = bu.load_bu_config(cfg, root) or {"bus": []}
        for b in bucfg.get("bus", []):
            for s in b.get("销售") or []:
                s = str(s).strip()
                if s and s not in by:
                    by[s] = 0

        def _ref(name):
            st = ostats.get(name)
            if not st or not st["count"]:
                return {"orders_count": 0, "ref_disp": "当年无下单"}
            return {
                "orders_count": st["count"],
                "ref_disp": f"{st['count']} 笔 · {core._unassigned_wan(st['amount'])[1:]}",
            }

        people = [{"name": n, "rows": by[n], **_ref(n)} for n in sorted(by.keys(), key=lambda k: (-by[k], k))]
        return {"sales": people, "count": len(people), **snap}

    @app.post("/api/bu_config")
    def api_bu_config_post(request: Request, payload: dict = Body(default={})):
        """保存 BU 数据归属 + 公共费用分摊，并立即重算重渲染 BU 页（一人一 BU）。C3：变更留痕。"""
        user = _require(request)
        bus = payload.get("bus")
        if not isinstance(bus, list):
            raise HTTPException(status_code=400, detail="bus 须为列表")
        if len(bus) > 20:
            raise HTTPException(status_code=400, detail="BU 数量过多（上限 20）")
        old = bu.load_bu_config(cfg, root) or {"bus": [], "公共费用分摊启用": False}
        old_bus, old_alloc = old["bus"], bool(old.get("公共费用分摊启用"))
        new_alloc = bool(payload.get("公共费用分摊启用", False))
        try:
            saved = bu.save_bu_config(cfg, root, bus, 公共费用分摊启用=new_alloc)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        recompute(cfg, root)
        _audit(cfg, root, user, _diff_bu_config(old_bus, saved["bus"], old_alloc, bool(saved.get("公共费用分摊启用"))))
        return {
            "bus": saved["bus"],
            "count": len(saved["bus"]),
            "公共费用分摊启用": bool(saved.get("公共费用分摊启用")),
            "note": "已保存并重算",
        }

    @app.get("/api/config_changes")
    def api_config_changes(request: Request, category: str | None = None, limit: int = 200):
        """C3 操作记录（管理员）：配置变更留痕倒序，可按类别筛。仅摘要，无密码明文。"""
        _require(request)
        conn = db.connect(cfg, root)
        try:
            return {
                "changes": db.list_config_changes(conn, category or None, limit),
                "categories": list(db.CONFIG_CHANGE_CATEGORIES),
            }
        finally:
            conn.close()

    @app.get("/api/version")
    def api_version(request: Request):
        """产品版本号 + 面向用户的更新日志（管理员会话）。
        版本号=根目录 VERSION（现 1.0-beta 公测 Beta），与 git 开发号(v8.x)分开、不给普通用户看。"""
        _require(request)
        return product_version.version_info()

    @app.get("/api/update/check")
    def api_update_check(request: Request):
        """④ 检测远端有没有新版本（管理员会话）：git fetch + 比对 HEAD 与 <update_remote>/分支。
        对标的远端由 config `update_remote` 决定（默认 origin；部署机从 Gitee clone 则 origin 即 Gitee）。
        只读、带护栏（非仓库/分叉/脏工作区不给更新），返回是否有新版本与"要更新啥"。"""
        _require(request)
        return updater.check_update(loaders.ROOT, remote=cfg.get("update_remote") or "origin")

    @app.post("/api/update/apply")
    def api_update_apply(request: Request):
        """④ 一键更新（管理员会话）：复检护栏 → git pull --ff-only <update_remote> → 触发看门狗重启。
        拉取成功才重启（进程以退出码 42 退出，看门狗用新代码拉起）；失败原样返回不重启。"""
        user = _require(request)
        res = updater.apply_update(loaders.ROOT, remote=cfg.get("update_remote") or "origin")
        if res.get("ok"):
            _audit(
                cfg,
                root,
                user,
                (
                    "更新",
                    f"一键更新 {res.get('from') or '?'}→{res.get('to') or '?'}（{res.get('pulled') or 0} 个提交）",
                ),
            )
            updater.request_restart()  # 后台延时退出→看门狗重启；HTTP 响应先发回
            res["restarting"] = True
        return res

    @app.get("/api/settings")
    def api_settings_get(request: Request):
        _require(request)
        out = {k: cfg.get(k) for k in EDITABLE_SETTINGS}
        out["schedule_times"] = get_schedule_times(cfg)  # ②多次更新：列表（缺失从旧单值推导）
        creds = read_zhiyun_creds(cfg, root)
        out["zhiyun_username"], out["zhiyun_password"] = creds["username"], creds["password"]
        out["zhiyun_conn"] = read_zhiyun_conn(cfg, root)  # 服务器地址+四表ID（内置默认+本地覆盖的生效值）
        out["ledger_share_path"] = cfg.get("ledger_share_path", "")  # 收单台账共享盘路径（界面填·落本地覆盖）
        out["overall_see_salary"] = False  # 54.12 R-01 已废止开关
        out["feishu_webhook_url"] = cfg.get("feishu_webhook_url", "") or ""  # 任务书43 告警
        out["run_log_keep_days"] = int(cfg.get("run_log_keep_days", 365) or 365)
        out["disk_free_min_ratio"] = float(cfg.get("disk_free_min_ratio", 0.10) or 0.10)
        bdir = loaders.data_dir(cfg, root) / "备份"
        baks = (sorted(bdir.glob("看板_*.db")) + sorted(bdir.glob("页面_*.html"))) if bdir.exists() else []
        out["backup_stats"] = {"count": len(baks), "mb": round(sum(p.stat().st_size for p in baks) / 1048576, 1)}
        return out

    @app.post("/api/settings")
    def api_settings_post(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        old_times = get_schedule_times(cfg)
        old_keep = cfg.get("backup_keep_days")
        old_lsp = cfg.get("ledger_share_path")
        try:
            res = save_settings(cfg, root, payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        chg = []  # C3：设置变更留痕（智云账号只记「已更换」不记值）
        if ("schedule_times" in payload or "schedule_time" in payload) and res["schedule_times"] != old_times:
            chg.append(f"更新时间 {'、'.join(old_times) or '—'}→{'、'.join(res['schedule_times'])}")
        if "backup_keep_days" in payload and res["backup_keep_days"] != old_keep:
            chg.append(f"备份保留 {old_keep}→{res['backup_keep_days']} 天")
        if "智云账号已更新" in (res.get("note") or ""):
            chg.append("智云账号已更换")
        if "智云连接配置已更新" in (res.get("note") or ""):
            chg.append("智云连接配置已更改（服务器/表ID）")
        # 台账路径含内网服务器名（敏感）→ 只记「已更改」不落值（铁律16）
        if (
            "ledger_share_path" in payload
            and str(payload.get("ledger_share_path") or "").strip() != str(old_lsp or "").strip()
        ):
            chg.append("收单台账共享盘路径已更改")
        # 54.12 R-01：overall_see_salary 已废止，忽略 payload 中的该字段
        if "feishu_webhook_url" in payload:
            # webhook 含密钥，只记「已更改」
            chg.append("飞书告警 webhook 已更改")
        if chg:
            _audit(cfg, root, user, ("设置", "设置：" + "；".join(chg)))
        return res

    @app.get("/api/archive_export")
    def api_archive_export(request: Request, year: str = Query("")):
        """审计流水年度导出归档（手填历史/预算历史/配置变更）→ xlsx；不删库内数据。管理员。"""
        _require(request)
        y = (year or "").strip() or str(__import__("datetime").date.today().year)
        import db_write
        from urllib.parse import quote

        conn = db.connect(cfg, root)
        try:
            raw = db_write.export_audit_archive_xlsx(conn, y)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            conn.close()
        fname = f"审计归档_{y}.xlsx"
        cd = f"attachment; filename=\"archive.xlsx\"; filename*=UTF-8''{quote(fname)}"
        return Response(
            content=raw,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": cd},
        )
