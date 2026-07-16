#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话密钥与 HMAC token（C：从 server 抽出）。

任务书46·1：token 载荷含「密码版本」；改密后旧会话 check 失败 → 401。
兼容旧 token（无版本字段）→ 视为版本 0。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import loaders
from app_state import SESSION_TTL


def secret_path(cfg, root=None) -> Path:
    return loaders.data_dir(cfg, root) / "管理员密钥.json"


def load_or_init_secret(cfg, root=None) -> dict:
    """读/建会话签名密钥。旧文件可能还带 salt/pw_hash（v7.x），读时保留不删。"""
    p = secret_path(cfg, root)
    if p.exists():
        try:
            sec = json.loads(p.read_text(encoding="utf-8"))
            if sec.get("cookie_key"):
                return sec
        except (OSError, ValueError):
            pass
    sec = {"cookie_key": os.urandom(32).hex()}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[server] 已生成会话密钥文件：{p}（账号口令见 数据/看板账号.json）")
    return sec


def save_secret(cfg, root, sec: dict) -> None:
    p = secret_path(cfg, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")


def make_token(sec: dict, user: str, now: float | None = None, pw_ver: int = 0) -> str:
    """签发会话：user|exp|pw_ver。pw_ver=账号密码版本（改密踢会话）。"""
    now = time.time() if now is None else now
    try:
        ver = int(pw_ver or 0)
    except (TypeError, ValueError):
        ver = 0
    payload = f"{user}|{int(now + SESSION_TTL)}|{ver}".encode()
    b64 = base64.urlsafe_b64encode(payload)
    sig = hmac.new(bytes.fromhex(sec["cookie_key"]), b64, hashlib.sha256).hexdigest()
    return b64.decode() + "." + sig


def check_token_raw(sec: dict, token: str, now: float | None = None) -> tuple[str, int] | None:
    """校验签名与过期；返回 (user, pw_ver) 或 None。旧 token 无版本字段 → pw_ver=0。"""
    now = time.time() if now is None else now
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    expect = hmac.new(bytes.fromhex(sec["cookie_key"]), b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        parts = base64.urlsafe_b64decode(b64.encode()).decode().split("|")
        if len(parts) == 2:
            user, exp = parts
            ver = 0
        elif len(parts) >= 3:
            user, exp, ver_s = parts[0], parts[1], parts[2]
            try:
                ver = int(ver_s)
            except (TypeError, ValueError):
                ver = 0
        else:
            return None
    except (ValueError, TypeError):
        return None
    if float(exp) < now:
        return None
    if not user:
        return None
    return user, ver


def check_token(sec: dict, token: str, now: float | None = None) -> str | None:
    """仅返回用户名（兼容旧调用）。密码版本校验由 server 层结合账号表完成。"""
    r = check_token_raw(sec, token, now)
    return r[0] if r else None


def check_vsubject(sec: dict, token: str, now: float | None = None) -> str | None:
    return check_token(sec, token, now)


def token_pw_ver(sec: dict, token: str, now: float | None = None) -> int | None:
    """取 token 内密码版本；无效 token → None。"""
    r = check_token_raw(sec, token, now)
    return r[1] if r else None
