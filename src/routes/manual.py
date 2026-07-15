"""手填/调整/分摊/去税/预算 — 从 server.create_app 纯搬家。"""

from __future__ import annotations


from fastapi import Body, HTTPException, Request

import bu
import charts
import db
import profit
from app_state import _state


def register(app, d):
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
    normalize_schedule_times = d.normalize_schedule_times
    save_settings = d.save_settings
    read_zhiyun_creds = d.read_zhiyun_creds
    save_zhiyun_creds = d.save_zhiyun_creds
    read_zhiyun_conn = d.read_zhiyun_conn
    save_zhiyun_conn = d.save_zhiyun_conn
    _screenshot_png = d.screenshot_png
    _HIDE_PW_STYLE = d.HIDE_PW_STYLE
    _WRAP_OPEN = d.WRAP_OPEN
    DEFAULT_PW = d.DEFAULT_PW

    def _require(request: Request) -> str:
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return user

    def _conn():
        return db.connect(cfg, root)

    @app.post("/api/adjust")
    def api_adjust(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        conn = _conn()
        try:
            aid = db.add_adjustment(
                conn,
                user,
                payload.get("目标表", ""),
                payload.get("定位键", ""),
                payload.get("字段", ""),
                payload.get("新值", ""),
                payload.get("原因", ""),
                payload.get("类型", "改值"),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "adj_id": aid, "built_at": _state["built_at"]}

    @app.post("/api/adjust/{adj_id}/revoke")
    def api_revoke(request: Request, adj_id: int):
        _require(request)
        conn = _conn()
        try:
            ok = db.revoke_adjustment(conn, adj_id)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok" if ok else "noop", "built_at": _state["built_at"]}

    @app.post("/api/adjust/expired/revoke_all")
    def api_revoke_all_expired(request: Request):
        """批量撤销全部「过期疑似」=一键听源头新值。前端走"点按钮→确认保存"两步，这里只管执行。"""
        _require(request)
        conn = _conn()
        try:
            n = db.revoke_expired_adjustments(conn)
        finally:
            conn.close()
        if n:
            recompute(cfg, root)
        return {"status": "ok", "revoked": n, "built_at": _state["built_at"]}

    @app.post("/api/adjust/{adj_id}/rearm")
    def api_rearm(request: Request, adj_id: int):
        """坚持我的数（仅过期疑似、仅逐条）：原值刷新为源头现值→重新生效→立即重算。"""
        _require(request)
        conn = _conn()
        try:
            db.rearm_adjustment(conn, adj_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.get("/api/adjustments")
    def api_adjustments(request: Request):
        _require(request)
        conn = _conn()
        try:
            return db.list_adjustments(conn)
        finally:
            conn.close()

    @app.get("/api/manual")
    def api_manual_get(request: Request, month: str | None = None, scope: str = "全公司"):
        _require(request)
        conn = _conn()
        try:
            return db.get_manual(conn, month, 范围=scope or "全公司")
        finally:
            conn.close()

    @app.post("/api/manual")
    def api_manual_set(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        item = payload.get("项目", "")
        if item not in {it["name"] for it in cfg["manual_items"]}:
            raise HTTPException(status_code=400, detail=f"未知手填项目：{item}")
        try:
            金额 = float(payload.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="金额须为数字")
        scope = str(payload.get("范围") or "全公司").strip() or "全公司"
        conn = _conn()
        try:
            db.set_manual(conn, payload.get("归属月", ""), item, 金额, user, 范围=scope)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.post("/api/manual_batch")
    def api_manual_batch(request: Request, payload: dict = Body(default={})):
        """批量手填：payload={归属月, 范围?, items:[{项目,金额,范围?}]}，只重算一遍。"""
        user = _require(request)
        month = payload.get("归属月", "")
        default_scope = str(payload.get("范围") or "全公司").strip() or "全公司"
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="items 不能为空")
        names = {it["name"] for it in cfg["manual_items"]}
        conn = _conn()
        try:
            n = 0
            for it in items:
                item = (it or {}).get("项目", "")
                if item not in names:
                    raise HTTPException(status_code=400, detail=f"未知手填项目：{item}")
                try:
                    金额 = float((it or {}).get("金额"))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"金额须为数字：{item}")
                sc = str((it or {}).get("范围") or default_scope).strip() or "全公司"
                db.set_manual(conn, month, item, 金额, user, 范围=sc)
                n += 1
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "count": n, "built_at": _state["built_at"]}

    def _alloc_month_payload(conn, month: str) -> dict:
        """某月分摊面板数据：BU 名单（与设置页同源）+ 比例 + 本月公共费用总额/剩余（显示串后端下发·铁律2）。"""
        import datetime as _dt
        import columns as _columns

        try:
            y, m = int(month[:4]), int(month[5:7])
            assert 1 <= m <= 12 and month[4] == "-"
        except (ValueError, AssertionError, IndexError):
            raise HTTPException(status_code=400, detail="归属月格式须为 YYYY-MM")
        bucfg = bu.load_bu_config(cfg, root) or {"bus": []}
        bu_names = [b["name"] for b in bucfg["bus"]]
        # 陆总0714：该月没填 → 回显沿用的最近填写月比例（inherited_from 标来源；保存即固化到本月）
        ratios, src_month = db.effective_alloc_month(conn, month)
        inherited_from = src_month if (src_month and src_month != month) else None
        lh, lr = db.load_ledger(cfg, conn)
        month_total = 0.0
        if lh:
            lcols = _columns.resolve_ledger_columns(lh)
            public_rows = profit.filter_ledger_rows_by_pc(lh, lr, {"公共"})
            start = _dt.date(y, m, 1)
            end = _dt.date(y, m + 1, 1) - _dt.timedelta(days=1) if m < 12 else _dt.date(y, 12, 31)
            led, _ = profit.compute_ledger_expenses(public_rows, y, start, end, cfg, lcols)
            month_total = round(sum(float(v or 0) for v in led.values()), 2)
        known = {b: p for b, p in ratios.items() if b in set(bu_names)}
        sum_pct = round(sum(known.values()), 1)
        remain_pct = round(max(0.0, 100.0 - sum_pct), 1)
        remain_amt = round(month_total * remain_pct / 100.0, 2)
        orphans = sorted(set(ratios) - set(bu_names))
        return {
            "month": month,
            "bus": bu_names,
            "ratios": known,
            "inherited_from": inherited_from,
            "orphans": orphans,
            "month_total": month_total,
            "month_total_disp": f"{month_total:,.2f}",
            "sum_pct": sum_pct,
            "remain_pct": remain_pct,
            "remain_amt_disp": f"{remain_amt:,.2f}",
        }

    @app.get("/api/alloc_ratios")
    def api_alloc_get(request: Request, month: str = ""):
        _require(request)
        conn = _conn()
        try:
            return _alloc_month_payload(conn, month)
        finally:
            conn.close()

    @app.post("/api/alloc_ratios")
    def api_alloc_set(request: Request, payload: dict = Body(default={})):
        """写某月分摊比例（管理员）。payload={归属月, ratios:{BU:比例%|null}}。
        约束：BU 须在设置页 BU 名单内；单值 0~100；已知 BU 合计 ≤100（容差 0.05）。null=删行不分摊。"""
        user = _require(request)
        month = str(payload.get("归属月") or "").strip()
        ratios = payload.get("ratios")
        if not isinstance(ratios, dict) or not ratios:
            raise HTTPException(status_code=400, detail="ratios 不能为空")
        bucfg = bu.load_bu_config(cfg, root) or {"bus": []}
        known = {b["name"] for b in bucfg["bus"]}
        vals: dict[str, float | None] = {}
        for b, v in ratios.items():
            b = str(b).strip()
            if b not in known:
                raise HTTPException(status_code=400, detail=f"未知 BU：{b}（以设置页 BU 名单为准）")
            if v is None or v == "":
                vals[b] = None
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"比例须为数字：{b}")
            if not (0 <= fv <= 100):
                raise HTTPException(status_code=400, detail=f"比例须在 0~100：{b}")
            vals[b] = round(fv, 1)
        conn = _conn()
        try:
            # 合并基准=该月生效比例（含沿用值·陆总0714）；保存时把生效全集固化进本月，
            # 否则只改一个 BU 会让其余 BU 的沿用比例丢失（本月一旦有行，沿用即不再兜底）
            merged, _src = db.effective_alloc_month(conn, month)
            merged = {b: p for b, p in merged.items() if b in known}
            for b, v in vals.items():
                if v is None:
                    merged.pop(b, None)
                else:
                    merged[b] = v
            total = sum(p for b, p in merged.items() if b in known)
            if total > 100.05:
                raise HTTPException(
                    status_code=400,
                    detail=f"该月各 BU 比例合计 {total:g}% 超过 100%，请调整（可以小于 100%，剩余留公司层）",
                )
            for b in known:
                db.set_alloc_ratio(conn, month, b, merged.get(b), user)
            out = _alloc_month_payload(conn, month)
        finally:
            conn.close()
        _audit(cfg, root, user, ("分摊", f"公共费用分摊：{month} 比例已更改（合计 {out['sum_pct']:g}%）"))
        recompute(cfg, root)
        out.update({"status": "ok", "built_at": _state["built_at"]})
        return out

    def _detax_payload(conn) -> dict:
        """费用去税率录入页数据：可去税类别（含全年金额参考·降序）+ 已填税率。"""

        cats = db.list_detax_categories(conn, cfg)
        rates = db.load_detax_rates(conn)
        return {
            "categories": [
                {"category": c["category"], "amount_disp": charts.fmt_wan(c["amount"]) + "万"} for c in cats
            ],
            "rates": rates,
        }

    @app.get("/api/detax_rates")
    def api_detax_get(request: Request):
        _require(request)
        conn = _conn()
        try:
            return _detax_payload(conn)
        finally:
            conn.close()

    @app.post("/api/detax_rates")
    def api_detax_set(request: Request, payload: dict = Body(default={})):
        """写费用去税率（管理员·全局一套·陆总0714）。payload={rates:{费用类别:税率%|null}}。
        税率 0~100；null/空/0 → 删行=该类别不去税（等价默认，页面数字回归红线中性）。"""
        user = _require(request)
        rates = payload.get("rates")
        if not isinstance(rates, dict) or not rates:
            raise HTTPException(status_code=400, detail="rates 不能为空")
        vals: dict[str, float | None] = {}
        for cat, v in rates.items():
            cat = str(cat).strip()
            if not cat:
                raise HTTPException(status_code=400, detail="费用类别不能为空")
            if v is None or v == "":
                vals[cat] = None
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"去税率须为数字：{cat}")
            if not (0 <= fv <= 100):
                raise HTTPException(status_code=400, detail=f"去税率须在 0~100：{cat}")
            vals[cat] = round(fv, 2)
        conn = _conn()
        try:
            for cat, v in vals.items():
                db.set_detax_rate(conn, cat, v, user)
            out = _detax_payload(conn)
        finally:
            conn.close()
        changed = "、".join(f"{c}={v if v is not None else '清除'}" for c, v in vals.items())
        _audit(cfg, root, user, ("去税", f"费用去税率已更改：{changed}"))
        recompute(cfg, root)
        out.update({"status": "ok", "built_at": _state["built_at"]})
        return out

    @app.get("/api/budget")
    def api_budget_get(request: Request, year: str | None = None):
        _require(request)
        conn = _conn()
        try:
            return db.get_budget(conn, year)
        finally:
            conn.close()

    @app.post("/api/budget")
    def api_budget_set(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        metric = payload.get("指标", "")
        if metric not in db.BUDGET_METRICS:
            raise HTTPException(status_code=400, detail=f"未知预算指标：{metric}")
        year = str(payload.get("年份", "")).strip()
        if not (year.isdigit() and len(year) == 4):
            raise HTTPException(status_code=400, detail="年份须为4位数字")
        try:
            金额 = float(payload.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="金额须为数字")
        scope = str(payload.get("范围", "全公司")).strip() or "全公司"
        if metric == "费用年预算" and scope == "全公司":
            raise HTTPException(status_code=400, detail="费用年预算须指定部门（范围）")
        # 业务目标允许 全公司 或 BU 名；费用年预算允许部门名
        conn = _conn()
        try:
            db.set_budget(conn, year, metric, 金额, user, 范围=scope)
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.post("/api/budget_batch")
    def api_budget_batch(request: Request, payload: dict = Body(default={})):
        """批量业绩目标：payload={items:[{年份,指标,金额,范围?}]}，一次重算。"""
        user = _require(request)
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="items 不能为空")
        conn = _conn()
        try:
            n = 0
            for it in items:
                it = it or {}
                metric = it.get("指标", "")
                if metric not in db.BUDGET_METRICS:
                    raise HTTPException(status_code=400, detail=f"未知预算指标：{metric}")
                year = str(it.get("年份", "")).strip()
                if not (year.isdigit() and len(year) == 4):
                    raise HTTPException(status_code=400, detail="年份须为4位数字")
                try:
                    金额 = float(it.get("金额"))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"金额须为数字：{metric}")
                scope = str(it.get("范围", "全公司")).strip() or "全公司"
                if metric == "费用年预算" and scope == "全公司":
                    raise HTTPException(status_code=400, detail="费用年预算须指定部门（范围）")
                if ("毛利率" in metric or "利润率" in metric) and (金额 < 0 or 金额 > 100):
                    raise HTTPException(status_code=400, detail=f"比率类目标须为 0~100：{metric}")
                db.set_budget(conn, year, metric, 金额, user, 范围=scope)
                n += 1
        finally:
            conn.close()
        recompute(cfg, root)
        return {"status": "ok", "count": n, "built_at": _state["built_at"]}

    @app.get("/api/budget_depts")
    def api_budget_depts(request: Request):
        _require(request)
        conn = _conn()
        try:
            return db.list_budget_depts(conn)
        finally:
            conn.close()

    @app.get("/api/adjust_fields")
    def api_adjust_fields(request: Request):
        """R1：各明细表可调整字段（schema 黑名单制推导），管理员端字段下拉数据源。"""
        _require(request)
        return db.adjustable_fields()
