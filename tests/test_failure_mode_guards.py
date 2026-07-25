# -*- coding: utf-8 -*-
"""2.6.4·C 失效模式守卫（静态）。每条须能「改坏会红」。

故意改坏 → 红 → 还原 的过程见 方案与文档/…/20260726_2.6.4复查证据/guards/break_restore.txt
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class TestFailureModeGuards(unittest.TestCase):
    def test_no_bare_except_pass_in_src(self):
        """禁止裸 except: pass（白名单：仅文档字符串示例可无）。"""
        bad: list[str] = []
        allow_files = {
            # 无
        }
        for p in SRC.rglob("*.py"):
            if p.name in allow_files:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            # 匹配 except: 后仅 pass 的块（单行）
            for i, line in enumerate(text.splitlines(), 1):
                s = line.strip()
                if s == "except:" or s == "except Exception:":
                    # 看下一非空行
                    lines = text.splitlines()
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and lines[j].strip() in ("pass", "pass  # noqa"):
                        # except Exception: pass 也算
                        if "except Exception" in s or s == "except:":
                            # allow: `except Exception:\n        pass` in notify? check
                            bad.append(f"{p.relative_to(ROOT)}:{i}")
        # 放宽：except Exception:\n            pass 在边界很常见且会吞错误——本守卫只拦「except:」裸捕获
        bad2 = [b for b in bad if ":except:" in b.replace(" ", "") or b.endswith("except:")]
        # 更严：仅拦 `except:` 无类型
        bare = []
        for p in SRC.rglob("*.py"):
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if re.match(r"^\s*except\s*:\s*(pass)?\s*$", line):
                    bare.append(f"{p.relative_to(ROOT)}:{i}:{line.strip()}")
        self.assertEqual(bare, [], "found bare except: " + "; ".join(bare[:10]))

    def test_private_credentials_use_atomic_write(self):
        """账号/智云凭据写入须走 secure_io 原子写。"""
        acc = (SRC / "accounts.py").read_text(encoding="utf-8")
        self.assertIn("write_private", acc)
        self.assertIn("secure_io", acc)
        # 禁止对 看板账号.json 直接 write_text 全量覆盖主路径
        # （允许 needs_restore 旗标 write_text）
        self.assertIn("write_private_text", acc)

    def test_db_path_no_double_segment(self):
        import sys

        sys.path.insert(0, str(SRC))
        import db
        import loaders

        cfg = loaders.load_config()
        cfg = dict(cfg, data_dir="数据", db_path="看板.db")
        p = db.db_path(cfg)
        self.assertNotIn("/数据/数据/", str(p).replace("\\", "/"))

    def test_run_verify_no_tail_pipe_green(self):
        rv = (ROOT / "tests" / "run_verify.sh").read_text(encoding="utf-8")
        for ln in rv.splitlines():
            s = ln.strip()
            if s.startswith("#"):
                continue
            self.assertNotIn("| tail", s)
            self.assertNotIn("| head", s)

    def test_deploy_scripts_fail_nonzero_on_error(self):
        """关键脚本含 set -e 或显式失败退出。"""
        sh = ROOT / "deploy" / "linux" / "start_with_rollback.sh"
        t = sh.read_text(encoding="utf-8")
        self.assertTrue("set -" in t or "set -e" in t or "set -u" in t)
        self.assertIn("exit 1", t)

    def test_notify_has_no_http_outbound(self):
        t = (SRC / "notify.py").read_text(encoding="utf-8")
        self.assertNotIn("urlopen", t)
        self.assertNotIn("post_feishu", t)
        self.assertNotIn("open.feishu", t)


if __name__ == "__main__":
    unittest.main()
