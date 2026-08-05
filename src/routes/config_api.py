"""BU 配置/设置/版本更新 — 从 server.create_app 纯搬家。"""

from __future__ import annotations


from fastapi import Body, HTTPException, Query, Request, Response

import bu
import core
import db
import loaders
import updater
import version as product_version


def register(app, d):  # noqa: C901  # 纯路由/装配分发壳，复杂度在子 handler
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
    _bootstrap_page = d.bootstrap_page
    _manual_items_json = d.manual_items_json
    _html_doc = d.html_doc
    _file_html_doc = d.file_html_doc
    _audit = d.audit
    _diff_accounts = d.diff_accounts
    _diff_bu_config = d.diff_bu_config
    _run_reasons = d.run_reasons

    from routes._srv import recompute  # 任务书64·D9 共享 helper


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

    @app.get("/api/v1/admin/bu_config")
    def api_bu_config_get(request: Request):
        """BU 配置（管理员会话）：BU 清单/负责人/销售名单/分摊比例 + 分摊总开关。"""
        _require(request)
        bucfg = bu.load_bu_config(cfg, root) or {"bus": [], "公共费用分摊启用": False}
        return {
            "bus": bucfg["bus"],
            "count": len(bucfg["bus"]),
            "公共费用分摊启用": bool(bucfg.get("公共费用分摊启用")),
        }

    @app.get("/api/v1/admin/sales_pool")
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

    @app.post("/api/v1/admin/bu_config")
    def api_bu_config_post(request: Request, payload: dict = Body(default={})):
        """保存 BU 数据归属 + 公共费用分摊，并立即重算重渲染 BU 页（一人一 BU）。C3：变更留痕。

        2.6.7 C-5：与铁律 8 对齐——刷新进行中返回 409 非阻塞等待。
        """
        user = _require(request)
        import accounts as _acc_mod
        import authz as _az

        _az.require_cap(_acc_mod.find_account(cfg, root, user), _az.CAP_DATA_WRITE)
        bus = payload.get("bus")
        if not isinstance(bus, list):
            raise HTTPException(status_code=400, detail="bus 须为列表")
        if len(bus) > 20:
            raise HTTPException(status_code=400, detail="BU 数量过多（上限 20）")
        old = bu.load_bu_config(cfg, root) or {"bus": [], "公共费用分摊启用": False}
        old_bus, old_alloc = old["bus"], bool(old.get("公共费用分摊启用"))
        new_alloc = bool(payload.get("公共费用分摊启用", False))
        # BE-003：先抢锁再落盘，避免 409 时「文件新、页面旧」
        from app_state import _LOCK, _state

        if _state.get("refreshing") or not _LOCK.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="更新进行中，请稍后再保存 BU 配置",
            )
        try:
            try:
                saved = bu.save_bu_config(cfg, root, bus, 公共费用分摊启用=new_alloc)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            # 3.7.8 P0：已持 _LOCK，必须 already_locked=True，否则二次抢锁死锁
            recompute(cfg, root, already_locked=True)
        finally:
            _LOCK.release()
        _audit(cfg, root, user, _diff_bu_config(old_bus, saved["bus"], old_alloc, bool(saved.get("公共费用分摊启用"))))
        return {
            "bus": saved["bus"],
            "count": len(saved["bus"]),
            "公共费用分摊启用": bool(saved.get("公共费用分摊启用")),
            "note": "已保存并重算",
        }

    @app.get("/api/v1/admin/config_changes")
    def api_config_changes(request: Request, category: str | None = None, limit: int = 200):
        """C3 操作记录（管理员）：配置变更留痕倒序，可按类别筛。仅摘要，无密码明文。

        3.3.0：无 category 时默认排除访问类（访问见用户统计）；?category=访问 仍可查。
        """
        _require(request)
        conn = db.connect(cfg, root)
        try:
            return {
                "changes": db.list_config_changes(conn, category or None, limit),
                "categories": list(db.CONFIG_CHANGE_CATEGORIES),
                "excluded_access_by_default": not bool(category),
            }
        finally:
            conn.close()

    @app.get("/api/v1/version")
    def api_version(request: Request):
        """产品版本号 + 更新日志（2.2.5：展示端/管理端任一登录会话可读；非敏感）。
        版本号=根目录 VERSION，与 git 开发号分开。"""
        if not (_user(request) or _vacct(request)):
            raise HTTPException(status_code=401, detail="未登录")
        return product_version.version_info()

    @app.get("/api/v1/update/check")
    def api_update_check(request: Request):
        """④ 检测远端有没有新版本（管理员会话）：git fetch + 比对 HEAD 与 <update_remote>/分支。
        对标的远端由 config `update_remote` 决定（默认 origin；部署机从 Gitee clone 则 origin 即 Gitee）。
        只读、带护栏（非仓库/分叉/脏工作区不给更新），返回是否有新版本与"要更新啥"。"""
        _require(request)
        return updater.check_update(loaders.ROOT, remote=cfg.get("update_remote") or "origin")

    @app.post("/api/v1/admin/update/apply")
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
            # 2.7.3：先亮维护页再重启；pull 失败不进此分支（禁止 turn_on）
            try:
                import maintenance_mode

                maintenance_mode.turn_on("update", cfg, root)
            except Exception:
                pass
            updater.request_restart()  # 后台延时退出→看门狗重启；HTTP 响应先发回
            res["restarting"] = True
        return res

    @app.get("/api/v1/admin/settings")
    def api_settings_get(request: Request):
        """3.7.5：智云密码绝不下发；仅 zhiyun_password_set 非秘密状态。"""
        _require(request)
        out = {k: cfg.get(k) for k in EDITABLE_SETTINGS}
        out["schedule_times"] = get_schedule_times(cfg)  # ②多次更新：列表（缺失从旧单值推导）
        creds = read_zhiyun_creds(cfg, root)
        out["zhiyun_username"] = creds.get("username") or ""
        # 3.7.5 P0：不下发 zhiyun_password / 任何可逆等价值
        out["zhiyun_password_set"] = bool(str(creds.get("password") or "").strip())
        out["zhiyun_conn"] = read_zhiyun_conn(cfg, root)  # 服务器地址+四表ID（内置默认+本地覆盖的生效值）
        out["ledger_share_path"] = cfg.get("ledger_share_path", "")  # 收单台账共享盘路径（界面填·落本地覆盖）
        # 3.7.15 B：结构化 CIFS 字段 + 探测；密码永不下发
        import ledger_cifs as _lc

        out.update(_lc.settings_public_view(cfg))
        out["overall_see_salary"] = False  # 54.12 R-01 已废止开关
        out["run_log_keep_days"] = int(cfg.get("run_log_keep_days", 365) or 365)
        out["disk_free_min_ratio"] = float(cfg.get("disk_free_min_ratio", 0.10) or 0.10)
        bdir = loaders.data_dir(cfg, root) / "备份"
        baks = (
            sorted(bdir.glob("看板_*.db")) + sorted(bdir.glob("vm_*.json")) + sorted(bdir.glob("页面_*.html"))
        ) if bdir.exists() else []
        out["backup_stats"] = {"count": len(baks), "mb": round(sum(p.stat().st_size for p in baks) / 1048576, 1)}
        return out

    def _settings_audit_changes(
        payload: dict,
        res: dict,
        *,
        old_times: list,
        old_keep,
        old_lsp,
        old_smb_server,
    ) -> list[str]:
        """设置变更审计条目（脱敏：无密码/完整 UNC）。"""
        chg: list[str] = []
        if ("schedule_times" in payload or "schedule_time" in payload) and res["schedule_times"] != old_times:
            chg.append(f"更新时间 {'、'.join(old_times) or '—'}→{'、'.join(res['schedule_times'])}")
        if "backup_keep_days" in payload and res["backup_keep_days"] != old_keep:
            chg.append(f"备份保留 {old_keep}→{res['backup_keep_days']} 天")
        note = res.get("note") or ""
        if "智云账号已更新" in note:
            chg.append("智云账号已更换")
        if "智云连接配置已更新" in note:
            chg.append("智云连接配置已更改（服务器/表ID）")
        smb_keys = (
            "ledger_share_path",
            "ledger_smb_server",
            "ledger_smb_share",
            "ledger_smb_relpath",
            "ledger_smb_username",
            "ledger_mount_root",
        )
        if any(k in payload for k in smb_keys):
            if str(res.get("ledger_share_path") or "") != str(old_lsp or ""):
                chg.append("收单台账共享盘路径已更改")
            elif str(payload.get("ledger_smb_server") or "") and str(
                payload.get("ledger_smb_server") or ""
            ) != str(old_smb_server or ""):
                chg.append("台账共享服务器已更改")
            else:
                chg.append("台账共享配置已更改")
        if "ledger_smb_password" in payload and str(payload.get("ledger_smb_password") or "") != "":
            chg.append("台账共享凭据已更新")
        elif "ledger_smb_username" in payload and "台账共享凭据已更新" in note:
            chg.append("台账共享凭据已更新")
        return chg

    @app.post("/api/v1/admin/settings")
    def api_settings_post(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        # BE-004：刷新中拒写设置，避免 schedule/备份配置与管道竞态
        from app_state import _state

        if _state.get("refreshing"):
            raise HTTPException(status_code=409, detail="更新进行中，请稍后再保存设置")
        old_times = get_schedule_times(cfg)
        old_keep = cfg.get("backup_keep_days")
        old_lsp = cfg.get("ledger_share_path")
        old_smb_server = cfg.get("ledger_smb_server")
        try:
            res = save_settings(cfg, root, payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        chg = _settings_audit_changes(
            payload,
            res,
            old_times=old_times,
            old_keep=old_keep,
            old_lsp=old_lsp,
            old_smb_server=old_smb_server,
        )
        if chg:
            msg = "设置：" + "；".join(chg)
            if "password" in msg.lower():
                msg = "设置：台账/系统配置已更改"
            _audit(cfg, root, user, ("设置", msg))
        return res

    # 2.6.7 B-7：/api/alerts/ack 与红色未读横幅一并下线；告警仍 append 写 数据/日志/告警.log

    @app.get("/api/v1/admin/archive_export")
    def api_archive_export(request: Request, year: str = Query("")):
        """审计流水年度导出归档（手填历史/预算历史/配置变更）→ xlsx；不删库内数据。管理员。"""
        user = _require(request)
        import accounts as _acc_mod
        import authz as _az

        _az.require_cap(_acc_mod.find_account(cfg, root, user), _az.CAP_EXPORT_ARCHIVE)
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
