"""
覆盖测试：全量 Agent 结构化 ITTO 统一字段 + enabled 过滤 + 旧格式兼容。

验证点：
① 注册中心所有 Agent（领域 + PMBOK/CPMAI）的 get_structured_itto 都返回
   含 {key,label,optional,enabled,kind,template_prompt} 六项字段，且 enabled 为布尔。
② prepare / run_material 对 enabled=False 的项进行过滤（输入/工具/输出）。
③ 兼容旧字符串列表与含 enabled 的 dict 覆盖。

[Backend Test | ITTO enabled filtering | Compatibility]
"""
import asyncio
import re
import pytest

from app.services.ai import agent_registry as reg
from app.services.ai import agent_materials as am
from app.services.ai.pmbok_agents import itto_to_structured
from app.services.ai.agent_registry import _norm_item, get_structured_itto

_UNIFIED_KEYS = {"key", "label", "optional", "enabled", "kind", "template_prompt"}


def test_all_registered_agents_have_unified_itto():
    """① 全量 Agent：每项都有统一六项字段，enabled 为布尔且默认 True。"""
    agents = reg.list_agents()
    assert len(agents) >= 75, f"注册 Agent 数量应 >=75，实际 {len(agents)}"
    seen = 0
    for a in agents:
        aid = a["id"]
        sitto = get_structured_itto(aid)
        for cat in ("inputs", "tools", "outputs"):
            for it in sitto[cat]:
                assert set(it.keys()) == _UNIFIED_KEYS, f"{aid}/{cat} 字段不符: {set(it.keys())}"
                assert isinstance(it["enabled"], bool), f"{aid}/{cat} enabled 非布尔"
                assert it["enabled"] is True, f"{aid}/{cat} 默认 enabled 应为 True"
                assert "key" in it and it["key"], f"{aid}/{cat} 缺 key"
        seen += 1
    assert seen == len(agents)
    # 抽样确认：领域 Agent、PMBOK 过程、第8版原则/绩效域/裁剪、CPMAI 阶段、可信AI
    samples = ["report", "pmbok:4.1", "pmbok:P0", "pmbok:D-Gov",
               "pmbok:T1", "pmbok:C1", "pmbok:TA1"]
    for s in samples:
        assert get_structured_itto(s)["inputs"], f"{s} 应至少有输入项"


def test_optional_independent_of_enabled():
    """optional（必需/可选）与 enabled（是否启用）相互独立。"""
    inp = _norm_item({"label": "L", "optional": True, "enabled": False}, "input")
    assert inp["optional"] is True and inp["enabled"] is False
    inp2 = _norm_item({"label": "L2", "optional": False, "enabled": True}, "input")
    assert inp2["optional"] is False and inp2["enabled"] is True


def test_compat_old_string_list_and_dict_override():
    """③ 兼容：旧字符串列表 → 结构化；dict 覆盖 enabled 被保留。"""
    # 旧字符串输入列表
    s_in = itto_to_structured("input", ["商业论证", "项目章程"])
    assert s_in[0]["enabled"] is True and s_in[0]["kind"] == "file"
    # 旧字符串工具列表
    s_tool = itto_to_structured("tool", ["专家判断"])
    assert s_tool[0]["enabled"] is True and s_tool[0]["kind"] == "technique"
    # dict 覆盖：显式禁用某工具
    d_tool = itto_to_structured("tool", [{"key": "k", "label": "L", "enabled": False}])
    assert d_tool[0]["enabled"] is False
    # _norm_item 旧字符串输出
    n_out = _norm_item("报告文档", "output")
    assert n_out["enabled"] is True and n_out["kind"] == "file"
    # _norm_item dict 禁用输出
    n_out2 = _norm_item({"label": "O", "enabled": False}, "output")
    assert n_out2["enabled"] is False


def test_prepare_filters_disabled_inputs():
    """② prepare：enabled=False 的输入被过滤，且不计入缺失清单。"""
    fake = {
        "inputs": [
            {"key": "i1", "label": "I1", "optional": False, "enabled": True,
             "kind": "file", "template_prompt": ""},
            {"key": "i2", "label": "I2", "optional": False, "enabled": False,
             "kind": "file", "template_prompt": ""},
        ],
        "tools": [
            {"key": "t1", "label": "T1", "optional": False, "enabled": True,
             "kind": "technique", "template_prompt": ""},
        ],
        "outputs": [
            {"key": "o1", "label": "O1", "optional": False, "enabled": True,
             "kind": "file", "template_prompt": ""},
        ],
    }
    orig = am.get_structured_itto
    am.get_structured_itto = lambda aid: fake
    try:
        res = asyncio.run(am.prepare(None, "x", None))
    finally:
        am.get_structured_itto = orig
    keys = [i["key"] for i in res["inputs"]]
    assert "i2" not in keys, "禁用输入不应出现在 prepare 结果"
    assert "i1" in keys
    assert "i2" not in res["missing_required"], "禁用输入不应计入缺失"
    assert "o1" == res["outputs"][0]["key"]
    assert "t1" == res["tools"][0]["key"]


