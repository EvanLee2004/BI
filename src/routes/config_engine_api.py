"""任务书46·4：管理端口径配置 API。"""
from __future__ import annotations

from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

import db
from domain import config_engine as ce


def register(app, d):
    cfg = d.cfg
    root = d.root
    _user = d.user
    _audit = d.audit

    def _require(request: Request) -> str:
        u = _user(request)
        if not u:
            raise HTTPException(status_code=401, detail="需要管理员登录")
        return u

    @app.get("/api/config/caliber")
    def api_caliber_get(request: Request):
        _require(request)
        conn = db.connect(cfg, root)
        try:
            ce.seed_if_empty(conn, cfg)
            data = ce.load_all(conn, use_cache=False)
        finally:
            conn.close()
        return {"config": data, "keys": list(ce.DEFAULT_KEYS)}

    @app.post("/api/config/caliber")
    def api_caliber_post(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        key = str(payload.get("key") or payload.get("键") or "").strip()
        if key not in ce.DEFAULT_KEYS:
            raise HTTPException(status_code=400, detail=f"未知键：{key}")
        if "value" not in payload and "值" not in payload:
            raise HTTPException(status_code=400, detail="缺少 value")
        value = payload.get("value", payload.get("值"))
        conn = db.connect(cfg, root)
        try:
            ce.seed_if_empty(conn, cfg, operator=user)
            ver, errs = ce.save_config(conn, key, value, operator=user)
            if errs:
                raise HTTPException(status_code=400, detail={"errors": errs})
            _audit(cfg, root, user, ("口径", f"更新 {key} → v{ver}"))
            data = ce.load_all(conn, use_cache=False)
        finally:
            conn.close()
        return {"ok": True, "version": ver, "config": data}

    @app.post("/api/config/caliber/rollback")
    def api_caliber_rollback(request: Request, payload: dict = Body(default={})):
        user = _require(request)
        key = str(payload.get("key") or "").strip()
        ver = int(payload.get("version") or 0)
        conn = db.connect(cfg, root)
        try:
            ok = ce.rollback_key(conn, key, ver, operator=user)
            if not ok:
                raise HTTPException(status_code=400, detail="回滚失败：版本不存在")
            _audit(cfg, root, user, ("口径", f"回滚 {key} → v{ver}"))
            data = ce.load_all(conn, use_cache=False)
        finally:
            conn.close()
        return {"ok": True, "config": data}
