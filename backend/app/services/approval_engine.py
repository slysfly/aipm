"""
PMI中国AI项目管理社区 - 审批引擎服务
支持多级审批、条件分支、转交、委托
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from datetime import datetime
from typing import Optional, Dict, Any, List
import ast
import logging
import operator

from app.models.approval import (
    ApprovalFlow, ApprovalInstance, ApprovalStep, ApprovalDelegate,
    ApprovalStatus, StepStatus
)
from app.models import User
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 安全表达式求值器（替代 eval，防止任意代码执行 / 作用域逃逸）
# 仅允许：字面量、变量名（来自 context 命名空间）、比较、布尔运算、
# 基础算术(+ - * / // % **)与成员运算(in / not in)。
# 禁止：属性访问、函数调用、下标、推导式、lambda 等任何逃逸路径。
# ---------------------------------------------------------------------------
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_BOOL_OPS = {
    ast.And: all,
    ast.Or: any,
}

_UNARY_OPS = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval_node(node: ast.AST, context: Dict[str, Any]) -> Any:
    """递归安全求 AST 节点；遇到白名单外的节点一律抛出 ValueError。"""
    # 字面量（int / float / str / bool / None）
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, str, bool)) or node.value is None:
            return node.value
        raise ValueError("不支持的字面量类型")

    # 变量名（仅允许来自 context 命名空间）
    if isinstance(node, ast.Name):
        if node.id in context:
            return context[node.id]
        raise NameError(f"条件表达式中引用了未定义的变量: {node.id}")

    # 列表 / 元组 / 集合字面量（仅用于 in 右侧的成员集合）
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_safe_eval_node(item, context) for item in node.elts]

    # 布尔运算 and / or
    if isinstance(node, ast.BoolOp):
        op = _BOOL_OPS.get(type(node.op))
        if op is None:
            raise ValueError("不支持的布尔运算符")
        return op([_safe_eval_node(value, context) for value in node.values])

    # 一元运算 not / - / +
    if isinstance(node, ast.UnaryOp):
        handler = _UNARY_OPS.get(type(node.op))
        if handler is None:
            raise ValueError("不支持的一元运算符")
        return handler(_safe_eval_node(node.operand, context))

    # 比较运算（支持链式比较，如 a < b < c）
    if isinstance(node, ast.Compare):
        left = _safe_eval_node(node.left, context)
        result: bool = True
        for op, comparator in zip(node.ops, node.comparators):
            right = _safe_eval_node(comparator, context)
            handler = _CMP_OPS.get(type(op))
            if handler is None:
                raise ValueError("不支持的比较运算符")
            result = result and bool(handler(left, right))
            left = right
        return result

    # 二元算术运算
    if isinstance(node, ast.BinOp):
        handler = _BIN_OPS.get(type(node.op))
        if handler is None:
            raise ValueError("不支持的算术运算符")
        return handler(
            _safe_eval_node(node.left, context),
            _safe_eval_node(node.right, context),
        )

    # 禁止其它所有节点（属性访问、函数调用、下标、lambda、推导式等）
    raise ValueError(f"不支持的表达式节点类型: {type(node).__name__}")


def _safe_eval_condition(expr: str, context: Dict[str, Any]) -> Any:
    """解析并安全求值条件表达式。任何解析/求值异常都会向上抛出，由调用方捕获。"""
    parsed = ast.parse(expr, mode="eval")
    return _safe_eval_node(parsed.body, context)


class ApprovalEngine:
    """审批引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_approval(
        self,
        flow_id: str,
        entity_type: str,
        entity_id: str,
        requester_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ApprovalInstance:
        """启动审批流程"""
        # 获取流程定义
        result = await self.db.execute(
            select(ApprovalFlow).where(
                ApprovalFlow.id == flow_id,
                ApprovalFlow.is_active == True
            )
        )
        flow = result.scalar_one_or_none()
        if not flow:
            raise ValueError("审批流程不存在或已停用")

        # 创建审批实例
        instance = ApprovalInstance(
            flow_id=flow_id,
            entity_type=entity_type,
            entity_id=entity_id,
            requester_id=requester_id,
            status=ApprovalStatus.PENDING.value,
            current_step=0,
        )
        self.db.add(instance)
        await self.db.flush()

        # 创建审批步骤
        flow_steps = flow.steps or []
        for step_def in flow_steps:
            # 条件判断
            if step_def.get("condition") and context:
                condition_met = await self.check_condition(
                    step_def["condition"], context
                )
                if not condition_met:
                    continue

            approver_id = step_def.get("approver_id")
            # 检查委托
            if approver_id:
                delegated_id = await self._get_delegated_approver(approver_id)
                if delegated_id:
                    approver_id = delegated_id

            step = ApprovalStep(
                instance_id=instance.id,
                step_order=step_def["step_order"],
                approver_id=approver_id or requester_id,
                status=StepStatus.PENDING.value,
            )
            self.db.add(step)

        await self.db.commit()
        await self.db.refresh(instance)

        # 通知第一个审批人
        await self.notify_approver(instance)

        return instance

    async def process_step(
        self,
        step_id: str,
        approver_id: str,
        action: str,
        comment: Optional[str] = None
    ) -> ApprovalInstance:
        """处理审批步骤"""
        result = await self.db.execute(
            select(ApprovalStep).where(ApprovalStep.id == step_id)
        )
        step = result.scalar_one_or_none()
        if not step:
            raise ValueError("审批步骤不存在")

        if step.approver_id != approver_id:
            raise ValueError("无权处理此审批")

        if step.status != StepStatus.PENDING.value:
            raise ValueError("此步骤已处理")

        # 更新步骤状态
        step.status = action
        step.comment = comment
        step.acted_at = datetime.now()

        # 获取实例
        result = await self.db.execute(
            select(ApprovalInstance).where(ApprovalInstance.id == step.instance_id)
        )
        instance = result.scalar_one()

        if action == StepStatus.REJECTED.value:
            instance.status = ApprovalStatus.REJECTED.value
            instance.completed_at = datetime.now()
            await self._notify_requester(instance, "rejected")
        elif action == StepStatus.APPROVED.value:
            # 检查是否还有后续步骤
            result = await self.db.execute(
                select(ApprovalStep).where(
                    ApprovalStep.instance_id == instance.id,
                    ApprovalStep.step_order > step.step_order,
                    ApprovalStep.status == StepStatus.PENDING.value
                ).order_by(ApprovalStep.step_order)
            )
            next_steps = result.scalars().all()

            if not next_steps:
                instance.status = ApprovalStatus.APPROVED.value
                instance.completed_at = datetime.now()
                await self._notify_requester(instance, "approved")
            else:
                instance.current_step = next_steps[0].step_order
                await self.notify_approver(instance)

        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def transfer_step(
        self,
        step_id: str,
        from_approver_id: str,
        to_approver_id: str,
        comment: Optional[str] = None
    ) -> ApprovalStep:
        """转交审批步骤"""
        result = await self.db.execute(
            select(ApprovalStep).where(ApprovalStep.id == step_id)
        )
        step = result.scalar_one_or_none()
        if not step:
            raise ValueError("审批步骤不存在")

        if step.approver_id != from_approver_id:
            raise ValueError("无权转交此审批")

        if step.status != StepStatus.PENDING.value:
            raise ValueError("此步骤已处理，无法转交")

        # 保存原审批人
        step.original_approver_id = step.approver_id
        step.approver_id = to_approver_id
        step.status = StepStatus.TRANSFERRED.value
        step.comment = comment or "已转交"
        step.acted_at = datetime.now()

        # 创建新步骤给被转交人
        new_step = ApprovalStep(
            instance_id=step.instance_id,
            step_order=step.step_order,
            approver_id=to_approver_id,
            status=StepStatus.PENDING.value,
        )
        self.db.add(new_step)

        await self.db.commit()
        await self.db.refresh(new_step)

        # 通知被转交人
        await self._notify_user(
            user_id=to_approver_id,
            title="收到转交的审批",
            content=f"您收到一条转交的审批请求",
            related_type="approval_step",
            related_id=new_step.id,
        )

        return new_step

    async def check_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """条件判断

        支持简单条件表达式，如:
        - "amount > 10000"
        - "priority == 'high'"
        - "type in ['bug', 'feature']"
        使用基于 AST 的白名单安全求值器（替代 eval），禁止任何代码执行/作用域逃逸。
        """
        if not condition:
            return True

        try:
            # 安全评估：基于 AST 的白名单求值，变量仅来自 context 命名空间
            result = _safe_eval_condition(condition.strip(), context)
            return bool(result)
        except Exception as e:
            # fail-closed：解析或求值时出现任何异常，默认拒绝（不再默认放行）
            logger.warning(f"条件判断失败（已默认拒绝）: {condition}, 错误: {e}")
            return False

    async def escalate_overdue(self, hours: int = 48) -> List[ApprovalInstance]:
        """超时升级 - 查找并处理超时的审批实例"""
        from datetime import timedelta

        cutoff_time = datetime.now() - timedelta(hours=hours)

        result = await self.db.execute(
            select(ApprovalInstance).where(
                ApprovalInstance.status == ApprovalStatus.PENDING.value,
                ApprovalInstance.created_at < cutoff_time
            )
        )
        overdue_instances = result.scalars().all()

        escalated = []
        for instance in overdue_instances:
            # 获取当前待处理步骤
            result = await self.db.execute(
                select(ApprovalStep).where(
                    ApprovalStep.instance_id == instance.id,
                    ApprovalStep.status == StepStatus.PENDING.value
                )
            )
            pending_steps = result.scalars().all()

            for step in pending_steps:
                # 发送催办通知
                await self._notify_user(
                    user_id=step.approver_id,
                    title="审批即将超时",
                    content=f"您有一条审批已等待超过 {hours} 小时，请尽快处理",
                    related_type="approval_step",
                    related_id=step.id,
                )
                escalated.append(instance)

        return escalated

    async def notify_approver(self, instance: ApprovalInstance) -> None:
        """通知当前审批人"""
        result = await self.db.execute(
            select(ApprovalStep).where(
                ApprovalStep.instance_id == instance.id,
                ApprovalStep.status == StepStatus.PENDING.value
            ).order_by(ApprovalStep.step_order)
        )
        pending_steps = result.scalars().all()

        if not pending_steps:
            return

        # 通知当前步骤的审批人
        current_step = pending_steps[0]
        await self._notify_user(
            user_id=current_step.approver_id,
            title="新的审批请求",
            content=f"您有一条新的审批请求需要处理",
            related_type="approval_instance",
            related_id=instance.id,
        )

    async def _get_delegated_approver(self, approver_id: str) -> Optional[str]:
        """获取委托的审批人"""
        now = datetime.now()
        result = await self.db.execute(
            select(ApprovalDelegate).where(
                ApprovalDelegate.delegator_id == approver_id,
                ApprovalDelegate.is_active == True,
                ApprovalDelegate.start_date <= now,
                ApprovalDelegate.end_date >= now
            )
        )
        delegate = result.scalar_one_or_none()
        return delegate.delegatee_id if delegate else None

    async def _notify_requester(
        self,
        instance: ApprovalInstance,
        result_status: str
    ) -> None:
        """通知申请人审批结果"""
        status_text = "已通过" if result_status == "approved" else "已拒绝"
        await self._notify_user(
            user_id=instance.requester_id,
            title=f"审批{status_text}",
            content=f"您的审批请求已被{status_text}",
            related_type="approval_instance",
            related_id=instance.id,
        )

    async def _notify_user(
        self,
        user_id: str,
        title: str,
        content: str,
        related_type: str,
        related_id: str
    ) -> None:
        """发送通知给用户"""
        try:
            await create_notification(
                db=self.db,
                user_id=user_id,
                type="approval",
                title=title,
                content=content,
                related_type=related_type,
                related_id=related_id,
            )
        except Exception as e:
            logger.error(f"发送通知失败: {e}")

    async def get_dashboard_stats(self, user_id: str) -> Dict[str, Any]:
        """获取审批仪表盘统计数据"""
        # 待我审批的数量
        result = await self.db.execute(
            select(func.count()).where(
                ApprovalStep.approver_id == user_id,
                ApprovalStep.status == StepStatus.PENDING.value
            )
        )
        pending_count = result.scalar() or 0

        # 我已审批的数量
        result = await self.db.execute(
            select(func.count()).where(
                ApprovalStep.approver_id == user_id,
                ApprovalStep.status.in_([StepStatus.APPROVED.value, StepStatus.REJECTED.value])
            )
        )
        processed_count = result.scalar() or 0

        # 我发起的审批
        result = await self.db.execute(
            select(func.count()).where(
                ApprovalInstance.requester_id == user_id
            )
        )
        total_requests = result.scalar() or 0

        # 平均审批时长（分钟）
        _bind = getattr(self.db, "bind", None)
        _dialect = _bind.dialect.name if _bind is not None else "sqlite"
        if _dialect == "postgresql":
            _duration_expr = func.extract("epoch", ApprovalStep.acted_at - ApprovalStep.created_at) / 60.0
        else:
            _duration_expr = (
                func.julianday(ApprovalStep.acted_at) - func.julianday(ApprovalStep.created_at)
            ) * 24 * 60
        result = await self.db.execute(
            select(func.avg(_duration_expr)).where(
                ApprovalStep.approver_id == user_id,
                ApprovalStep.acted_at.isnot(None)
            )
        )
        avg_duration = result.scalar()

        # 委托数量
        result = await self.db.execute(
            select(func.count()).where(
                ApprovalDelegate.delegator_id == user_id,
                ApprovalDelegate.is_active == True
            )
        )
        delegated_count = result.scalar() or 0

        return {
            "pending_count": pending_count,
            "approved_count": processed_count,  # 包含通过和拒绝
            "rejected_count": 0,  # 可细分
            "avg_approval_duration_minutes": round(avg_duration, 2) if avg_duration else None,
            "delegated_count": delegated_count,
            "total_requests": total_requests,
        }
