#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PMI中国AI 冒烟测试 —— 独立运行版（针对已启动的真实服务）

与 tests/test_smoke_*.py（pytest 进程内）互补：本脚本用纯 httpx 直连
一个「已 boot 的服务」（serve:app / uvicorn app.main:app），走真实网络路径，
用于代码冻结点后的端到端验证。

覆盖：
- 登录 + /auth/me
- 列项目 / 创建项目 / 详情 / 更新状态 / 统计
- 创建任务 / 看板状态变更 / 软删
- F-01 对象级鉴权：非成员 -> 403；不存在项目 -> 404；未认证 -> 401
- F-03 AI 项目隔离：非成员带他人 project_id -> 403（无需大模型）
- AI 助手对话 / inbound/agent：仅当 SMOKE_LIVE_AI=1 时真实调用大模型，否则 SKIP

用法（在 backend/ 目录下，用 managed venv）：
    ../../venv/Scripts/python scripts/smoke_run.py
    ../../venv/Scripts/python scripts/smoke_run.py http://127.0.0.1:8000
    SMOKE_LIVE_AI=1 ../../venv/Scripts/python scripts/smoke_run.py

退出码：0 = 无 FAIL（SKIP 不计入失败）；1 = 存在 FAIL。
"""
import argparse
import asyncio
import os
import sys
import uuid

import httpx


BASE = "/api/v1"
_LIVE_AI = os.environ.get("SMOKE_LIVE_AI", "") in ("1", "true", "True")

# 结果收集
RESULTS = []


def record(name: str, ok: bool, detail: str = "", skip: bool = False):
    tag = "SKIP" if skip else ("PASS" if ok else "FAIL")
    RESULTS.append((tag, name, detail))
    line = f"[{tag}] {name}"
    if detail:
        line += f"  -- {detail}"
    print(line, flush=True)


async def _reg_login(client: httpx.AsyncClient, suffix: str) -> str:
    email = f"smkrun_{suffix}@example.com"
    username = f"smkrun_{suffix}"
    pw = "Smoke123!"
    await client.post(
        f"{BASE}/auth/register",
        json={"email": email, "username": username,
              "password": pw, "full_name": f"冒烟{suffix}"},
    )
    r = await client.post(f"{BASE}/auth/login", json={"username": username, "password": pw})
    if r.status_code != 200:
        raise RuntimeError(f"登录失败 {r.status_code}: {r.text}")
    return r.json()["access_token"]


async def _create_project(client: httpx.AsyncClient, token: str, name: str) -> str:
    r = await client.post(
        f"{BASE}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "priority": 3},
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"建项目失败 {r.status_code}: {r.text}")
    return r.json()["id"]


async def run(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0, follow_redirects=True) as c:

        # ---------- 认证 ----------
        tok_a = await _reg_login(c, "a")
        ha = {"Authorization": f"Bearer {tok_a}"}
        r = await c.get(f"{BASE}/auth/me", headers=ha)
        record("登录 + /auth/me", r.status_code == 200 and bool(r.json().get("id")),
               f"status={r.status_code}")

        # ---------- 项目生命周期 ----------
        pid = await _create_project(c, tok_a, "冒烟项目A")
        r = await c.get(f"{BASE}/projects", headers=ha)
        in_list = r.status_code == 200 and any(x["id"] == pid for x in r.json()["items"])
        record("列项目含新建项目", in_list, f"status={r.status_code}")

        r = await c.get(f"{BASE}/projects/{pid}", headers=ha)
        record("获取项目详情", r.status_code == 200 and r.json().get("name") == "冒烟项目A",
               f"status={r.status_code}")

        r = await c.put(f"{BASE}/projects/{pid}", headers=ha, json={"status": "active"})
        record("更新项目状态", r.status_code == 200 and r.json().get("status") == "active",
               f"status={r.status_code}")

        r = await c.get(f"{BASE}/projects/{pid}/statistics", headers=ha)
        record("项目统计", r.status_code == 200 and "task_count" in r.json(),
               f"status={r.status_code}")

        # ---------- 任务 + 看板 ----------
        rt = await c.post(
            f"{BASE}/tasks", headers=ha,
            json={"project_id": pid, "name": "实现登录", "status": "todo", "priority": 2},
        )
        if rt.status_code not in (200, 201):
            record("创建任务", False, f"status={rt.status_code}: {rt.text[:200]}")
            tid = None
        else:
            tid = rt.json()["id"]
            record("创建任务", bool(rt.json().get("wbs_code")), f"wbs={rt.json().get('wbs_code')}")
        if tid:
            r = await c.put(f"{BASE}/tasks/{tid}", headers=ha,
                            json={"status": "done", "progress": 100})
            record("看板状态变更(done)", r.status_code == 200 and r.json().get("status") == "done",
                   f"status={r.status_code}")
            r = await c.delete(f"{BASE}/tasks/{tid}", headers=ha)
            record("任务软删", r.status_code == 200, f"status={r.status_code}")

        # ---------- F-01 对象级鉴权 ----------
        tok_b = await _reg_login(c, "b")  # B 非 A 项目成员
        hb = {"Authorization": f"Bearer {tok_b}"}
        r = await c.get(f"{BASE}/projects/{pid}", headers=hb)
        record("F-01 非成员访问他人项目->403", r.status_code == 403, f"status={r.status_code}")
        # 注意：非成员得到 403 意味着「项目存在」被泄露；真正不泄露的是「不存在项目」->404
        fake_id = str(uuid.uuid4())
        r = await c.get(f"{BASE}/projects/{fake_id}", headers=ha)
        record("F-01 不存在项目->404(非403)", r.status_code == 404,
               f"status={r.status_code}")
        r = await c.get(f"{BASE}/projects/{pid}")  # 无 token
        record("F-01 未认证->401", r.status_code == 401, f"status={r.status_code}")

        # ---------- F-03 AI 项目隔离 ----------
        r = await c.post(
            f"{BASE}/openclaw/assistant/chat", headers=hb,
            json={"message": "读一下那个项目", "project_id": pid},
        )
        record("F-03 非成员带他人project_id->403", r.status_code == 403, f"status={r.status_code}")

        if _LIVE_AI:
            r = await c.post(
                f"{BASE}/openclaw/assistant/chat", headers=ha,
                json={"message": "本项目进度", "project_id": pid},
            )
            record("F-03 成员带自己project_id->200(真实LLM)",
                   r.status_code == 200, f"status={r.status_code}")
            r = await c.post(
                f"{BASE}/integrations/inbound/agent", headers=ha,
                json={"provider": "dingtalk", "project_id": pid,
                      "content": "会议纪要：下周三前完成登录联调"},
            )
            record("inbound/agent(真实LLM)", r.status_code == 200, f"status={r.status_code}")
        else:
            record("F-03 成员AI对话 / inbound(需真实LLM)", True,
                   "SKIP：设 SMOKE_LIVE_AI=1 启用", skip=True)


def main():
    ap = argparse.ArgumentParser(description="PMI中国AI 端到端冒烟测试（独立运行版）")
    ap.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000",
                   help="已启动服务地址，默认 http://127.0.0.1:8000")
    args = ap.parse_args()

    print(f"=== PMI中国AI 冒烟测试 @ {args.base_url} ===")
    print(f"=== SMOKE_LIVE_AI={_LIVE_AI} ===\n")
    try:
        asyncio.run(run(args.base_url))
    except Exception as e:  # noqa: BLE001
        record("运行期异常", False, str(e))

    print("\n=== 汇总 ===")
    n_pass = sum(1 for t, _, _ in RESULTS if t == "PASS")
    n_fail = sum(1 for t, _, _ in RESULTS if t == "FAIL")
    n_skip = sum(1 for t, _, _ in RESULTS if t == "SKIP")
    print(f"PASS={n_pass}  FAIL={n_fail}  SKIP={n_skip}")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
