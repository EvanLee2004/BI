#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话密钥与 HMAC token（C：从 server 抽出）。"""
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


def make_token(sec: dict, user: str, now: float | None = None) -> str:
    now = time.time() if now is None else now
    payload = f"{user}|{int(now + SESSION_TTL)}".encode()
    b64 = base64.urlsafe_b64encode(payload)
    sig = hmac.new(bytes.fromhex(sec["cookie_key"]), b64, hashlib.sha256).hexdigest()
    return b64.decode() + "." + sig


def check_token_raw(sec: dict, token: str, now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    expect = hmac.new(bytes.fromhex(sec["cookie_key"]), b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        user, exp = base64.urlsafe_b64decode(b64.encode()).decode().split("|", 1)
    except (ValueError, TypeError):
        return None
    if float(exp) < now:
        return None
    return user or None


def check_token(sec: dict, token: str, now: float | None = None) -> str | None:
    return check_token_raw(sec, token, now)


def check_vsubject(sec: dict, token: str, now: float | None = None) -> str | None:
    return check_token_raw(sec, token, now)
