# -*- coding: utf-8 -*-
"""3.7.3 候选预热 / 切流纯函数。"""

from __future__ import annotations

import unittest

from publish_bluegreen import (
    candidate_health_ok,
    cutover_plan,
    parse_upstream_port,
    render_upstream_conf,
    should_reset_git_on_candidate_fail,
)


class TestCandidateHealth(unittest.TestCase):
    def test_default_requires_align(self):
        """OPS-002/TEST-005：默认 require_runtime_align=True，仅 200 不够。"""
        ok, reason = candidate_health_ok(health_code=200)
        self.assertFalse(ok, reason)

    def test_loose_http_only(self):
        ok, reason = candidate_health_ok(health_code=200, require_runtime_align=False)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "ok_http_200")

    def test_bad_health(self):
        ok, reason = candidate_health_ok(health_code=503, require_runtime_align=False)
        self.assertFalse(ok)
        self.assertIn("health_not_200", reason)

    def test_strict_version_mismatch(self):
        ok, reason = candidate_health_ok(
            health_code=200,
            runtime_version="3.7.2",
            disk_version="3.7.3",
            runtime_commit="abc",
            disk_commit="abc",
            runtime_pid=1,
            require_runtime_align=True,
        )
        self.assertFalse(ok)
        self.assertIn("version_mismatch", reason)

    def test_strict_ok_when_aligned(self):
        ok, reason = candidate_health_ok(
            health_code=200,
            runtime_version="3.7.16",
            disk_version="3.7.16",
            runtime_commit="abc1234",
            disk_commit="abc1234",
            runtime_pid=42,
        )
        self.assertTrue(ok, reason)


class TestUpstreamRender(unittest.TestCase):
    def test_roundtrip(self):
        text = render_upstream_conf(8019)
        self.assertIn("127.0.0.1:8019", text)
        self.assertEqual(parse_upstream_port(text), 8019)

    def test_invalid_port(self):
        with self.assertRaises(ValueError):
            render_upstream_conf(0)


class TestCutoverPlan(unittest.TestCase):
    def test_abort_on_fail(self):
        plan = cutover_plan(candidate_ok=False, nginx_cutover=True)
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["steps"][0]["action"], "kill_candidate")
        self.assertEqual(plan["steps"][1]["action"], "abort_keep_primary")

    def test_warm_reload(self):
        plan = cutover_plan(candidate_ok=True, nginx_cutover=False)
        self.assertTrue(plan["ok"])
        actions = [s["action"] for s in plan["steps"]]
        self.assertEqual(actions, ["reload_primary", "verify_primary", "kill_candidate"])

    def test_nginx_cutover_steps(self):
        plan = cutover_plan(candidate_ok=True, nginx_cutover=True)
        self.assertTrue(plan["ok"])
        actions = [s["action"] for s in plan["steps"]]
        self.assertIn("write_upstream", actions)
        self.assertIn("nginx_reload", actions)
        self.assertEqual(actions[0], "write_upstream")
        self.assertEqual(actions[0:2], ["write_upstream", "nginx_reload"])


class TestGitResetPolicy(unittest.TestCase):
    def test_reset_when_pulled_and_failed(self):
        self.assertTrue(
            should_reset_git_on_candidate_fail(
                pulled=True, candidate_ok=False, prev_commit="abc123"
            )
        )

    def test_no_reset_when_ok(self):
        self.assertFalse(
            should_reset_git_on_candidate_fail(
                pulled=True, candidate_ok=True, prev_commit="abc123"
            )
        )


if __name__ == "__main__":
    unittest.main()
