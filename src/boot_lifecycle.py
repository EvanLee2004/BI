# -*- coding: utf-8 -*-
"""冷启动 LKG / install_state 钩子（3.6.0 G1）——从 server.serve 拆出。"""

from __future__ import annotations

from app_state import _state
import loaders


def boot_save_lkg_and_ready(cfg, root) -> None:
    """成功构建 → LKG + install ready。"""
    try:
        import install_state as _inst
        import lkg_snapshot as _lkg
        import runtime_marker as _rm
        import version as _ver

        dd = loaders.data_dir(cfg, root)
        ident = _rm.runtime_identity(root)
        try:
            from schema import SCHEMA_VERSION as _sv
        except Exception:
            _sv = None
        _lkg.save_lkg(
            dd,
            _state.get("summary") or {},
            version=str(_ver.read_version()),
            commit=str(ident.get("git_commit") or ""),
            schema_version=_sv,
        )
        _inst.mark_ready(
            dd,
            version=str(ident.get("version") or ""),
            commit=str(ident.get("git_commit") or ""),
        )
    except Exception as _e:
        print(f"[server] LKG/install_state 保存跳过：{type(_e).__name__}")


def boot_fail_closed(cfg, root, exc: BaseException) -> None:
    """构建失败 fail-closed — LKG / degraded，禁止伪装首次安装。"""
    print(
        f"[server] ⚠ 构建失败：{type(exc).__name__}: {exc}"
        "（服务仍启动，修数据后 /api/v1/admin/refresh 或重启）"
    )
    _state["last_build_ok"] = False
    try:
        import install_state as _inst
        import lkg_snapshot as _lkg

        dd = loaders.data_dir(cfg, root)
        _inst.mark_degraded(dd, reason=type(exc).__name__)
        try:
            from schema import SCHEMA_VERSION as _sv
        except Exception:
            _sv = None
        lkg = _lkg.load_lkg(dd, require_schema=_sv)
        if lkg is not None and _lkg.is_compatible(lkg, schema_version=_sv):
            summary = lkg.get("summary")
            if isinstance(summary, dict):
                _state["summary"] = summary
                _state["has_data"] = True
                _state["admin_html"] = "ready"
                _state["built_at"] = lkg.get("saved_at") or _state.get("built_at")
                _state["from_lkg"] = True
                print("[server] 已加载 Last-Known-Good 快照（构建失败 fail-closed）")
    except Exception as _e2:
        print(f"[server] LKG 加载跳过：{type(_e2).__name__}")
    try:
        import maintenance_mode as _mm

        if not _mm.is_on(cfg, root):
            _mm.turn_on("boot", cfg, root)
    except Exception:
        pass


def boot_first_refresh(cfg, root, refresh_fn) -> bool:
    """冷启动首次 refresh；成功 True。refresh_fn 由 server 注入避免环依赖。"""
    print("[server] 首次构建页面（跑管道+渲染）……")
    try:
        refresh_fn(cfg, root)
        _state["last_build_ok"] = True
        print(f"[server] 就绪 built_at={_state['built_at']}")
        boot_save_lkg_and_ready(cfg, root)
        return True
    except Exception as e:
        boot_fail_closed(cfg, root, e)
        return False
