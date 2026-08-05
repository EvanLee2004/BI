# -*- coding: utf-8 -*-
"""台账共享 CIFS 配置（3.7.15 B 方案）· 拼装/校验/探测/apply 接口。

- 本地配置存非密字段 + 派生 ledger_share_path
- 密码只写本机 cred（经受控脚本），永不进 git / GET
- 禁止 path traversal；禁止 Python 内任意 sudo shell
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

# 默认挂载点（可被本地配置覆盖；非「唯一不可覆盖生产常量」）
DEFAULT_MOUNT_ROOT = "/mnt/kanban-ledger"
DEFAULT_CRED_PATH = "/etc/kanban/cifs-ledger.cred"

# 字段键
KEY_SERVER = "ledger_smb_server"
KEY_SHARE = "ledger_smb_share"
KEY_RELPATH = "ledger_smb_relpath"
KEY_USERNAME = "ledger_smb_username"
KEY_MOUNT_ROOT = "ledger_mount_root"
KEY_SHARE_PATH = "ledger_share_path"
KEY_PASSWORD_SET = "ledger_smb_password_set"  # 仅探测用，可不落盘

SMB_LOCAL_KEYS = (
    KEY_SERVER,
    KEY_SHARE,
    KEY_RELPATH,
    KEY_USERNAME,
    KEY_MOUNT_ROOT,
    KEY_SHARE_PATH,
)

_RE_SERVER = re.compile(r"^[A-Za-z0-9._\-]+$")
_RE_SHARE = re.compile(r"^[^/\\]+$")


def normalize_mount_root(raw: str | None) -> str:
    s = str(raw or "").strip() or DEFAULT_MOUNT_ROOT
    s = s.rstrip("/")
    if not s.startswith("/"):
        raise ValueError("挂载根路径须为绝对路径（如 /mnt/kanban-ledger）")
    if ".." in s.split("/"):
        raise ValueError("挂载根路径非法")
    return s


def normalize_relpath(raw: str | None) -> str:
    """相对路径：禁止绝对、禁止 ..、禁止空段穿越。"""
    s = str(raw or "").strip().replace("\\", "/")
    if not s:
        raise ValueError("台账相对路径不能为空")
    if s.startswith("/"):
        raise ValueError("相对路径不能以 / 开头")
    parts = [p for p in s.split("/") if p not in ("", ".")]
    if not parts:
        raise ValueError("相对路径不能为空")
    if any(p == ".." for p in parts):
        raise ValueError("相对路径禁止包含 ..")
    return "/".join(parts)


def normalize_server(raw: str | None) -> str:
    s = str(raw or "").strip()
    if not s:
        raise ValueError("共享服务器地址不能为空")
    if not _RE_SERVER.match(s):
        raise ValueError("服务器地址仅允许字母数字与 ._-")
    return s


def normalize_share(raw: str | None) -> str:
    s = str(raw or "").strip()
    if not s:
        raise ValueError("共享名不能为空")
    if "/" in s or "\\" in s or ".." in s:
        raise ValueError("共享名非法")
    return s


def normalize_username(raw: str | None) -> str:
    s = str(raw or "").strip()
    # 允许空：仅改路径时可不交 username
    return s


def assemble_ledger_share_path(
    *,
    mount_root: str | None = None,
    relpath: str | None = None,
    server: str | None = None,
    share: str | None = None,
) -> str:
    """拼装 POSIX 路径：{mount_root}/{relpath}。

    server/share 参与校验（须合法）但不进入 POSIX 路径（由 cifs 挂载提供）。
    """
    root = normalize_mount_root(mount_root)
    rel = normalize_relpath(relpath)
    if server is not None and str(server).strip():
        normalize_server(server)
    if share is not None and str(share).strip():
        normalize_share(share)
    return f"{root}/{rel}"


def parse_legacy_share_path(
    path: str | None,
    *,
    default_mount_root: str = DEFAULT_MOUNT_ROOT,
) -> dict[str, str] | None:
    """从旧 ledger_share_path 尽量拆出 mount_root + relpath。

    仅识别默认/已知 POSIX 挂载根前缀；gvfs/UNC 返回 None。
    """
    s = str(path or "").strip().replace("\\", "/")
    if not s or not s.startswith("/"):
        return None
    # gvfs
    if "gvfs" in s or "smb-share:" in s:
        return None
    root = normalize_mount_root(default_mount_root)
    if s == root:
        return {KEY_MOUNT_ROOT: root, KEY_RELPATH: "", KEY_SHARE_PATH: s}
    prefix = root + "/"
    if s.startswith(prefix):
        rel = s[len(prefix) :]
        try:
            rel_n = normalize_relpath(rel) if rel else ""
        except ValueError:
            return None
        return {
            KEY_MOUNT_ROOT: root,
            KEY_RELPATH: rel_n,
            KEY_SHARE_PATH: s if not rel_n else f"{root}/{rel_n}",
        }
    # 其它绝对路径：整段作为「仅旧路径」不可拆
    return None


def validate_structured_payload(payload: dict) -> dict[str, str]:
    """校验并返回规范化非密字段（可部分字段：仅改路径时）。

    若任一 smb 结构化键出现，则 server/share/relpath 最终须齐全（可与 cfg 合并后调用）。
    """
    out: dict[str, str] = {}
    if KEY_MOUNT_ROOT in payload:
        out[KEY_MOUNT_ROOT] = normalize_mount_root(payload.get(KEY_MOUNT_ROOT))
    if KEY_SERVER in payload:
        out[KEY_SERVER] = normalize_server(payload.get(KEY_SERVER))
    if KEY_SHARE in payload:
        out[KEY_SHARE] = normalize_share(payload.get(KEY_SHARE))
    if KEY_RELPATH in payload:
        out[KEY_RELPATH] = normalize_relpath(payload.get(KEY_RELPATH))
    if KEY_USERNAME in payload:
        out[KEY_USERNAME] = normalize_username(payload.get(KEY_USERNAME))
    return out


def merge_structured(cfg: dict, payload: dict) -> dict[str, str]:
    """合并 cfg 已有 + payload，得到完整结构化字段并拼装 path。"""
    # 是否触碰结构化
    touch = any(k in payload for k in (KEY_SERVER, KEY_SHARE, KEY_RELPATH, KEY_USERNAME, KEY_MOUNT_ROOT))
    # 也允许仅 legacy path
    if not touch and KEY_SHARE_PATH in payload:
        lsp = str(payload.get(KEY_SHARE_PATH) or "").strip()
        return {KEY_SHARE_PATH: lsp}

    if not touch:
        return {}

    server = payload[KEY_SERVER] if KEY_SERVER in payload else cfg.get(KEY_SERVER, "")
    share = payload[KEY_SHARE] if KEY_SHARE in payload else cfg.get(KEY_SHARE, "")
    relpath = payload[KEY_RELPATH] if KEY_RELPATH in payload else cfg.get(KEY_RELPATH, "")
    username = payload[KEY_USERNAME] if KEY_USERNAME in payload else cfg.get(KEY_USERNAME, "")
    mount_root = (
        payload[KEY_MOUNT_ROOT] if KEY_MOUNT_ROOT in payload else cfg.get(KEY_MOUNT_ROOT, DEFAULT_MOUNT_ROOT)
    )

    server_n = normalize_server(server)
    share_n = normalize_share(share)
    rel_n = normalize_relpath(relpath)
    root_n = normalize_mount_root(mount_root)
    user_n = normalize_username(username)
    path = assemble_ledger_share_path(
        mount_root=root_n, relpath=rel_n, server=server_n, share=share_n
    )
    return {
        KEY_SERVER: server_n,
        KEY_SHARE: share_n,
        KEY_RELPATH: rel_n,
        KEY_USERNAME: user_n,
        KEY_MOUNT_ROOT: root_n,
        KEY_SHARE_PATH: path,
    }


def cred_path() -> Path:
    return Path(os.environ.get("KANBAN_CIFS_CRED_PATH") or DEFAULT_CRED_PATH)


def password_set_on_disk(path: Path | None = None) -> bool:
    p = path or cred_path()
    try:
        if not p.is_file():
            return False
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        if line.strip().startswith("password=") and len(line.strip()) > len("password="):
            return True
    return False


def detect_mount_ok(mount_root: str | None = None, server: str | None = None) -> bool:
    """best-effort：findmnt 是否 cifs 且挂在 mount_root（可选匹配 server）。"""
    root = normalize_mount_root(mount_root or DEFAULT_MOUNT_ROOT)
    try:
        r = subprocess.run(
            ["findmnt", "-n", "-o", "FSTYPE,SOURCE", root],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return False
        line = (r.stdout or "").strip()
        if not line.lower().startswith("cifs"):
            return False
        if server and str(server).strip():
            return str(server).strip() in line
        return True
    except Exception:
        return False


def settings_public_view(cfg: dict) -> dict[str, Any]:
    """管理员 GET 用：结构化字段 + 探测；**永不**含 password。"""
    lsp = str(cfg.get(KEY_SHARE_PATH) or "").strip()
    server = str(cfg.get(KEY_SERVER) or "").strip()
    share = str(cfg.get(KEY_SHARE) or "").strip()
    relpath = str(cfg.get(KEY_RELPATH) or "").strip()
    username = str(cfg.get(KEY_USERNAME) or "").strip()
    mount_root = str(cfg.get(KEY_MOUNT_ROOT) or "").strip() or DEFAULT_MOUNT_ROOT
    legacy_only = False
    migrate_hint = ""

    if not any((server, share, relpath)) and lsp:
        parsed = parse_legacy_share_path(lsp, default_mount_root=mount_root)
        if parsed:
            mount_root = parsed.get(KEY_MOUNT_ROOT, mount_root)
            relpath = parsed.get(KEY_RELPATH, relpath)
            migrate_hint = "已从旧路径解析挂载根与相对路径；保存后写入结构化字段。"
        else:
            legacy_only = True
            migrate_hint = "当前为旧版完整路径（无法自动拆解）；可继续使用，或改填结构化字段后保存。"

    try:
        path_exists = bool(lsp) and os.path.exists(lsp)
    except Exception:
        path_exists = False

    out: dict[str, Any] = {
        KEY_SERVER: server,
        KEY_SHARE: share,
        KEY_RELPATH: relpath,
        KEY_USERNAME: username,
        KEY_MOUNT_ROOT: mount_root,
        KEY_SHARE_PATH: lsp,
        "ledger_path_exists": path_exists,
        "ledger_mount_ok": detect_mount_ok(mount_root, server or None),
        "ledger_smb_password_set": password_set_on_disk(),
        "ledger_legacy_path_only": legacy_only,
        "ledger_migrate_hint": migrate_hint,
    }
    # 铁律：绝不带 password
    assert "password" not in out
    assert "ledger_smb_password" not in out
    return out


def apply_script_path() -> str:
    """受控脚本路径：环境变量优先，否则仓内 deploy 脚本（部署后可装到 /usr/local/sbin）。"""
    env = os.environ.get("KANBAN_CIFS_APPLY_SCRIPT")
    if env:
        return env
    # 相对本文件：src/../deploy/linux/kanban-cifs-apply.sh
    here = Path(__file__).resolve().parents[1] / "deploy" / "linux" / "kanban-cifs-apply.sh"
    return str(here)


def should_apply_credentials(payload: dict) -> bool:
    """改 username 或显式提交非空 password 时才触发 apply。"""
    if KEY_USERNAME in payload and str(payload.get(KEY_USERNAME) or "").strip():
        # 仅当同时带了 password 或明确 apply 标志才真正改 cred
        pass
    pw = payload.get("ledger_smb_password")
    if pw is not None and str(pw) != "":
        return True
    if payload.get("ledger_smb_apply_creds") is True:
        return True
    # 改 username 且 password 留空：仍可重写 cred 的 username 行（密码保持）——需要脚本支持
    if KEY_USERNAME in payload and str(payload.get(KEY_USERNAME) or "").strip():
        return True
    return False


def run_cifs_apply(
    *,
    username: str,
    password: str | None,
    server: str,
    share: str,
    mount_root: str,
    dry_run: bool = False,
) -> str:
    """调用受控脚本；失败抛 RuntimeError（人话）。不经 shell。"""
    script = apply_script_path()
    if not Path(script).is_file() and not os.environ.get("KANBAN_CIFS_APPLY_SCRIPT"):
        # 允许测试注入假脚本
        raise RuntimeError(f"CIFS 应用脚本不存在：{script}（请安装 deploy/linux/kanban-cifs-apply.sh）")

    cmd = [
        script,
        "--cred-file",
        str(cred_path()),
        "--username",
        username or "",
        "--server",
        server or "",
        "--share",
        share or "",
        "--mount-root",
        mount_root or DEFAULT_MOUNT_ROOT,
    ]
    if password is not None and str(password) != "":
        cmd.extend(["--password", str(password)])
    if dry_run or os.environ.get("KANBAN_CIFS_DRY_RUN") == "1":
        cmd.append("--dry-run")
    # 测试 / 无 root：不 remount
    if os.environ.get("KANBAN_CIFS_SKIP_MOUNT") == "1":
        cmd.append("--skip-mount")
    # 生产：sudo -n 固定脚本（见 sudoers.d-kanban-cifs）；测试默认关
    if os.environ.get("KANBAN_CIFS_USE_SUDO") == "1":
        cmd = ["sudo", "-n", *cmd]

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"无法执行 CIFS 应用脚本：{e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("CIFS 应用脚本超时") from e

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:300]
        raise RuntimeError(err or f"CIFS 应用失败（退出码 {r.returncode}）")
    return (r.stdout or "").strip() or "ok"