def test_run_material_filters_disabled_items():
    """② run_material：禁用 输入/工具/输出 均被过滤出运行。"""
    captured = {}

    async def fake_llm(prompt, *a, **k):
        captured["prompt"] = prompt
        return "# O1\n\n生成内容"

    fake = {
        "inputs": [
            {"key": "i1", "label": "I1", "optional": False, "enabled": True,
             "kind": "file", "template_prompt": ""},
            {"key": "i2", "label": "I2", "optional": False, "enabled": False,
             "kind": "file", "template_prompt": ""},
        ],
        "tools": [
            {"key": "t1", "label": "T1", "optional": False, "enabled": True,
             "kind": "technique", "template_prompt": ""},
            {"key": "t2", "label": "T2", "optional": False, "enabled": False,
             "kind": "technique", "template_prompt": ""},
        ],
        "outputs": [
            {"key": "o1", "label": "O1", "optional": False, "enabled": True,
             "kind": "file", "template_prompt": ""},
            {"key": "o2", "label": "O2", "optional": False, "enabled": False,
             "kind": "file", "template_prompt": ""},
        ],
    }
    orig_sitto = am.get_structured_itto
    orig_llm = am._llm
    am.get_structured_itto = lambda aid: fake
    am._llm = fake_llm
    try:
        res = asyncio.run(am.run_material(
            None, "x", None,
            input_refs={"i1": "r1", "i2": "r2"},
            selected_tools=[], user_input="",
        ))
    finally:
        am.get_structured_itto = orig_sitto
        am._llm = orig_llm

    assert "I2" not in captured["prompt"], "禁用输入不应进入提示"
    assert "I1" in captured["prompt"]
    assert "T2" not in captured["prompt"], "禁用工具不应进入提示"
    assert "T1" in captured["prompt"]
    # 仅启用的输出被生成
    assert len(res["outputs"]) == 1, f"应仅 1 个输出，实际 {len(res['outputs'])}"
    assert "O1" in res["outputs"][0]["title"]


_RAW_PREFIX_PAIRS = [
    ("4.1", "pmbok:4.1"), ("P0", "pmbok:P0"), ("C1", "pmbok:C1"),
    ("TA1", "pmbok:TA1"), ("T1", "pmbok:T1"), ("D-Gov", "pmbok:D-Gov"),
]


def test_raw_id_and_pmbok_prefix_map_to_same_itto():
    """原始 proc.id（如 '4.1'）与 'pmbok:4.1' 映射到同一份 ITTO。"""
    for raw, pref in _RAW_PREFIX_PAIRS:
        s_raw = get_structured_itto(raw)
        s_pref = get_structured_itto(pref)
        assert s_raw["inputs"], f"{raw} 应解析到非空输入"
        assert s_raw == s_pref, f"{raw} 与 {pref} 应映射到同一 ITTO"
        # 每项都应带 enabled（默认 True）
        for cat in ("inputs", "tools", "outputs"):
            for it in s_raw[cat]:
                assert "enabled" in it, f"{raw}/{cat} 缺 enabled"


def test_override_compat_raw_and_prefixed():
    """override 兼容 raw 与 pmbok: 两种 key：任一写法都能命中同一份覆盖。"""
    import app.api.v1.ai_routes.agent as agent_mod
    from unittest import mock

    base = {
        "inputs_struct": [{"key": "x", "label": "X", "optional": False,
                           "enabled": False, "kind": "file", "template_prompt": ""}],
        "tools_struct": [], "outputs_struct": [],
    }
    # 场景 A：覆盖以 raw '4.1' 存储，用 'pmbok:4.1' 读取
    fake_a = {"4.1": dict(base)}
    with mock.patch.object(agent_mod, "_load_overrides", lambda: fake_a):
        s_a = get_structured_itto("pmbok:4.1")
    assert s_a["inputs"][0]["key"] == "x"
    assert s_a["inputs"][0]["enabled"] is False, "override 的 enabled=False 应被保留并过滤"

    # 场景 B：覆盖以 'pmbok:4.1' 存储，用 raw '4.1' 读取
    fake_b = {"pmbok:4.1": dict(base)}
    with mock.patch.object(agent_mod, "_load_overrides", lambda: fake_b):
        s_b = get_structured_itto("4.1")
    assert s_b["inputs"][0]["key"] == "x"
    assert s_b["inputs"][0]["enabled"] is False
