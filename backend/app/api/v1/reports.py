"""
[PMBOK KA: 沟通管理 | PG: 监控 (Communications/Monitoring) — 绩效报告、EVM报表、状态报告]
对应PMI第6版标准：绩效报告、EVM报表、状态报告

PMBOK 7th Principle: Value/Measurement | Domain: Measurement — 绩效测量、价值报告
PMBOK 8th: Data-Driven Decision Making"""

import io
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.services.report_service import ReportService
from app.services.ai.report_generator import ReportGenerator

router = APIRouter(prefix="/reports", tags=["智能报告"])


@router.get("/daily")
async def generate_daily_report(
    report_date: Optional[date] = Query(None, description="日报日期，默认为今天"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    target_date = report_date or date.today()

    generator = ReportGenerator(db)
    report = await generator.generate_daily_report(
        user_id=current_user.id,
        target_date=target_date
    )

    return {
        "success": True,
        "data": report
    }


@router.get("/weekly")
async def generate_weekly_report(
    start: Optional[date] = Query(None, description="周报开始日期，默认本周一"),
    end: Optional[date] = Query(None, description="周报结束日期，默认本周日"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if start and end:
        start_date = start
        end_date = end
    else:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)

    generator = ReportGenerator(db)
    report = await generator.generate_weekly_report(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )

    return {
        "success": True,
        "data": report
    }


@router.get("/projects/{project_id}/status")
async def generate_project_status_report(
    project_id: str,
    start: Optional[date] = Query(None, description="报告开始日期"),
    end: Optional[date] = Query(None, description="报告结束日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    generator = ReportGenerator(db)
    report = await generator.generate_project_report(
        project_id=project_id,
        start_date=start,
        end_date=end
    )

    if "error" in report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=report["error"]
        )

    return {
        "success": True,
        "data": report
    }


@router.post("/daily/send")
async def send_daily_report(
    report_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.models import Task, Notification

    project_id = report_data.get("project_id")
    recipient = report_data.get("recipient") or getattr(current_user, "email", None)
    send_type = report_data.get("send_type", "email")

    today = datetime.now().date()
    conditions = [Task.is_deleted == False, Task.updated_at >= today]
    if project_id:
        conditions.append(Task.project_id == project_id)
    rows = (await db.execute(
        select(Task).where(*conditions).order_by(Task.updated_at.desc())
    )).scalars().all()

    summary_lines = [f"- {t.name} [{t.status}]" for t in rows[:20]]
    body = (
        f"【{today.isoformat()} 项目日报】\n"
        f"共 {len(rows)} 个任务今日更新：\n"
        + ("\n".join(summary_lines) or "（无）")
    )

    result = {
        "recipient": recipient,
        "send_type": send_type,
        "sent_at": today.isoformat(),
    }

    if send_type == "email" and recipient:
        try:
            from app.core.email import send_email
            result["email"] = await send_email(
                to=[recipient], subject=f"项目日报 {today.isoformat()}", body=body
            )
        except Exception as e:
            result["email_error"] = str(e)

    # 站内通知
    try:
        db.add(Notification(
            user_id=current_user.id,
            type="daily_report",
            title=f"项目日报 {today.isoformat()}",
            content=body,
        ))
        await db.commit()
        result["notification"] = True
    except Exception as e:
        result["notification_error"] = str(e)

    return {"success": True, "message": "日报已生成并发送", "data": result}


@router.get("/templates")
async def get_report_templates(
    current_user: User = Depends(get_current_user)
):
    templates = [
        {
            "id": "daily_default",
            "name": "默认日报模板",
            "type": "daily",
            "description": "包含今日摘要、已完成任务、进行中任务、阻塞项和明日计划",
            "sections": ["summary", "completed_tasks", "in_progress_tasks", "blockers", "tomorrow_plan"]
        },
        {
            "id": "daily_concise",
            "name": "简洁日报模板",
            "type": "daily",
            "description": "仅包含今日摘要和关键任务",
            "sections": ["summary", "key_tasks"]
        },
        {
            "id": "weekly_default",
            "name": "默认周报模板",
            "type": "weekly",
            "description": "包含本周综述、亮点、完成情况、进行中、阻塞和下周计划",
            "sections": ["summary", "highlights", "completed", "in_progress", "blockers", "next_week_plan"]
        },
        {
            "id": "weekly_executive",
            "name": "管理层周报模板",
            "type": "weekly",
            "description": "面向管理层的周报，突出关键指标和决策事项",
            "sections": ["summary", "kpi", "risks", "decisions", "next_week_plan"]
        },
        {
            "id": "project_status",
            "name": "项目状态报告模板",
            "type": "project",
            "description": "项目整体状态、进度、风险和团队贡献",
            "sections": ["summary", "health_score", "progress", "risks", "team_contributions", "milestones", "recommendations"]
        }
    ]

    return {
        "success": True,
        "data": templates
    }


@router.get("/project-progress")
async def project_progress_report(
    project_id: str = Query(...),
    period: str = Query("week", pattern="^(week|month)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ReportService(db)
    data = await service.get_project_progress(project_id, period)
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=data["error"]
        )
    return data


@router.get("/burndown")
async def burndown_report(
    project_id: str = Query(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ReportService(db)
    data = await service.get_burndown_data(project_id, start_date, end_date)
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=data["error"]
        )
    return data


@router.get("/velocity")
async def velocity_report(
    project_id: str = Query(...),
    sprint_length: int = Query(14, ge=7, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ReportService(db)
    data = await service.get_velocity_data(project_id, sprint_length)
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=data["error"]
        )
    return data


@router.get("/cumulative-flow")
async def cumulative_flow_report(
    project_id: str = Query(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ReportService(db)
    data = await service.get_cumulative_flow(project_id, start_date, end_date)
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=data["error"]
        )
    return data


@router.get("/evm")
async def evm_report(
    project_id: str = Query(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ReportService(db)
    data = await service.get_evm_report(project_id, start_date, end_date)
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=data["error"]
        )
    return data


@router.get("/evm/pdf")
async def evm_report_pdf(
    project_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """导出 EVM 偏差分析报告 PDF（含 9 大指标、偏差诊断、AI 建议）"""
    from datetime import datetime
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    service = ReportService(db)
    data = await service.get_evm_report(project_id, None, None)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])

    project = await db.get(Project, project_id)
    project_name = getattr(project, "name", project_id) if project else project_id

    # 获取当前 EVM 数据
    cur = data.get("current", {})
    pv, ev, ac = float(cur.get("pv", 0)), float(cur.get("ev", 0)), float(cur.get("ac", 0))
    bac = float(cur.get("bac", 0))
    sv, cv = float(cur.get("sv", 0)), float(cur.get("cv", 0))
    spi, cpi = float(cur.get("spi", 1)), float(cur.get("cpi", 1))
    eac, etc, vac = float(cur.get("eac", 0)), float(cur.get("etc", 0)), float(cur.get("vac", 0))
    tcpi = float(cur.get("tcpi", 1))
    done_pct = round(ev / bac * 100, 1) if bac > 0 else 0

    # 诊断
    diag_lines = []
    if spi < 1:
        diag_lines.append(f"SPI={spi:.2f} < 1：进度落后计划 {(1-spi)*100:.1f}%")
    else:
        diag_lines.append(f"SPI={spi:.2f} >= 1：进度符合/超前计划")
    if cpi < 1:
        diag_lines.append(f"CPI={cpi:.2f} < 1：每完成 ¥1 价值实际花费 ¥{1/cpi:.2f}，超支 {(1/cpi-1)*100:.1f}%")
    else:
        diag_lines.append(f"CPI={cpi:.2f} >= 1：成本控制良好")
    if vac < 0:
        diag_lines.append(f"VAC={vac:,.0f}：预计完工时超支 ¥{abs(vac):,.0f}")
    else:
        diag_lines.append(f"VAC={vac:,.0f}：预计完工时结余 ¥{vac:,.0f}")
    if tcpi > 1:
        diag_lines.append(f"TCPI={tcpi:.2f} > 1：剩余工作需以 {tcpi*100:.0f}% 效率完成才能达成 BAC 目标")
    else:
        diag_lines.append(f"TCPI={tcpi:.2f} <= 1：剩余工作可在当前效率下完成")

    # AI 建议生成
    suggestions = []
    if cpi < 0.9:
        suggestions.append("成本严重超支：建议立即启动成本控制会议，识别超支根因，对剩余 WBS 工作包重新估算")
    if spi < 0.9:
        suggestions.append("进度严重滞后：建议启动赶工(Crashing)或快速跟进(Fast-Tracking)策略，并重新评估关键路径")
    if cpi < 1 and spi < 1:
        suggestions.append("进度成本双红灯：建议向项目发起人汇报，考虑范围缩减或追加预算")
    if cpi >= 1 and spi >= 1:
        suggestions.append("绩效良好：建议保持当前节奏，并将经验沉淀为组织过程资产")
    if not suggestions:
        suggestions.append("关注趋势：建议每周做一次 EVM 快照，监控 CPI/SPI 是否有下滑趋势")

    # 用 reportlab 直接生成 PDF
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    except ImportError:
        raise HTTPException(status_code=503, detail="reportlab 未安装，无法导出 PDF")

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        cjk = "STSong-Light"
    except Exception:
        cjk = "Helvetica"

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm, title=f"EVM 报告 - {project_name}")
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("TitleCJK", parent=styles["Title"], fontName=cjk, textColor=colors.HexColor("#FF6B35"))
    h2_s = ParagraphStyle("H2CJK", parent=styles["Heading2"], fontName=cjk, textColor=colors.HexColor("#333333"))
    body_s = ParagraphStyle("BodyCJK", parent=styles["Normal"], fontName=cjk, fontSize=10, leading=14)
    cell_s = ParagraphStyle("CellCJK", parent=styles["Normal"], fontName=cjk, fontSize=9, leading=12)

    story = []
    story.append(Paragraph("PMI中国 AI-PM · EVM 偏差分析报告", title_s))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"{project_name} · {datetime.now().strftime('%Y-%m-%d %H:%M')}", body_s))
    story.append(Spacer(1, 12))

    # 1. 项目概况
    story.append(Paragraph("1. 项目概况", h2_s))
    story.append(Paragraph(f"项目名称：{project_name}", body_s))
    story.append(Paragraph(f"项目 ID：{project_id}", body_s))
    story.append(Paragraph(f"完工百分比：{done_pct}%", body_s))
    story.append(Spacer(1, 12))

    # 2. EVM 9 大指标表格
    story.append(Paragraph("2. EVM 9 大核心指标", h2_s))
    rows = [
        ["指标", "中文", "数值"],
        ["PV", "计划价值", f"¥{pv:,.2f}"],
        ["EV", "挣得价值", f"¥{ev:,.2f}"],
        ["AC", "实际成本", f"¥{ac:,.2f}"],
        ["BAC", "完工预算", f"¥{bac:,.2f}"],
        ["SV", "进度偏差", f"¥{sv:,.2f}"],
        ["CV", "成本偏差", f"¥{cv:,.2f}"],
        ["SPI", "进度绩效指数", f"{spi:.4f}"],
        ["CPI", "成本绩效指数", f"{cpi:.4f}"],
        ["EAC", "完工估算", f"¥{eac:,.2f}"],
        ["ETC", "完工尚需估算", f"¥{etc:,.2f}"],
        ["VAC", "完工偏差", f"¥{vac:,.2f}"],
        ["TCPI", "完工尚需绩效指数", f"{tcpi:.4f}"],
    ]
    rendered_rows = [[Paragraph(c, cell_s) for c in row] for row in rows]
    tbl = Table(rendered_rows, colWidths=[3*cm, 5*cm, 6*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6B35")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFF7F2"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#FFB088")),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 12))

    # 3. 偏差诊断
    story.append(Paragraph("3. 偏差诊断", h2_s))
    for line in diag_lines:
        story.append(Paragraph(f"• {line}", body_s))
    story.append(Spacer(1, 12))

    # 4. AI 建议
    story.append(Paragraph("4. AI 建议", h2_s))
    for s in suggestions:
        story.append(Paragraph(f"• {s}", body_s))
    story.append(Spacer(1, 12))

    # 5. PMBOK 标准对齐
    story.append(Paragraph("5. PMBOK 标准对齐", h2_s))
    story.append(Paragraph("本报告依据 PMBOK 第6版第7章《项目成本管理》挣值管理(EVM)方法", body_s))
    story.append(Paragraph("9 大指标定义与 PMI 标准 PMBOK 6th Edition 一致", body_s))
    story.append(Paragraph("用于 PMP 持证者项目汇报与 PMO 管理决策", body_s))

    doc.build(story)
    pdf_bytes = buf.getvalue()

    filename = f"evm_report_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/resource-utilization")
async def resource_utilization_report(
    project_id: str = Query(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ReportService(db)
    data = await service.get_resource_utilization(project_id, start_date, end_date)
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=data["error"]
        )
    return data


@router.get("/risk-trend")
async def risk_trend_report(
    project_id: str = Query(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ReportService(db)
    data = await service.get_risk_trend(project_id, start_date, end_date)
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=data["error"]
        )
    return data


@router.get("/export")
async def export_report(
    project_id: str = Query(...),
    report_type: str = Query(..., pattern="^(project-progress|burndown|velocity|cumulative-flow|evm|resource-utilization|risk-trend)$"),
    format_type: str = Query("csv", pattern="^(csv|json)$"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = ReportService(db)
    content, mime_type = await service.export_report(
        project_id=project_id,
        report_type=report_type,
        format_type=format_type,
        start_date=start_date,
        end_date=end_date
    )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="报表数据不存在"
        )

    filename = f"{report_type}_{project_id}_{date.today().isoformat()}.{format_type}"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
