"""手填/调整/分摊/去税/预算 — 从 server.create_app 纯搬家。

2.6.1 R7：校验辅助见 manual_helpers（语义零变更）。
2.6.3·C1：写路径进 _LOCK；忙/锁占用 → 409「更新进行中，请稍后再保存」。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from fastapi import Body, HTTPException, Request

import bu
import charts
import db
import profit
from app_state import _LOCK, _state
from routes.manual_helpers import (  # noqa: F401
    _clear_detail_rules,
    _item_amount_yuan,
    _ledger_public_fine_amounts,
    _merge_alloc_month,
    _merge_overrides_into_fine,
    _parse_alloc_ratios_payload,
    _parse_money_yuan,
    _parse_month_ym,
    _prepare_budget_batch_items,
    _prepare_manual_batch_items,
    _save_detail_rules_for_cat,
)

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

    from refresh_pipeline import do_recompute  # 持锁内调用，避免 recompute 再抢 _LOCK 死锁
    from routes._srv import recompute  # 读路径/兼容

    _screenshot_png = d.screenshot_png
    _HIDE_PW_STYLE = d.HIDE_PW_STYLE
    _WRAP_OPEN = d.WRAP_OPEN
    _WRITE_BUSY_DETAIL = "更新进行中，请稍后再保存"

    def _require(request: Request) -> str:
        user = _user(request)
        if not user:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return user

    def _conn():
        return db.connect(cfg, root)

    @contextmanager
    def with_write_lock(*, rebuild_std: bool = False):
        """2.6.3·C1：非阻塞拿刷新锁 → 写库 → do_recompute；拿不到或 OperationalError → 409。"""
        if _state.get("refreshing") or not _LOCK.acquire(blocking=False):
            raise HTTPException(status_code=409, detail=_WRITE_BUSY_DETAIL)
        try:
            try:
                yield
                do_recompute(cfg, root, rebuild_std=rebuild_std)
            except sqlite3.OperationalError as e:
                raise HTTPException(status_code=409, detail=_WRITE_BUSY_DETAIL) from e
        finally:
            _LOCK.release()

    @app.post("/api/adjust")
    def api_adjust(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        with with_write_lock(rebuild_std=True):
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
        return {"status": "ok", "adj_id": aid, "built_at": _state["built_at"]}

    @app.post("/api/adjust/batch")
    def api_adjust_batch(request: Request, payload: dict = Body(default={})):
        """批量写调整（2.2.6）：预检全过再写，整批一次 recompute。

        body: {目标表, 字段, 新值, 原因?, 类型?, 定位键列表:[...]}
        空列表/预检失败 → 400，不写库。
        """
        user = _require(request)
        keys_raw = payload.get("定位键列表")
        if not isinstance(keys_raw, list) or not keys_raw:
            raise HTTPException(status_code=400, detail="定位键列表不能为空")
        keys = [str(k).strip() for k in keys_raw if str(k).strip()]
        if not keys:
            raise HTTPException(status_code=400, detail="定位键列表不能为空")
        with with_write_lock(rebuild_std=True):
            conn = _conn()
            try:
                ids = db.add_adjustments_batch(
                    conn,
                    user,
                    str(payload.get("目标表") or ""),
                    keys,
                    str(payload.get("字段") or ""),
                    payload.get("新值", ""),
                    str(payload.get("原因") or ""),
                    str(payload.get("类型") or "改值"),
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            finally:
                conn.close()
        return {
            "status": "ok",
            "count": len(ids),
            "adj_ids": ids,
            "built_at": _state["built_at"],
        }

    @app.post("/api/adjust/{adj_id}/revoke")
    def api_revoke(request: Request, adj_id: int, payload: dict = Body(default={})):
        """撤销调整。任务书63·H-03：可选 reason 写入 config 审计。"""
        user = _require(request)
        reason = str((payload or {}).get("reason") or "").strip()
        with with_write_lock(rebuild_std=True):
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
            else:
                # 无变更时 with_write_lock 仍会 do_recompute；可接受（轻量）
                pass
        return {"status": "ok" if ok else "noop", "built_at": _state["built_at"]}

    @app.post("/api/adjust/expired/revoke_all")
    def api_revoke_all_expired(request: Request, payload: dict = Body(default={})):
        """批量撤销全部「过期疑似」=一键听源头新值。前端走"点按钮→确认保存"两步，这里只管执行。"""
        user = _require(request)
        reason = str((payload or {}).get("reason") or "").strip()
        with with_write_lock(rebuild_std=True):
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
        return {"status": "ok", "revoked": n, "built_at": _state["built_at"]}

    @app.post("/api/adjust/{adj_id}/rearm")
    def api_rearm(request: Request, adj_id: int, payload: dict = Body(default={})):
        """坚持我的数（仅过期疑似、仅逐条）：原值刷新为源头现值→重新生效→立即重算。"""
        user = _require(request)
        reason = str((payload or {}).get("reason") or "").strip()
        with with_write_lock(rebuild_std=True):
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
        with with_write_lock(rebuild_std=False):
            conn = _conn()
            try:
                db.set_manual(conn, payload.get("归属月", ""), item, 金额, user, 范围=scope)
            finally:
                conn.close()
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
        with with_write_lock(rebuild_std=False):
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

    def _public_detail_rows_for_month(conn, month: str, bu_names: list[str]) -> list[dict]:
        """2.4.0 管理端公共明细表：台账公共明细（降序）+ 金额覆盖 + 精配规则。"""
        import money as _money
        from profit.expense_period import manual_alloc_category_map as _mac

        y, m = _parse_month_ym(month)
        cat_map = _mac(cfg) or {}
        editable = set(cat_map.keys())
        overrides = db.get_public_detail_amount_overrides(conn, month)
        fine_rules = db.get_alloc_detail_rules(conn, month)
        by_fine = _ledger_public_fine_amounts(cfg, conn, y, m)
        _merge_overrides_into_fine(by_fine, overrides, editable, cat_map)
        rows: list[dict] = []
        for name, info in sorted(
            by_fine.items(), key=lambda kv: -float(kv[1].get("amount_fen") or 0)
        ):
            fen = float(info.get("amount_fen") or 0)
            yuan = float(_money.fen_to_yuan(int(round(fen))))
            rules = fine_rules.get(name) or {}
            modes = {str((r or {}).get("mode") or "") for r in rules.values()}
            modes.discard("")
            mode = next(iter(modes)) if len(modes) == 1 else ("" if not modes else "比例")
            bu_values: dict[str, float | None] = {b: None for b in bu_names}
            for b, r in rules.items():
                if b in bu_values:
                    bu_values[b] = float((r or {}).get("value") or 0)
            rows.append(
                {
                    "category": name,
                    "ledger_cat": info.get("cat") or "",
                    "amount_yuan": yuan,
                    "amount_disp": f"{yuan:,.2f}",
                    "amount_source": info.get("source") or "auto",
                    "amount_editable": name in editable,
                    "mode": mode or None,
                    "bu_values": bu_values,
                }
            )
        return rows

    def _alloc_panel_payload(conn, month: str) -> dict:
        """2.4.0 统一分摊面板：默认比例 + 公共明细两轴 + 汇总串。"""
        import money as _money
        from profit.bu_alloc import allocate_public_details_for_month

        base = _alloc_month_payload(conn, month)
        bu_names = list(base.get("bus") or [])
        details = _public_detail_rows_for_month(conn, month, bu_names)
        # 算各 BU 摊入（展示用，后端算好 disp）
        detail_pool = {
            d["category"]: {
                "amount": float(
                    _money.yuan_to_fen(d["amount_yuan"]) or 0
                ),
                "cat": d.get("ledger_cat") or "管理费用",
            }
            for d in details
            if abs(float(d.get("amount_yuan") or 0)) > 1e-12
            or d.get("amount_editable")
        }
        fine_rules: dict[str, dict] = {}
        for d in details:
            if not d.get("mode"):
                continue
            vals = {
                b: {"mode": d["mode"], "value": v}
                for b, v in (d.get("bu_values") or {}).items()
                if v is not None and v != ""
            }
            if vals:
                fine_rules[d["category"]] = vals
        defaults = dict(base.get("ratios") or {})
        try:
            by_bu = allocate_public_details_for_month(
                detail_pool, fine_rules, defaults, bu_names
            )
        except ValueError:
            by_bu = {}
        by_bu_disp = {}
        for b in bu_names:
            fen = sum(float(v) for v in (by_bu.get(b) or {}).values())
            by_bu_disp[b] = f"{float(_money.fen_to_yuan(int(round(fen)))):,.2f}"
        pool_fen = sum(
            float(_money.yuan_to_fen(d["amount_yuan"]) or 0) for d in details
        )
        alloc_fen = sum(
            sum(float(v) for v in cats.values()) for cats in by_bu.values()
        )
        remain_fen = max(0.0, pool_fen - alloc_fen)
        base.update(
            {
                "details": details,
                "by_bu_disp": by_bu_disp,
                "remain_company_disp": f"{float(_money.fen_to_yuan(int(round(remain_fen)))):,.2f}",
                "editable_amount_keys": sorted(
                    {
                        str(k)
                        for k in (
                            (cfg.get("manual_alloc_category_map") or {})
                            if isinstance(cfg.get("manual_alloc_category_map"), dict)
                            else {}
                        )
                    }
                ),
            }
        )
        return base

    @app.get("/api/alloc_ratios")
    def api_alloc_get(request: Request, month: str = ""):
        _require(request)
        conn = _conn()
        try:
            # 2.4.0：默认返回统一面板（含 details）；旧客户端仍可读 ratios 字段
            return _alloc_panel_payload(conn, month)
        finally:
            conn.close()

    def _write_alloc_panel(conn, month: str, known: set, user: str, payload: dict) -> dict:
        ratios = payload.get("ratios")
        overrides = payload.get("overrides")
        detail_rules = payload.get("detail_rules")
        if isinstance(ratios, dict) and ratios:
            vals = _parse_alloc_ratios_payload(ratios, known)
            merged = _merge_alloc_month(conn, month, known, vals)
            for b in known:
                db.set_alloc_ratio(conn, month, b, merged.get(b), user)
        if isinstance(overrides, dict) and overrides:
            for cat, amt in overrides.items():
                cat = str(cat or "").strip()
                if not cat:
                    continue
                try:
                    db.set_public_detail_amount_override(
                        conn,
                        month,
                        cat,
                        None if amt is None or amt == "" else amt,
                        user,
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e)) from e
        if isinstance(detail_rules, dict) and detail_rules:
            rows_lookup = _public_detail_rows_for_month(conn, month, list(known))
            for cat, spec in detail_rules.items():
                cat = str(cat or "").strip()
                if cat:
                    _save_detail_rules_for_cat(
                        conn, month, cat, spec, known, user, rows_lookup
                    )
        return _alloc_panel_payload(conn, month)

    @app.post("/api/alloc_ratios")
    def api_alloc_set(request: Request, payload: dict = Body(default={})):
        """写某月分摊（管理员）。兼容 ratios；扩展 overrides / detail_rules。"""
        user = _require(request)
        month = str(payload.get("归属月") or "").strip()
        ratios = payload.get("ratios")
        overrides = payload.get("overrides")
        detail_rules = payload.get("detail_rules")
        if not (
            (isinstance(ratios, dict) and ratios)
            or (isinstance(overrides, dict) and overrides)
            or (isinstance(detail_rules, dict) and detail_rules)
        ):
            raise HTTPException(status_code=400, detail="ratios/overrides/detail_rules 不能全空")
        bucfg = bu.load_bu_config(cfg, root) or {"bus": []}
        known = {b["name"] for b in bucfg["bus"]}
        with with_write_lock(rebuild_std=False):
            conn = _conn()
            try:
                out = _write_alloc_panel(conn, month, known, user, payload)
            finally:
                conn.close()
            _audit(
                cfg,
                root,
                user,
                (
                    "分摊",
                    f"公共费用分摊：{month} 已更新（默认合计 {out.get('sum_pct', 0):g}%）",
                ),
            )
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
        with with_write_lock(rebuild_std=False):
            conn = _conn()
            try:
                for cat, v in vals.items():
                    db.set_detax_rate(conn, cat, v, user)
                out = _detax_payload(conn)
            finally:
                conn.close()
            changed = "、".join(f"{c}={v if v is not None else '清除'}" for c, v in vals.items())
            _audit(cfg, root, user, ("去税", f"费用去税率已更改：{changed}"))
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
        with with_write_lock(rebuild_std=False):
            conn = _conn()
            try:
                db.set_budget(conn, year, metric, 金额, user, 范围=scope)
            finally:
                conn.close()
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
        with with_write_lock(rebuild_std=False):
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
