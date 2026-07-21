"""手填/调整/分摊/去税/预算 — 从 server.create_app 纯搬家。"""

from __future__ import annotations


from fastapi import Body, HTTPException, Request

import bu
import charts
import db
import profit
from app_state import _state


def _parse_money_yuan(v) -> float:
    """手填/预算金额：Decimal(str) 解析，返回元 float（db 层再 yuan_to_fen）。"""
    import money as _money

    d = _money.parse_decimal(v)
    if d is None:
        raise ValueError("空金额")
    return float(d)


def _parse_alloc_ratios_payload(ratios: dict, known: set) -> dict[str, float | None]:
    import money as _money

    vals: dict[str, float | None] = {}
    for b, v in ratios.items():
        b = str(b).strip()
        if b not in known:
            raise HTTPException(status_code=400, detail=f"未知 BU：{b}（以设置页 BU 名单为准）")
        if v is None or v == "":
            vals[b] = None
            continue
        try:
            fv = _money.quantize_rate(v, places=1)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"比例须为数字：{b}") from None
        if not (0 <= fv <= 100):
            raise HTTPException(status_code=400, detail=f"比例须在 0~100：{b}")
        vals[b] = fv
    return vals


def _merge_alloc_month(conn, month: str, known: set, vals: dict[str, float | None]) -> dict:
    """合并基准=该月生效比例（含沿用值）；返回合并后的 {BU:比例}。"""
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
    return merged


def _prepare_manual_batch_items(items: list, names: set, default_scope: str) -> list[tuple[str, float, str]]:
    """F-02 校验手填批量行 → [(项目, 金额, 范围), ...]。"""
    prepared: list[tuple[str, float, str]] = []
    for it in items:
        item = (it or {}).get("项目", "")
        if item not in names:
            raise HTTPException(status_code=400, detail=f"未知手填项目：{item}")
        try:
            金额 = _parse_money_yuan((it or {}).get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"金额须为数字：{item}") from None
        sc = str((it or {}).get("范围") or default_scope).strip() or "全公司"
        prepared.append((item, 金额, sc))
    return prepared


