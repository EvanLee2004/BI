#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内网双端服务薄门面（3.2.0）。

实现见：
- app_factory.build_app — FastAPI 组装
- middleware_stack — 中间件
- refresh_pipeline — 刷新/重算/异步刷新
- app_state — 唯一 _state / _LOCK

测试与 routes 仍 `import server`；本模块 re-export 稳定符号。
"""

from __future__ import annotations

import os
import threading
import time

import accounts
import auth_session
import loaders
import refresh_pipeline
import tpl
from app_state import (  # noqa: F401
    COOKIE,
    SID_COOKIE,
    VCOOKIE,
    SESSION_TTL,
    STATIC_DIR,
    _EXPORT_LOCK,
    _LOCK,
    _state,
)
from audit_diff import (  # noqa: E402,F401
    _ZY_BANNER_NAMES,
    _ZY_FILE_KEYS,
    _admin_page,
    _audit,
    _bootstrap_page,
    _diff_accounts,
    _diff_bu_config,
    _file_as_of_label,
    _join_summary,
    _manual_items_json,
    _run_reasons,
    admin_ui_source,
    apply_business_health_yellow,
    build_fetch_fallback_banners,
)
from settings_io import (  # noqa: E402,F401
    CRON_BEGIN,
    CRON_END,
    EDITABLE_SETTINGS,
    MAX_SCHEDULE_TIMES,
    _TIME_RE,
    _cron_block_for_times,
    _linux_sync_schedule,
    _strip_cron_sentinel,
    _zhiyun_cfg_file,
    get_schedule_times,
    normalize_schedule_times,
    read_zhiyun_conn,
    read_zhiyun_creds,
    save_settings,
    save_zhiyun_conn,
    save_zhiyun_creds,
    sync_schedule,
)

# 兼容旧引用
GZIP_MINIMUM_SIZE = 1000
_NO_STORE = {"Cache-Control": "no-store"}
_HIDE_PW_STYLE = tpl.load("partials/hide_pw_style.html")
_WRAP_OPEN = tpl.load("partials/wrap_open.html")
_EMPTY_DATA_HTML = tpl.load("partials/empty_data.html")
_BU_NAV_TPL = tpl.load("partials/bu_nav.html")
_BU_NAV_LINK_TPL = tpl.load("partials/bu_nav_link.html")
DEFAULT_PW = os.environ.get("KANBAN_ADMIN_PW", accounts.DEFAULT_ADMIN_PW)
DEFAULT_VIEW_PW = accounts.DEFAULT_VIEW_PW
DEFAULT_ADMIN_ACCOUNT = "lushasha"

# 会话别名
_secret_path = auth_session.secret_path
_load_or_init_secret = auth_session.load_or_init_secret
_save_secret = auth_session.save_secret
_make_token = auth_session.make_token
_check_token_raw = auth_session.check_token_raw
_check_token = auth_session.check_token
_check_vsubject = auth_session.check_vsubject

# 刷新管道（_do_full 可被测试打桩；publish 稳定别名供 import server 使用）
publish = refresh_pipeline.publish
_publish = refresh_pipeline.publish
_do_full = refresh_pipeline.do_full
_do_recompute = refresh_pipeline.do_recompute
recompute = refresh_pipeline.recompute
refresh = refresh_pipeline.refresh
start_refresh_async = refresh_pipeline.start_refresh_async

# app factory helpers re-export（兼容旧 from server import …）
from app_factory import (  # noqa: E402,F401
    _admin_login_file,
    _file_html_doc,
    _html_doc,
    _view_login_file,
    resolve_serve_static,
    resolve_server_host,
)

refresh_pipeline.set_admin_page_builder(_admin_page)


def create_app(cfg, root=None):
    """组装 FastAPI（实现见 app_factory.build_app）。"""
    from app_factory import build_app

    return build_app(cfg, root)


import export_png as _export_png  # noqa: E402

_screenshot_png = _export_png.screenshot_png


def _write_boot_runtime_marker(root=None) -> None:
    """3.5.0：启动写 runtime marker，供 reload 真生效核验。"""
    try:
        from pathlib import Path

        import runtime_marker as _rm

        _root = Path(root) if root else Path(__file__).resolve().parent.parent
        m = _rm.write_runtime_marker(_root)
        print(
            f"[server] runtime_marker version={m.get('version')} "
            f"commit={(m.get('git_commit') or '')[:12]} pid={m.get('pid')}"
        )
    except Exception as e:
        print(f"[server] runtime_marker 写入跳过：{type(e).__name__}: {e}")


def _default_program_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent


def serve(cfg=None, root=None):
    cfg = cfg or loaders.load_config()
    root = root or _default_program_root()
    try:
        from app_logging import setup_logging

        setup_logging(cfg, root)
    except Exception:
        pass
    # 3.7.3：候选预热进程（KANBAN_CANDIDATE=1）不写共享 runtime_marker、不跑 boot/调度
    is_candidate = _is_candidate_process()
    if is_candidate:
        print(
            "[server] candidate warm-up mode: skip runtime_marker write + "
            "boot_first_refresh + schedule_loop"
        )
    else:
        _boot_primary(cfg, root)
    app = create_app(cfg, root)
    import uvicorn

    host = resolve_server_host(cfg)
    port = int(os.environ.get("KANBAN_PORT") or cfg.get("server_port", 8018))
    static_on = resolve_serve_static(cfg)
    mode = "直连(挂static)" if static_on else "反代后端(无static挂载)"
    print(f"[server] 内网服务 host={host} port={port} 模式={mode}")
    print(
        f"[server] 用户端 http://{host if host not in ('0.0.0.0', '::') else '<本机IP>'}:{port}/"
        "   管理员 /admin"
    )
    if not is_candidate:
        _start_background_services(cfg, root)
    uvicorn.run(app, host=host, port=port, log_level="info")


def _is_candidate_process() -> bool:
    return str(os.environ.get("KANBAN_CANDIDATE") or "").strip() in (
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    )


def _confirm_update_good():
    # OPS-005：冷启动全量刷新可能 >20s；等 has_data 或最多 180s 再清回滚标记
    import app_state as _as

    deadline = time.time() + 180
    while time.time() < deadline:
        if _as._state.get("has_data") or _as._state.get("built_at"):
            break
        time.sleep(2)
    else:
        print("[server] clear_rollback_marker: wait has_data timeout 180s, clearing anyway")
    try:
        import updater

        updater.clear_rollback_marker(loaders.ROOT)
    except Exception as e:
        print(f"[server] clear_rollback_marker 跳过：{type(e).__name__}: {e}")


def _boot_primary(cfg, root) -> None:
    _write_boot_runtime_marker(root)
    from boot_lifecycle import boot_first_refresh

    boot_ok = boot_first_refresh(cfg, root, refresh)
    if not boot_ok:
        return
    try:
        import maintenance_mode as _mm

        _mm.turn_off(cfg, root)
    except Exception as e:
        print(f"[server] maintenance turn_off 跳过：{type(e).__name__}: {e}")


def _start_background_services(cfg, root) -> None:
    threading.Thread(target=_confirm_update_good, daemon=True).start()
    try:
        from schedule_loop import start_schedule_loop

        start_schedule_loop(cfg, root, start_refresh_async)
    except Exception as e:
        print(f"[server] schedule_loop 启动失败：{type(e).__name__}: {e}")



if __name__ == "__main__":
    serve()
