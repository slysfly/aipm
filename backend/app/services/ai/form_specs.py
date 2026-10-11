"""
「AI 帮我填」表单字段规格表（单一事实来源）。

存在意义
--------
原实现把「表单里有哪些字段、每个字段允许什么取值」完全交给大模型自由发挥，
prompt 里只有一句「字段名使用与输入一致的英文/中文名」。这同时导致两个问题：

【慢】模型不知道要填几个字段、每个值该多长，于是倾向输出长篇大论，
      2000 max_tokens 经常被顶满；而输出 token 是串行生成的，是端到端延迟的
      主要构成。
【不准】模型可能返回
      - 表单里不存在的 key（antd Form 会静默忽略，用户以为填了其实没填）
      - 枚举的中文标签（优先级返回「高」，而 Select 的 value 是 1/3/5，回填后显示空白）
      - 编造的真实编号（assignee_id="张三"、project_id="p_001"）
      - 非法日期 / 超范围数字

本模块把每个 form_type 的字段契约显式声明出来，用于：
1. 生成「白名单式」prompt —— 只允许输出这些 key、这些取值，输出量自然收敛；
2. 对模型输出做校验与强制类型转换（validate_suggestions）后才允许回填。

设计约定
--------
- `kind` 决定校验与转换策略；
- `ai="never"` 表示该字段是系统内真实编号 / 外键，**禁止 AI 填写**（不进入 prompt，
  输出中若出现也直接丢弃）；
- 非文本字段（枚举/数字/日期）只有在「当前为空」或「当前值等于默认值」时才允许
  覆盖 —— 否则用户在编辑态点一下 AI 就会被改掉状态/优先级，属于典型误伤。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# 允许被 AI 改写的「自由文本」类字段：这类字段可以做专业润色
_REFINABLE_KINDS = {"text", "long_text"}

_DATE_PATTERNS = (
    re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$"),
    re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$"),
    re.compile(r"^(\d{4})(\d{2})(\d{2})$"),
)

_TRUE_WORDS = {"true", "yes", "是", "1", "y"}


@dataclass(frozen=True)
class FieldSpec:
    """单个表单字段的契约。"""

    key: str
    kind: str  # text | long_text | enum | int_enum | number | int | date | ref
    label: str = ""
    max_len: int = 0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    # (value, label) —— value 是回填表单用的真实取值
    options: Tuple[Tuple[Any, str], ...] = ()
    ai: str = "fill"  # fill | never
    default: Any = None
    aliases: Tuple[str, ...] = ()
    hint: str = ""
    # 该字段是否允许在非空时被润色覆盖（默认仅文本类允许）
    refine: Optional[bool] = None

    @property
    def is_dynamic_enum(self) -> bool:
        """取值来自运行时（如项目类型由数据库维护），需由前端/调用方传入。"""
        return self.kind in ("enum", "int_enum") and not self.options


@dataclass(frozen=True)
class FormSpec:
    form_type: str
    label: str
    fields: Tuple[FieldSpec, ...] = ()
    required: Tuple[str, ...] = ()

    def field_map(self) -> Dict[str, FieldSpec]:
        return {f.key: f for f in self.fields}


# ---------------------------------------------------------------------------
# 表单定义（与前端 Projects.tsx / Tasks.tsx 的 Form.Item name 一一对应）
# ---------------------------------------------------------------------------

PROJECT_STATUS_OPTIONS: Tuple[Tuple[Any, str], ...] = (
    ("planning", "规划"),
    ("active", "进行中"),
    ("done", "已完成"),
    ("archived", "已归档"),
)

PROJECT_PRIORITY_OPTIONS: Tuple[Tuple[Any, str], ...] = (
    (1, "高"),
    (3, "中"),
    (5, "低"),
)

TASK_STATUS_OPTIONS: Tuple[Tuple[Any, str], ...] = (
    ("backlog", "待办"),
    ("todo", "待开始"),
    ("in_progress", "进行中"),
    ("in_review", "评审中"),
    ("testing", "测试中"),
    ("done", "已完成"),
    ("cancelled", "已取消"),
)


_PROJECT_FIELDS: Tuple[FieldSpec, ...] = (
    FieldSpec(
        key="name",
        kind="text",
        label="项目名称",
        max_len=60,
        aliases=("项目名称", "项目名", "title", "project_name"),
        hint="简洁、可识别，例如「智慧园区门禁改造项目」",
    ),
    FieldSpec(
        key="description",
        kind="long_text",
        label="描述",
        max_len=200,
        aliases=("描述", "项目描述", "简介", "desc"),
        hint="一句话说清目标 + 范围 + 周期",
    ),
    FieldSpec(
        key="status",
        kind="enum",
        label="状态",
        options=PROJECT_STATUS_OPTIONS,
        default="planning",
        aliases=("状态", "项目状态"),
        hint="新项目通常是 planning",
        refine=False,  # 不允许 AI 改状态，避免把新建项目的 planning 改成 active
    ),
    FieldSpec(
        key="priority",
        kind="int_enum",
        label="优先级",
        options=PROJECT_PRIORITY_OPTIONS,
        default=3,
        aliases=("优先级",),
        hint="1=高 3=中 5=低",
    ),
    FieldSpec(
        key="project_type",
        kind="enum",
        label="项目类型",
        aliases=("项目类型", "类型", "方法论"),
        hint="必须从给定可选值中选；无法判断就省略该字段",
    ),
    FieldSpec(
        key="industry_type",
        kind="text",
        label="行业",
        max_len=20,
        aliases=("行业", "所属行业", "industry"),
        hint="例如 IT软件 / 金融 / 制造 / 建筑",
    ),
    FieldSpec(
        key="budget",
        kind="number",
        label="预算",
        min_value=0,
        max_value=1_000_000_000,
        aliases=("预算", "预算金额", "budget"),
        hint="人民币金额，无依据就省略",
    ),
    FieldSpec(
        key="start_date",
        kind="date",
        label="开始日期",
        aliases=("开始日期", "计划开始", "start"),
        hint="无依据就省略",
    ),
    FieldSpec(
        key="end_date",
        kind="date",
        label="结束日期",
        aliases=("结束日期", "计划结束", "end"),
        hint="必须晚于开始日期",
    ),
)

_TASK_FIELDS: Tuple[FieldSpec, ...] = (
    FieldSpec(key="project_id", kind="ref", label="所属项目", ai="never"),
    FieldSpec(key="sprint_id", kind="ref", label="所属 Sprint", ai="never"),
    FieldSpec(
        key="name",
        kind="text",
        label="任务名称",
        max_len=60,
        aliases=("任务名称", "任务名", "title"),
        hint="以动词开头的可交付项，例如「完成登录模块开发」",
    ),
    FieldSpec(
        key="description",
        kind="long_text",
        label="描述",
        max_len=200,
        aliases=("描述", "任务描述", "desc"),
        hint="验收标准 + 关键步骤",
    ),
    FieldSpec(
        key="status",
        kind="enum",
        label="状态",
        options=TASK_STATUS_OPTIONS,
        default="todo",
        aliases=("状态", "任务状态"),
        refine=False,
    ),
    FieldSpec(
        key="priority",
        kind="int",
        label="优先级",
        min_value=1,
        max_value=5,
        default=3,
        aliases=("优先级",),
        hint="1~5 的整数，1 最高",
    ),
    FieldSpec(key="assignee_id", kind="ref", label="负责人ID", ai="never"),
    FieldSpec(
        key="planned_start",
        kind="date",
        label="计划开始",
        aliases=("计划开始", "开始日期"),
    ),
    FieldSpec(
        key="planned_end",
        kind="date",
        label="计划结束",
        aliases=("计划结束", "结束日期"),
    ),
    FieldSpec(
        key="estimated_hours",
        kind="number",
        label="预估工时",
        min_value=0,
        max_value=1000,
        aliases=("预估工时", "工时", "estimated_hours"),
        hint="单位小时，无依据就省略",
    ),
)


FORM_SPECS: Dict[str, FormSpec] = {
    "project": FormSpec(
        form_type="project",
        label="项目",
        fields=_PROJECT_FIELDS,
        required=("name",),
    ),
    "task": FormSpec(
        form_type="task",
        label="任务",
        fields=_TASK_FIELDS,
        required=("name",),
    ),
}


def get_form_spec(form_type: str) -> Optional[FormSpec]:
    return FORM_SPECS.get((form_type or "").strip().lower())


def blocked_keys(spec: FormSpec) -> List[str]:
    """表单中存在、但禁止 AI 填写的字段（真实编号 / 外键）。"""
    return [f.key for f in spec.fields if f.ai == "never"]


# ---------------------------------------------------------------------------
# 运行时取值注入（如 project_type 由数据库维护，前端随请求传入合法 code）
# ---------------------------------------------------------------------------

def resolve_fields(
    spec: FormSpec,
    dynamic_options: Optional[Dict[str, Sequence[Any]]] = None,
) -> List[FieldSpec]:
    """把运行时枚举取值合并进字段规格。

    dynamic_options 形如 {"project_type": ["it_software", "construction"]}
    或 {"project_type": [{"value": "x", "label": "y"}]}。
    """
    dynamic_options = dynamic_options or {}
    out: List[FieldSpec] = []
    for f in spec.fields:
        if f.ai == "never":
            continue
        if f.is_dynamic_enum:
            raw = dynamic_options.get(f.key) or []
            opts: List[Tuple[Any, str]] = []
            for item in raw:
                if isinstance(item, dict):
                    val = item.get("value", item.get("code"))
                    lab = item.get("label", item.get("name", ""))
                    if val is not None:
                        opts.append((val, str(lab or val)))
                elif item is not None:
                    opts.append((item, str(item)))
            if not opts:
                # 运行时没给出合法取值 —— 直接不向模型暴露该字段，避免瞎编
                continue
            out.append(
                FieldSpec(
                    key=f.key,
                    kind=f.kind,
                    label=f.label,
                    options=tuple(opts),
                    aliases=f.aliases,
                    hint=f.hint,
                    default=f.default,
                    refine=f.refine,
                )
            )
            continue
        out.append(f)
    return out


# ---------------------------------------------------------------------------
# Prompt 构造
# ---------------------------------------------------------------------------

def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return ""
    try:
        if float(value).is_integer():
            return f"{int(value):,}"
    except (TypeError, ValueError):
        return ""
    return f"{value:g}"


def _describe_field(f: FieldSpec) -> str:
    if f.kind in ("enum", "int_enum"):
        opts = "|".join(str(v) for v, _ in f.options)
        desc = f"单选，只能取 {opts}"
    elif f.kind == "date":
        desc = "日期，格式 YYYY-MM-DD"
    elif f.kind in ("number", "int"):
        lo, hi = _fmt_num(f.min_value), _fmt_num(f.max_value)
        rng = f"，范围 {lo}~{hi}" if (lo or hi) else ""
        desc = ("整数" if f.kind == "int" else "数字") + rng
    else:
        desc = f"文本，不超过 {f.max_len} 字"
    hint = f"，{f.hint}" if f.hint else ""
    return f"- {f.key}: {desc}{hint}"


def build_field_brief(fields: Sequence[FieldSpec]) -> str:
    return "\n".join(_describe_field(f) for f in fields)


def estimate_max_tokens(fields: Sequence[FieldSpec]) -> int:
    """按字段数与长度上限估算输出预算。

    只是「安全上限」，真正决定输出量的是 prompt 里的长度约束；
    但把上限从 2000 收到数百，可避免模型啰嗦时无限拖延。
    """
    est = 40  # JSON 外壳 + improve_tips
    for f in fields:
        if f.kind in ("text", "long_text"):
            est += min(f.max_len, 80) + 8
        else:
            est += 16
    return max(500, min(1200, int(est * 1.5)))


# 上下文中表示「系统里已存在的同类条目」的 key（由 context_builder 写入）
_EXISTING_ITEM_KEYS = ("sibling_tasks", "existing_items", "related_items")
# 会被拿去和「已有条目」比对的建议字段
_NAME_LIKE_KEYS = ("name", "title")
_NORM_RE = re.compile(r"[\s\u3000（）()【】\[\]·、,，.。:：;；\-—_/\\|]+")


def _existing_items(context: Dict[str, Any]) -> list:
    """取出上下文里的「已有条目」列表（第一个非空者）。"""
    if not isinstance(context, dict):
        return []
    for k in _EXISTING_ITEM_KEYS:
        v = context.get(k)
        if isinstance(v, (list, tuple)) and v:
            return [x for x in v if isinstance(x, str) and x.strip()]
    return []


def _norm_item(value: Any) -> str:
    """归一化：去掉空白与标点、统一小写，用于「是否同一件事」的宽松比对。"""
    return _NORM_RE.sub("", str(value or "")).lower()


def drop_existing_suggestions(
    clean: Dict[str, Any], context: Dict[str, Any]
) -> Dict[str, Any]:
    """丢掉与系统中已有条目重名的建议。

    实测模型会把上下文里 sibling_tasks 的条目原样当成建议返回，
    用户点「AI 帮我填」后得到一个已经存在的任务名 —— 等于没填，
    还会误以为功能坏了。这里做一次确定性兜底（prompt 里已先行约束）。
    """
    existing = _existing_items(context)
    if not existing or not isinstance(clean, dict):
        return clean
    pool = {_norm_item(x) for x in existing}
    out = dict(clean)
    for key in _NAME_LIKE_KEYS:
        val = out.get(key)
        if isinstance(val, str) and _norm_item(val) in pool:
            out.pop(key, None)
    return out


def build_assist_prompt(
    form_label: str,
    fields: Sequence[FieldSpec],
    current_fields: Dict[str, Any],
    context: Dict[str, Any],
    required: Iterable[str] = (),
    blocked: Sequence[str] = (),
) -> str:
    required = [r for r in required if any(f.key == r for f in fields)]
    rules = [
        "1. key 必须与上面完全一致，禁止新增、禁止改写 key；",
        "2. 只填「已填字段」中为空/未提供的字段；已提供的字段仅在明显不规范时优化，且不得改变原意；",
        "3. 枚举字段必须输出给定取值之一（数字枚举直接输出数字），不确定就省略该字段；",
        "4. 不要编造无法从上下文推断的具体信息（真实人名、编号、精确金额、精确日期）；",
        "5. 每条文本值尽量简短，improve_tips 最多 2 条、每条不超过 25 字；",
        "6. 只输出一个 JSON 对象，不要 markdown 代码块、不要任何解释。",
    ]
    # 条件性规则按 1.1 → 1.4 的顺序拼好，再整体插到第 2 条位置（避免互相插队导致编号颠倒）
    sub_rules: List[str] = []
    if required:
        sub_rules.append(f"1.1 其中 {'/'.join(required)} 应尽量给出；")
    if blocked:
        sub_rules.append(f"1.2 严禁输出这些字段：{', '.join(blocked)}（系统真实编号，你无法得知）；")
    # 上下文里带了「同类已有条目」时，明确禁止重复建议——
    # 否则模型常把已存在的任务名原样当建议返回（实测出现过），用户点了等于没填。
    if _existing_items(context):
        sub_rules.append(
            "1.3 上下文中的 sibling_tasks / existing_items 是系统中**已存在**的条目，"
            "严禁把它们原样作为建议输出；只能给出尚未存在的新条目，"
            "若想不出新条目就省略该字段；"
        )
    # 日期字段：规则层已经会填合理默认值，模型凭感觉编的日期只会污染表单
    # （实测编出过 2024-01-01，而当天是 2026-09）。
    if any(f.kind == "date" for f in fields):
        sub_rules.append(
            "1.4 日期字段：仅当上下文里明确出现了日期时才输出，否则省略该字段"
            "（系统会自动填合理的默认日期）。严禁凭感觉编日期；"
        )
    if sub_rules:
        rules[1:1] = sub_rules

    return (
        f"你是项目管理系统的表单填写助手，正在填写【{form_label}】表单。\n\n"
        f"允许输出的字段（白名单）：\n{build_field_brief(fields)}\n\n"
        f"已填字段：{_json(current_fields)}\n"
        f"补充上下文：{_json(context)}\n\n"
        f"输出格式：\n"
        f'{{"suggestions": {{"字段key": "值"}}, "improve_tips": ["建议1"]}}\n\n'
        f"规则：\n" + "\n".join(rules)
    )


def _json(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


# ---------------------------------------------------------------------------
# 输出校验与强制类型转换
# ---------------------------------------------------------------------------

def _unwrap(value: Any) -> Any:
    """模型偶尔会输出 {"value": x} / {"建议值": x} 这类包装，先剥一层。"""
    if isinstance(value, dict):
        for k in ("value", "值", "建议值", "suggestion", "suggested"):
            if k in value:
                return value[k]
        if len(value) == 1:
            return next(iter(value.values()))
    return value


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _may_override(f: FieldSpec, current: Any) -> bool:
    """判断 AI 是否可以写入该字段（在已有值的情况下）。

    三种语义：
    - refine=True   自由文本类：允许润色覆盖（保持原意的前提下优化措辞）；
    - refine=False  锁定字段（如状态）：只有当前为空时才允许填，永不覆盖；
    - refine=None   默认启发式：枚举/数字/日期这类「用户一旦选过就不该被改」的字段，
                    仅当为空、或仍等于表单默认值（说明用户没主动选过）时才允许覆盖。
    """
    if f.refine is True:
        return True
    if f.refine is False:
        return _is_blank(current)
    if f.kind in _REFINABLE_KINDS:
        return True
    return _is_blank(current) or current == f.default


def _coerce_date(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        # 可能是毫秒/秒时间戳
        ts = float(value)
        if ts > 1e11:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts).date().isoformat()
        except Exception:
            return None

    text = _norm_text(value)
    if not text:
        return None
    text = text.split("T")[0].split(" ")[0]
    for pat in _DATE_PATTERNS:
        m = pat.match(text)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            try:
                parsed = date(y, mo, d)
            except ValueError:
                return None
            if not (1970 <= parsed.year <= 2100):
                return None
            return parsed.isoformat()
    return None


def _match_option(value: Any, options: Sequence[Tuple[Any, str]], kind: str) -> Tuple[bool, Any]:
    """把模型给的值匹配到合法取值上。返回 (是否命中, 命中值)。"""
    raw = _unwrap(value)

    # 1) 数字枚举：先按数值比
    if kind == "int_enum" or (isinstance(raw, (int, float)) and not isinstance(raw, bool)):
        try:
            num = int(float(raw))
            for v, _lab in options:
                if isinstance(v, (int, float)) and int(v) == num:
                    return True, v
        except (TypeError, ValueError):
            pass

    text = _norm_text(raw)
    if not text:
        return False, None

    # 2) 精确命中 value（字符串）
    for v, _lab in options:
        if isinstance(v, str) and v.lower() == text.lower():
            return True, v
    # 3) 命中标签
    for v, lab in options:
        if lab and _norm_text(lab) == text:
            return True, v
    # 4) 宽松命中：标签包含 / 被包含（如「高优先级」→「高」）
    for v, lab in options:
        lab_n = _norm_text(lab)
        if lab_n and (lab_n in text or text in lab_n):
            return True, v
    # 5) 布尔语义
    if text.lower() in _TRUE_WORDS:
        for v, _lab in options:
            if v in (True, "true", 1, "1"):
                return True, v
    return False, None


def _coerce_number(value: Any, f: FieldSpec) -> Optional[float]:
    raw = _unwrap(value)
    if isinstance(raw, str):
        cleaned = re.sub(r"[^\d.\-]", "", raw.replace(",", ""))
        raw = cleaned or None
    if raw is None or raw == "":
        return None
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return None
    if f.min_value is not None:
        num = max(num, f.min_value)
    if f.max_value is not None:
        num = min(num, f.max_value)
    if f.kind == "int":
        return int(round(num))
    if float(num).is_integer():
        return int(num)
    return num


def validate_suggestions(
    fields: Sequence[FieldSpec],
    raw_suggestions: Any,
    current_fields: Optional[Dict[str, Any]] = None,
    blocked_keys: Sequence[str] = (),
) -> Tuple[Dict[str, Any], List[str]]:
    """把模型输出清洗为「可直接回填表单」的字典。

    返回 (clean, notes)：notes 记录被丢弃/被修正的项，用于日志与可观测性。
    blocked_keys 为 ai="never" 的字段（真实编号/外键），单独给出更明确的说明。
    """
    current_fields = current_fields or {}
    blocked = set(blocked_keys)
    clean: Dict[str, Any] = {}
    notes: List[str] = []

    if not isinstance(raw_suggestions, dict):
        return clean, ["模型未返回 suggestions 对象"]

    by_key = {f.key: f for f in fields}
    by_alias: Dict[str, FieldSpec] = {}
    for f in fields:
        for a in (f.label,) + tuple(f.aliases):
            if a:
                by_alias.setdefault(_norm_text(a).lower(), f)

    for raw_key, raw_value in raw_suggestions.items():
        if isinstance(raw_key, str) and raw_key in blocked:
            notes.append(f"丢弃 {raw_key}（系统真实编号/外键，禁止 AI 编造）")
            continue
        f = by_key.get(raw_key)
        if f is None and isinstance(raw_key, str):
            f = by_alias.get(_norm_text(raw_key).lower())
        if f is None:
            notes.append(f"丢弃字段 {raw_key!r}（不在表单白名单内）")
            continue
        if f.ai == "never":
            notes.append(f"丢弃 {f.key}（系统真实编号/外键，禁止 AI 编造）")
            continue

        value = _unwrap(raw_value)
        if _is_blank(value):
            continue

        # 已有值且不允许覆盖 → 保留用户的选择，避免误改
        cur = current_fields.get(f.key)
        if not _is_blank(cur) and not _may_override(f, cur):
            notes.append(f"保留用户已选的 {f.key}（={cur!r}）")
            continue

        converted: Any = None
        if f.kind in ("text", "long_text"):
            text = _norm_text(value)
            if f.max_len and len(text) > f.max_len:
                notes.append(f"{f.key} 超长，已截断到 {f.max_len} 字")
                text = text[: f.max_len].rstrip()
            converted = text
        elif f.kind in ("enum", "int_enum"):
            ok, hit = _match_option(value, f.options, f.kind)
            if not ok:
                notes.append(f"丢弃 {f.key}（{value!r} 不是合法取值）")
                continue
            converted = hit
        elif f.kind in ("number", "int"):
            num = _coerce_number(value, f)
            if num is None:
                notes.append(f"丢弃 {f.key}（{value!r} 不是合法数字）")
                continue
            converted = num
        elif f.kind == "date":
            iso = _coerce_date(value)
            if not iso:
                notes.append(f"丢弃 {f.key}（{value!r} 不是合法日期）")
                continue
            if _date_too_far(iso):
                # 实测模型会编出 planned_start=2024-01-01（当天是 2026-09）。
                # 这种离谱日期会覆盖掉规则层已经填好的合理默认值，
                # 用户看到的是一张"日期莫名其妙"的表单 —— 宁可丢掉。
                notes.append(f"丢弃 {f.key}（{value!r} 距今天过远，疑为编造）")
                continue
            converted = iso
        else:
            continue

        if _is_blank(converted):
            continue
        if not _is_blank(cur) and cur == converted:
            # 与现值相同，回填也无意义，避免前端提示「已补全」却没变化
            continue
        clean[f.key] = converted

    _fix_date_range(clean, notes)
    return clean, notes


def _fix_date_range(clean: Dict[str, Any], notes: List[str]) -> None:
    pairs = (("start_date", "end_date"), ("planned_start", "planned_end"))
    for start_key, end_key in pairs:
        s, e = clean.get(start_key), clean.get(end_key)
        if s and e and str(s) > str(e):
            clean.pop(end_key, None)
            notes.append(f"{end_key} 早于 {start_key}，已丢弃")


# 日期合理性护栏：离今天太远的日期基本是模型编的
_MAX_PAST_DAYS = 365
_MAX_FUTURE_DAYS = 365 * 5


def _date_too_far(iso: str, today: Optional[date] = None) -> bool:
    """判断日期是否离今天远到不可能是真实意图（用于挡掉编造的日期）。"""
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (ValueError, TypeError):
        return True
    delta = (d - (today or date.today())).days
    return delta < -_MAX_PAST_DAYS or delta > _MAX_FUTURE_DAYS


def sanitize_tips(raw_tips: Any, limit: int = 2, max_len: int = 40) -> List[str]:
    if not isinstance(raw_tips, (list, tuple)):
        return []
    out: List[str] = []
    for t in raw_tips:
        text = _norm_text(_unwrap(t))
        if not text:
            continue
        if len(text) > max_len:
            text = text[:max_len].rstrip()
        out.append(text)
        if len(out) >= limit:
            break
    return out


def prompt_visible_fields(fields: Sequence[FieldSpec], current: Dict[str, Any]) -> Dict[str, Any]:
    """构造给模型看的「已填字段」：剔除仍等于表单默认值的项。

    前端 form.getFieldsValue(true) 会把 initialValue 一起带出来（如 status=planning、
    priority=3），这些并非用户真实输入。若原样交给模型，模型会认为这两个字段「已填」
    而不再给出建议（「优先级建议」能力因此失效）。
    校验层仍使用完整值判断是否允许覆盖，所以这里只是收窄模型视野，不影响安全性。
    """
    by_key = {f.key: f for f in fields}
    out: Dict[str, Any] = {}
    for k, v in (current or {}).items():
        f = by_key.get(k)
        if f is not None and f.default is not None and v == f.default:
            continue
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# 规则层：不调模型、0ms 就能给出的「合理默认值」
# ---------------------------------------------------------------------------

# 每个表单的默认日期跨度（天）：起点=今天，终点=今天+N。
# 这是**规则推导**，不是编造 —— 用户看得见、随时可改。
_INSTANT_DATE_SPAN: Dict[str, Tuple[str, str, int]] = {
    "project": ("start_date", "end_date", 90),
    "task": ("planned_start", "planned_end", 7),
}

# 按规则就能定的数字默认值
_INSTANT_NUMBER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "task": {"estimated_hours": 8},
}


def deterministic_suggestions(
    form_type: str,
    fields: Dict[str, Any],
    spec: Optional[FormSpec] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """规则层：不依赖模型、立刻可确定的字段。

    为什么需要它
    ------------
    本项目所用网关首字延迟 2~8.9s（生成本身只占约 1s，其余全在排队）。
    用户点下「AI 帮我填」后要盯着空表单等这么久，体感极差。
    把「按规则就能定」的字段（日期跨度、预估工时、状态/优先级默认值）提前返回，
    前端立刻可见，模型产出到了再补充 —— **等待被隐藏掉了**。

    与模型产出的本质区别：**这些是规则推导，不是编造。**
    只填「当前为空或仍等于默认值」的字段，绝不覆盖用户的主动选择。
    """
    spec = spec or get_form_spec(form_type)
    if spec is None:
        return {}

    by_key = {f.key: f for f in spec.fields}
    fields = fields or {}
    base = today or date.today()
    out: Dict[str, Any] = {}

    def _writable(key: str) -> Optional[FieldSpec]:
        f = by_key.get(key)
        if f is None or f.ai == "never":
            return None
        if not _may_override(f, fields.get(key)):
            return None
        cur = fields.get(key)
        # 已经等于默认值就不必再写（避免制造无意义的"已填"噪声）
        if not _is_blank(cur) and f.default is not None and cur == f.default:
            return None
        return f

    # 1) 状态 / 优先级：仅当前为空时给（表单通常有 initialValue，多数是 no-op）
    for key in ("status", "priority"):
        f = _writable(key)
        if f is not None and f.default is not None and _is_blank(fields.get(key)):
            out[key] = f.default

    # 2) 日期：今天 / 今天+N
    span = _INSTANT_DATE_SPAN.get(form_type)
    if span:
        start_key, end_key, days = span
        start_writable = _writable(start_key)
        end_writable = _writable(end_key)

        if start_writable is not None:
            out[start_key] = base.isoformat()
            anchor = base
        else:
            # 用户已填开始日期 → 以它为基准推结束日期，保证"结束晚于开始"
            parsed = _coerce_date(fields.get(start_key))
            anchor = None
            if parsed:
                try:
                    anchor = datetime.strptime(parsed, "%Y-%m-%d").date()
                except ValueError:
                    anchor = None

        if end_writable is not None and anchor is not None:
            out[end_key] = (anchor + timedelta(days=days)).isoformat()

    # 3) 数字默认（预估工时）
    for key, val in _INSTANT_NUMBER_DEFAULTS.get(form_type, {}).items():
        if _writable(key) is not None:
            out[key] = val

    return out


def cache_key(form_type: str, fields: Dict[str, Any], context: Dict[str, Any], options: Dict[str, Any]) -> str:
    """构造结果缓存键（同样的输入直接命中缓存，重复点击秒回）。"""
    import hashlib
    import json

    payload = json.dumps(
        {
            "form_type": form_type,
            "fields": _sorted_jsonable(fields),
            "context": _sorted_jsonable(context),
            "options": _sorted_jsonable(options),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _sorted_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _sorted_jsonable(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_sorted_jsonable(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)
