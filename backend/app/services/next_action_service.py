"""
任务下一步行动建议服务（规则引擎版）

触发时机：
- 创建任务时（create_task 后立即生成）
- 任务关键字段变更时（status/priority/progress/planned_end/actual_hours/assignee_id）
- 前端主动调用 POST /tasks/{id}/next-action/regenerate

设计要点：
- 不依赖外部 LLM，纯规则 + 启发式模板，覆盖 12+ 场景
- 输出结构稳定：{summary, scenario, items[{action, reason, priority, eta}], confidence}
- 计算 source_hash 用于变更检测；hash 一致则跳过重算
- 字段提取优先级：DB 字段 > 计算值 > 默认值
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# 关键字段指纹：用于检测"是否需要重新生成"
# ────────────────────────────────────────────────────────────────────────
def compute_source_hash(task: Any) -> str:
    """根据关键字段算指纹；任意字段变更都会改变指纹"""
    parts = [
        str(getattr(task, "status", "") or ""),
        str(getattr(task, "priority", "") or ""),
        str(getattr(task, "progress", "") or ""),
        str(getattr(task, "planned_end", "") or ""),
        str(getattr(task, "planned_start", "") or ""),
        str(getattr(task, "actual_hours", "") or ""),
        str(getattr(task, "estimated_hours", "") or ""),
        str(getattr(task, "actual_cost", "") or ""),
        str(getattr(task, "assignee_id", "") or ""),
        str(getattr(task, "is_milestone", "") or ""),
        ",".join(sorted(getattr(task, "labels", []) or []) or []),
        str(getattr(task, "category", "") or ""),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────────────
# 时间辅助
# ────────────────────────────────────────────────────────────────────────
def _to_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _progress_num(t: Any) -> float:
    try:
        return float(getattr(t, "progress", 0) or 0)
    except Exception:
        return 0.0


def _cost_num(t: Any) -> float:
    try:
        return float(getattr(t, "actual_cost", 0) or 0)
    except Exception:
        return 0.0


def _hours_est(t: Any) -> float:
    try:
        return float(getattr(t, "estimated_hours", 0) or 0)
    except Exception:
        return 0.0


def _hours_act(t: Any) -> float:
    try:
        return float(getattr(t, "actual_hours", 0) or 0)
    except Exception:
        return 0.0


def _days_late(planned_end: Optional[datetime], now: datetime) -> int:
    pe = _to_dt(planned_end)
    if not pe:
        return 0
    # 统一到 tz-naive 比较
    try:
        if pe.tzinfo:
            pe_naive = pe.replace(tzinfo=None)
        else:
            pe_naive = pe
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        return max(0, (now_naive - pe_naive).days)
    except Exception:
        return 0


def _days_left(planned_end: Optional[datetime], now: datetime) -> int:
    pe = _to_dt(planned_end)
    if not pe:
        return 0
    try:
        if pe.tzinfo:
            pe_naive = pe.replace(tzinfo=None)
        else:
            pe_naive = pe
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        return max(0, (pe_naive - now_naive).days)
    except Exception:
        return 0


def _time_progress_pct(t: Any, now: datetime) -> Optional[float]:
    s = _to_dt(getattr(t, "planned_start", None))
    e = _to_dt(getattr(t, "planned_end", None))
    if not s or not e or e <= s:
        return None
    total = (e - s).total_seconds() or 1
    used = max(0.0, (now - s).total_seconds())
    return round(min(100.0, max(0.0, used / total * 100)), 1)


# ────────────────────────────────────────────────────────────────────────
# 工具：构造建议条目
# ────────────────────────────────────────────────────────────────────────
def _item(action: str, reason: str, priority: int = 2, eta: str = "本周内") -> Dict[str, Any]:
    return {
        "action": action,
        "reason": reason,
        "priority": int(max(1, min(3, priority))),
        "eta": eta,
    }


def _pack(scenario: str, summary: str, items: List[Dict[str, Any]], confidence: float) -> Dict[str, Any]:
    if not items:
        items = [_item("暂无特别建议，请持续关注任务进展", "任务当前各项指标均健康", 3, "持续跟踪")]
    return {
        "scenario": scenario,
        "summary": summary,
        "items": items,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
    }


# ────────────────────────────────────────────────────────────────────────
# 场景分析
# ────────────────────────────────────────────────────────────────────────
def _analyze(t: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    status = getattr(t, "status", "todo") or "todo"
    priority = int(getattr(t, "priority", 3) or 3)
    progress = _progress_num(t)
    labels: List[str] = list(getattr(t, "labels", []) or [])
    planned_end = getattr(t, "planned_end", None)
    planned_start = getattr(t, "planned_start", None)
    actual_start = getattr(t, "actual_start", None)
    assignee_id = getattr(t, "assignee_id", None)
    is_milestone = bool(getattr(t, "is_milestone", False))
    hours_est = _hours_est(t)
    hours_act = _hours_act(t)
    cost = _cost_num(t)
    name = (getattr(t, "name", "") or "").strip() or "该任务"

    late = _days_late(planned_end, now)
    left = _days_left(planned_end, now)
    tp_pct = _time_progress_pct(t, now)

    items: List[Dict[str, Any]] = []
    scenario = "idle"
    summary = "任务推进平稳，建议按计划继续执行"
    confidence = 0.55

    # ─── 1) 已完成 ────────────────────────────────────────
    if status == "done":
        summary = "任务已完成，建议归档并复盘关键经验"
        items = [
            _item("更新关联文档/产物，标注最终交付物版本",
                  "完成后及时同步文档，避免下游引用过期信息", 2, "今日"),
            _item("向项目负责人/干系人发送完成通知",
                  "主动同步交付状态，便于下一阶段规划", 3, "今日"),
        ]
        if progress < 100:
            items.append(_item("把进度推进到 100% 并确认实际完成时间",
                               "进度与状态不一致会让统计失真", 1, "今日"))
        scenario = "done"
        confidence = 0.95
        return _pack(scenario, summary, items, confidence)

    # ─── 2) 已取消 ────────────────────────────────────────
    if status == "cancelled":
        return _pack(
            "cancelled",
            "任务已取消",
            [_item("记录取消原因到描述或评论，便于事后复盘", "保留决策痕迹是项目管理重要资产", 3, "本周内")],
            0.95,
        )

    # ─── 3) 逾期未完成（最高优先级） ────────────────────────────
    if late > 0 and status not in ("done", "cancelled"):
        summary = f"任务已逾期 {late} 天，需要立即处理"
        items = [
            _item("今日内评估：是否仍可补救？若可，立即出补救计划并同步给负责人",
                  f"逾期 {late} 天，继续拖延将放大影响面", 1, "今日"),
            _item("在描述/评论中记录逾期原因与新目标完成时间",
                  "为后续复盘与责任追溯保留依据", 1, "今日"),
            _item("如涉及关键路径，立即评估对下游任务/里程碑的影响",
                  "上游延期会沿着依赖链路放大", 1, "今日"),
        ]
        if priority <= 2:
            items.append(_item("升级到项目干系人，请求资源/优先级支持",
                               "P1/P2 任务的逾期应进入升级流程", 1, "今日"))
        scenario = "overdue"
        confidence = 0.95
        return _pack(scenario, summary, items, confidence)

    # ─── 4) 进度落后于时间进度 ─────────────────────────────────
    if tp_pct is not None and tp_pct >= 30 and progress + 1 < tp_pct - 15 and status in ("in_progress", "todo"):
        gap = round(tp_pct - progress, 1)
        summary = f"进度落后于时间进度约 {gap} 个百分点"
        items = [
            _item("列出下一步 3 个关键产出，并把它们落到今天-本周末",
                  "把抽象进度拆成具体动作，更易追责", 1, "今日"),
            _item("向负责人/PM 同步现状，评估是否需要增援或调整范围",
                  "主动暴露风险比临时救火更有效", 2, "本周内"),
        ]
        if hours_est > 0 and hours_act < hours_est * 0.2 and tp_pct > 50:
            items.append(_item("核对工时记录：是否漏登实际投入",
                               "工时与时间不匹配，常因记录习惯导致数据失真", 2, "今日"))
        scenario = "behind"
        confidence = 0.85
        return _pack(scenario, summary, items, confidence)

    # ─── 5) 临近截止但未开始（P1/P2 高优） ────────────────────────
    if status in ("backlog", "todo") and left <= 3 and priority <= 2:
        summary = f"高优先级任务还有 {left} 天到截止但尚未启动"
        items = [
            _item("今日确认责任人并召开启动 kick-off，明确关键产出",
                  "高优先级 + 临近截止的双重压力，最容易卡在'等待启动'", 1, "今日"),
            _item("拆解为 2-3 个子任务并填入 WBS，便于追踪",
                  "大任务未拆解是阻塞主因", 1, "今日"),
        ]
        if not assignee_id:
            items.append(_item("指派明确负责人，必要时考虑资源调整",
                               "无责任人的高优先级任务是最大风险", 1, "今日"))
        scenario = "high_priority_pending"
        confidence = 0.9
        return _pack(scenario, summary, items, confidence)

    # ─── 6) 进行中但工时为 0 / 进度不动 ──────────────────────────
    if status == "in_progress" and progress < 1 and (actual_start or planned_start):
        started = _to_dt(actual_start) or _to_dt(planned_start)
        if started and (now - started).days >= 2:
            summary = "任务已进入进行中但进度仍未推进"
            items = [
                _item("与负责人一对一沟通：是否卡在某个阻塞点？",
                      "进度 0% 且已开始 2 天以上几乎一定有外部阻塞", 1, "今日"),
                _item("把阻塞点写入描述或评论，并打 blocker 标签",
                      "阻塞信息不显式化容易被遗忘", 1, "今日"),
            ]
            scenario = "stalled"
            confidence = 0.8
            return _pack(scenario, summary, items, confidence)

    # ─── 7) 评审中 ──────────────────────────────────────────
    if status == "in_review":
        summary = "任务处于评审阶段"
        items = [
            _item("确认评审人是否已收到材料/链接，主动 @ 提醒",
                  "评审阶段最大风险是被遗忘", 2, "今日"),
            _item("列出评审检查清单（Checklist）以减少来回",
                  "清单化评审可缩短 30%+ 周期", 2, "本周内"),
        ]
        if left <= 2:
            items.append(_item("距截止 ≤2 天，需协调评审人加速或申请延期",
                               "评审阶段最容易被低估时间", 1, "今日"))
        scenario = "in_review"
        confidence = 0.8
        return _pack(scenario, summary, items, confidence)

    # ─── 8) 测试中 ──────────────────────────────────────────
    if status == "testing":
        summary = "任务处于测试阶段"
        items = [
            _item("与 QA 同步测试用例通过率与阻塞缺陷",
                  "测试阶段的瓶颈通常是缺陷数量", 2, "今日"),
            _item("列出 P0/P1 缺陷清单并分配修复人",
                  "阻塞缺陷必须当日处理", 1, "今日"),
        ]
        scenario = "testing"
        confidence = 0.8
        return _pack(scenario, summary, items, confidence)

    # ─── 9) 无负责人 ────────────────────────────────────────
    if not assignee_id and status in ("backlog", "todo", "in_progress"):
        summary = "任务暂无明确负责人"
        items = [
            _item("今日内指派负责人，若难以指派则升级到 PM 协调",
                  "无责任人的任务完成率显著低于平均", 1, "今日"),
            _item("指派后与责任人同步背景、范围、验收标准",
                  "清晰的范围能显著减少返工", 2, "今日"),
        ]
        scenario = "no_assignee"
        confidence = 0.95
        return _pack(scenario, summary, items, confidence)

    # ─── 10) 成本/工时超支 ───────────────────────────────────
    if hours_est > 0 and hours_act > hours_est * 1.2:
        ratio = round(hours_act / hours_est, 2)
        summary = f"工时已消耗 {hours_act:.1f}h / 预算 {hours_est:.1f}h（{ratio}×）"
        items = [
            _item("复盘超支原因：是估算偏低、范围蔓延，还是返工？",
                  "没有归因就无法避免再次超支", 1, "本周内"),
            _item("评估是否需要追加预算或调整范围",
                  "成本超支需要正式走变更流程", 2, "本周内"),
        ]
        scenario = "cost_overrun"
        confidence = 0.85
        return _pack(scenario, summary, items, confidence)

    # ─── 11) 低优先级长期未开始（>7 天） ─────────────────────────
    if status in ("backlog", "todo") and planned_start:
        ps = _to_dt(planned_start)
        if ps and (now - ps).days > 7:
            summary = "低优先级任务长期堆积未启动"
            items = [
                _item("评估是否仍需做；若否，则取消或合并",
                      "Backlog 堆积会稀释团队注意力", 2, "本周内"),
                _item("若仍需做，重新评估优先级并排入下一迭代",
                      "长期 backlog 通常意味着优先级被错估", 3, "下周"),
            ]
            scenario = "low_priority_idle"
            confidence = 0.7
            return _pack(scenario, summary, items, confidence)

    # ─── 12) 默认健康 ───────────────────────────────────────
    summary = "任务各项指标正常，建议按计划持续推进"
    if is_milestone:
        summary = "里程碑任务，请重点关注按时达成"
        items = [_item("与上游/下游任务对齐里程碑依赖", "里程碑延期会放大影响", 2, "本周内")]
    elif left <= 7 and left > 0 and status == "in_progress":
        items = [_item(f"距离截止还有 {left} 天，建议做好日清日结",
                       "临近截止需要保持节奏", 2, "持续")]
    else:
        items = [_item("按计划推进，更新进度并保持沟通节奏",
                       "节奏稳定是按时交付的最大保障", 3, "持续")]
    scenario = "idle"
    confidence = 0.6
    return _pack(scenario, summary, items, confidence)


# ────────────────────────────────────────────────────────────────────────
# 主入口：生成建议（异步包装，便于后续接入 LLM）
# ────────────────────────────────────────────────────────────────────────
async def generate_next_action(t: Any, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """生成任务的下一步行动建议"""
    try:
        return _analyze(t)
    except Exception as e:
        logger.warning("生成 next_action 失败（已降级）: %s", e, exc_info=True)
        return _pack(
            "idle",
            "暂无法生成下一步建议，请稍后重试",
            [_item("手动评估下一步动作并写在描述或评论中",
                   "AI 生成暂时不可用，需依赖人工判断", 2, "今日")],
            0.3,
        )


def generate_next_action_sync(t: Any) -> Dict[str, Any]:
    """同步版（用于 update_task 中无需 await 的场景）"""
    try:
        return _analyze(t)
    except Exception as e:
        logger.warning("generate_next_action_sync 失败: %s", e, exc_info=True)
        return _pack("idle", "暂无法生成建议", [], 0.3)