def _prepare_budget_batch_items(items: list) -> list[tuple[str, str, float, str]]:
    """F-02 校验预算批量行 → [(年份, 指标, 金额, 范围), ...]。"""
    prepared: list[tuple[str, str, float, str]] = []
    for it in items:
        it = it or {}
        metric = it.get("指标", "")
        if metric not in db.BUDGET_METRICS:
            raise HTTPException(status_code=400, detail=f"未知预算指标：{metric}")
        year = str(it.get("年份", "")).strip()
        if not (year.isdigit() and len(year) == 4):
            raise HTTPException(status_code=400, detail="年份须为4位数字")
        try:
            金额 = _parse_money_yuan(it.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"金额须为数字：{metric}") from None
        scope = str(it.get("范围", "全公司")).strip() or "全公司"
        if metric == "费用年预算" and scope == "全公司":
            raise HTTPException(status_code=400, detail="费用年预算须指定部门（范围）")
        if ("毛利率" in metric or "利润率" in metric) and (金额 < 0 or 金额 > 100):
            raise HTTPException(status_code=400, detail=f"比率类目标须为 0~100：{metric}")
        prepared.append((year, metric, 金额, scope))
    return prepared


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


    _screenshot_png = d.screenshot_png
    _HIDE_PW_STYLE = d.HIDE_PW_STYLE
    _WRAP_OPEN = d.WRAP_OPEN

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
            raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            conn.close()
        recompute(cfg, root, rebuild_std=True)
        return {"status": "ok", "adj_id": aid, "built_at": _state["built_at"]}

    @app.post("/api/adjust/{adj_id}/revoke")
    def api_revoke(request: Request, adj_id: int, payload: dict = Body(default={})):
        """撤销调整。任务书63·H-03：可选 reason 写入 config 审计。"""
        user = _require(request)
        reason = str((payload or {}).get("reason") or "").strip()
        conn = _conn()
        try:
            rows = db.list_adjustments(conn)
            hit = next((r for r in rows if int(r.get("id") or 0) == int(adj_id)), None)
            ok = db.revoke_adjustment(conn, adj_id)
        finally:
            conn.close()
        if ok:
            tip = f"撤销调整#{adj_id}"
            if hit:
                tip += f" · {hit.get('目标表') or ''}/{hit.get('定位键') or ''}/{hit.get('字段') or ''}"
            if reason:
                tip += f" · 理由：{reason}"
            _audit(cfg, root, user, ("调整", tip))
            recompute(cfg, root, rebuild_std=True)
        return {"status": "ok" if ok else "noop", "built_at": _state["built_at"]}

    @app.post("/api/adjust/expired/revoke_all")
    def api_revoke_all_expired(request: Request, payload: dict = Body(default={})):
        """批量撤销全部「过期疑似」=一键听源头新值。前端走"点按钮→确认保存"两步，这里只管执行。"""
        user = _require(request)
        reason = str((payload or {}).get("reason") or "").strip()
        conn = _conn()
        try:
            n = db.revoke_expired_adjustments(conn)
        finally:
            conn.close()
        if n:
            tip = f"批量撤销过期疑似 {n} 条"
            if reason:
                tip += f" · 理由：{reason}"
            _audit(cfg, root, user, ("调整", tip))
            recompute(cfg, root, rebuild_std=True)
        return {"status": "ok", "revoked": n, "built_at": _state["built_at"]}

    @app.post("/api/adjust/{adj_id}/rearm")
    def api_rearm(request: Request, adj_id: int, payload: dict = Body(default={})):
        """坚持我的数（仅过期疑似、仅逐条）：原值刷新为源头现值→重新生效→立即重算。"""
        user = _require(request)
        reason = str((payload or {}).get("reason") or "").strip()
        conn = _conn()
        try:
            rows = db.list_adjustments(conn)
            hit = next((r for r in rows if int(r.get("id") or 0) == int(adj_id)), None)
            db.rearm_adjustment(conn, adj_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            conn.close()
        tip = f"坚持调整#{adj_id}"
        if hit:
            tip += f" · {hit.get('目标表') or ''}/{hit.get('定位键') or ''}/{hit.get('字段') or ''}"
        if reason:
            tip += f" · 理由：{reason}"
        _audit(cfg, root, user, ("调整", tip))
        recompute(cfg, root, rebuild_std=True)
        return {"status": "ok", "built_at": _state["built_at"]}

    @app.get("/api/adjustments")
    def api_adjustments(request: Request):
        _require(request)
        conn = _conn()
        try:
            return db.list_adjustments(conn)
        finally:
            conn.close()

    @app.get("/api/manual_items")
    def api_manual_items(request: Request):
        """手填项目名列表（Vue 管理端用；与 config.manual_items / legacy __MANUAL_ITEMS__ 同源）。"""
        _require(request)
        items = [it["name"] for it in (cfg.get("manual_items") or []) if isinstance(it, dict) and it.get("name")]
        return {"items": items}

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
            金额 = _parse_money_yuan(payload.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="金额须为数字") from None
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
        """批量手填：payload={归属月, 范围?, items:[{项目,金额,范围?}]}，只重算一遍。

        任务书63·F-02：先全量校验 → 原子事务内逐条 commit=False 写入 → 一次提交；
        任一条非法则整批不落库。
        """
        user = _require(request)
        month = payload.get("归属月", "")
        default_scope = str(payload.get("范围") or "全公司").strip() or "全公司"
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="items 不能为空")
        names = {it["name"] for it in cfg["manual_items"]}
        prepared = _prepare_manual_batch_items(items, names, default_scope)
        n = 0
        conn = _conn()
        try:

            def _write():
                nonlocal n
                for item, 金额, sc in prepared:
                    db.set_manual(conn, month, item, 金额, user, 范围=sc, commit=False)
                    n += 1

            db.commit_immediate(conn, _write)
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
            raise HTTPException(status_code=400, detail="归属月格式须为 YYYY-MM") from None
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
            # led 值为分；汇总仍用分做比例拆分，显示层再 ÷100 转元（2.2.4·E）
            month_total = round(sum(float(v or 0) for v in led.values()), 2)
        known = {b: p for b, p in ratios.items() if b in set(bu_names)}
        sum_pct = round(sum(known.values()), 1)
        remain_pct = round(max(0.0, 100.0 - sum_pct), 1)
        remain_amt = round(month_total * remain_pct / 100.0, 2)
        orphans = sorted(set(ratios) - set(bu_names))
        # 显示串：分 → 元（铁律2：前端零运算；用 money.fen_to_yuan）
        import money as _money

        month_total_yuan = _money.fen_to_yuan(month_total)
        remain_amt_yuan = _money.fen_to_yuan(remain_amt)
        return {
            "month": month,
            "bus": bu_names,
            "ratios": known,
            "inherited_from": inherited_from,
            "orphans": orphans,
            "month_total": month_total,  # 分（内部/兼容）
            "month_total_disp": f"{month_total_yuan:,.2f}",  # 元
            "sum_pct": sum_pct,
            "remain_pct": remain_pct,
            "remain_amt_disp": f"{remain_amt_yuan:,.2f}",  # 元
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
        vals = _parse_alloc_ratios_payload(ratios, known)
        conn = _conn()
        try:
            # 合并基准=该月生效比例（含沿用值·陆总0714）；保存时把生效全集固化进本月，
            # 否则只改一个 BU 会让其余 BU 的沿用比例丢失（本月一旦有行，沿用即不再兜底）
            merged = _merge_alloc_month(conn, month, known, vals)
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
                import money as _money

                fv = _money.quantize_rate(v, places=2)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"去税率须为数字：{cat}") from None
            if not (0 <= fv <= 100):
                raise HTTPException(status_code=400, detail=f"去税率须在 0~100：{cat}")
            vals[cat] = fv
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
            金额 = _parse_money_yuan(payload.get("金额"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="金额须为数字") from None
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
        """批量业绩目标：payload={items:[{年份,指标,金额,范围?}]}，一次重算。

        任务书63·F-02：先全量校验 → 原子事务内逐条 commit=False 写入 → 一次提交。
        """
        user = _require(request)
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail="items 不能为空")
        prepared = _prepare_budget_batch_items(items)
        n = 0
        conn = _conn()
        try:

            def _write():
                nonlocal n
                for year, metric, 金额, scope in prepared:
                    db.set_budget(conn, year, metric, 金额, user, 范围=scope, commit=False)
                    n += 1

            db.commit_immediate(conn, _write)
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
