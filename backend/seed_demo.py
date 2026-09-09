"""
PMI中国 AI-PM 示例项目 — 多维度联动数据 seed
覆盖模块：项目/任务/依赖/Sprint/OKR/风险/资源/资源分配/EVM/变更/里程碑/预算/知识库/白板/评论/通知
约束：通过 SQLAlchemy async 直连，绕开演示策略，FK 由 models 自动约束
"""
import asyncio
import os
import sys
import uuid
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(BASE_DIR, 'test.db')}"
sys.path.insert(0, BASE_DIR)

from app.db.session import async_session_maker
from app.models import (
    User, Organization, Project, Task, TaskDependency, Sprint, SprintTask,
    Objective, Risk, ChangeRequest, EVMSnapshot, Milestone, ProjectBudget,
    Resource, ResourceAllocation, KnowledgeBase, KnowledgeDocument,
    Whiteboard, Comment, Notification, Attachment, BudgetCategory,
)
from sqlalchemy import select, text


def dt(s):
    return datetime.fromisoformat(s.replace("T", " "))


async def main():
    async with async_session_maker() as s:
        # 查 admin（动态获取，避免硬编码 ID 跨环境失效）
        admin = (await s.execute(select(User).where(User.username == 'admin'))).scalars().first()
        if not admin:
            admin = (await s.execute(select(User).limit(1))).scalar_one()
        ADMIN_ID = admin.id
        print(f"Admin: {admin.username}")

        # 修整 schema 不一致：resource_allocations.task_id 应为可空
        try:
            await s.execute(text("""
                CREATE TABLE resource_allocations_new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    task_id VARCHAR(36),
                    resource_id VARCHAR(36) NOT NULL,
                    project_id VARCHAR(36) NOT NULL,
                    allocated_hours NUMERIC(10, 2),
                    allocated_date DATE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    task_title VARCHAR(255),
                    start_date DATE,
                    end_date DATE,
                    hours_per_day NUMERIC(10, 2),
                    daily_hours JSON,
                    priority INTEGER,
                    status VARCHAR(20),
                    notes TEXT,
                    is_ai_move BOOLEAN,
                    original_start_date DATE,
                    original_end_date DATE,
                    original_daily_hours JSON,
                    original_hours_per_day NUMERIC(10, 2),
                    optimization_reason VARCHAR(512)
                )
            """))
            await s.execute(text("INSERT INTO resource_allocations_new SELECT * FROM resource_allocations"))
            await s.execute(text("DROP TABLE resource_allocations"))
            await s.execute(text("ALTER TABLE resource_allocations_new RENAME TO resource_allocations"))
            await s.execute(text("CREATE INDEX ix_resource_allocations_task_id ON resource_allocations(task_id)"))
            await s.execute(text("CREATE INDEX ix_resource_allocations_resource_id ON resource_allocations(resource_id)"))
            await s.execute(text("CREATE INDEX ix_resource_allocations_project_id ON resource_allocations(project_id)"))
            await s.execute(text("CREATE INDEX ix_resource_allocations_start_date ON resource_allocations(start_date)"))
            await s.execute(text("CREATE INDEX ix_resource_allocations_end_date ON resource_allocations(end_date)"))
            print("Schema patch: resource_allocations.task_id made nullable")
        except Exception as ex:
            print(f"Schema patch warning: {ex}")
        await s.commit()

        # 查/建 组织
        org = (await s.execute(select(Organization).limit(1))).scalar_one_or_none()
        if not org:
            org = Organization(
                id=str(uuid.uuid4()),
                name="PMI中国科技",
                code="TW",
                level=0,
                owner_user_id=ADMIN_ID,
                plan_id=None,
                status="active",
                max_seats=50,
                used_seats=1,
            )
            s.add(org)
            await s.flush()
        print(f"Org: {org.id} {org.name}")

        # === 1. 创建项目"PMI中国 AI-PM 示例项目" ===
        proj = Project(
            id=str(uuid.uuid4()),
            name="PMI中国 AI-PM 示例项目",
            description="AI 驱动的智能项目管理系统 v2.0 升级 — 引入 RAG 知识库、多 Agent 协作、PMBOK 8 性能域对齐。30 天冲刺，覆盖需求/设计/开发/测试/上线全流程。",
            industry_type="it_software",
            project_type="agile",
            status="active",
            priority=2,
            color="#722ed1",
            start_date=date(2026, 7, 29),
            end_date=date(2026, 8, 27),
            baseline_start=date(2026, 7, 29),
            baseline_end=date(2026, 8, 27),
            budget=Decimal("100000.00"),
            baseline_budget=Decimal("100000.00"),
            owner_id=ADMIN_ID,
        )
        s.add(proj)
        await s.flush()
        PID = proj.id
        print(f"Project created: {PID} {proj.name}")

        # === 2. 7 个任务（2 完成 + 2 进行中 + 3 未开始，进度 29%） ===
        T = []
        task_specs = [
            # (wbs, name, desc, est, act, ps, pe, as, ae, prog, status, pri, ms, pv, ev, ac, sort)
            ("1.1", "项目启动与立项", "完成项目章程、识别关键干系人、召开启动会。", 16, 18,
             "2026-07-29T09:00:00", "2026-07-30T18:00:00", "2026-07-29T09:00:00", "2026-07-30T17:30:00",
             100, "done", 1, True, 5000, 5000, 4500, 1),
            ("1.2", "需求调研与分析", "完成 15 家客户访谈、输出 PRD v1.2。", 40, 44,
             "2026-07-29T09:00:00", "2026-08-03T18:00:00", "2026-07-29T09:00:00", "2026-08-03T16:00:00",
             100, "done", 1, False, 10000, 10000, 9500, 2),
            ("2.1", "系统架构设计", "完成微服务拆分、API 网关、向量库选型。", 60, 40,
             "2026-08-04T09:00:00", "2026-08-10T18:00:00", "2026-08-04T09:00:00", None,
             60, "in_progress", 1, False, 15000, 9000, 8000, 3),
            ("2.2", "后端核心服务开发", "FastAPI 升级、PGvector 集成、Agent 编排。", 80, 30,
             "2026-08-11T09:00:00", "2026-08-17T18:00:00", "2026-08-11T09:00:00", None,
             30, "in_progress", 1, False, 20000, 6000, 7000, 4),
            ("2.3", "前端界面开发", "AntD 5 升级、PMBOK 8 性能域页面、多 Agent 协作面板。", 80, 0,
             "2026-08-18T09:00:00", "2026-08-24T18:00:00", None, None,
             0, "todo", 2, False, 20000, 0, 0, 5),
            ("3.1", "集成测试与 Bug 修复", "全链路测试、压测、安全扫描。", 40, 0,
             "2026-08-25T09:00:00", "2026-08-26T18:00:00", None, None,
             0, "todo", 1, False, 15000, 0, 0, 6),
            ("4.1", "v2.0 正式上线", "灰度发布 → 全量发布 → 监控告警。", 16, 0,
             "2026-08-27T09:00:00", "2026-08-27T18:00:00", None, None,
             0, "todo", 1, True, 15000, 0, 0, 7),
        ]
        for spec in task_specs:
            (wbs, name, desc, est, act, ps, pe, asg, ae, prog, status, pri, ms, pv, ev, ac, sort) = spec
            t = Task(
                id=str(uuid.uuid4()),
                project_id=PID,
                wbs_code=wbs,
                name=name,
                description=desc,
                level=2,
                estimated_hours=est,
                actual_hours=act,
                planned_start=dt(ps),
                planned_end=dt(pe),
                actual_start=dt(asg) if asg else None,
                actual_end=dt(ae) if ae else None,
                progress=Decimal(prog),
                status=status,
                priority=pri,
                assignee_id=ADMIN_ID,
                is_milestone=ms,
                planned_value=Decimal(pv),
                earned_value=Decimal(ev),
                actual_cost=Decimal(ac),
                sort_order=sort,
            )
            s.add(t)
            T.append(t)
        await s.flush()
        print(f"Tasks: 7 (2 done, 2 in_progress, 3 todo)")

        # === 3. 任务依赖（关键路径：1→2→3→4→6→7，5 与 4 并行）===
        deps = [
            (T[1], T[0]),
            (T[2], T[1]),
            (T[3], T[2]),
            (T[4], T[1]),
            (T[5], T[3]),
            (T[5], T[4]),
            (T[6], T[5]),
        ]
        seen = set()
        for succ, pred in deps:
            k = (succ.id, pred.id)
            if k in seen:
                continue
            seen.add(k)
            s.add(TaskDependency(id=str(uuid.uuid4()), successor_id=succ.id, predecessor_id=pred.id, dependency_type="FS", lag_time=0))
        await s.flush()
        print(f"Task deps: {len(seen)}")

        # === 4. Sprint 1 + 2 ===
        sp1 = Sprint(
            id=str(uuid.uuid4()), project_id=PID,
            name="Sprint 1 - 启动与设计",
            goal="完成项目启动、需求调研、架构设计，进入开发阶段。",
            start_date=date(2026, 7, 29), end_date=date(2026, 8, 12),
            status="completed", velocity=116, capacity=200,
            created_by=ADMIN_ID,
        )
        sp2 = Sprint(
            id=str(uuid.uuid4()), project_id=PID,
            name="Sprint 2 - 开发与上线",
            goal="完成核心开发、集成测试和 v2.0 上线发布。",
            start_date=date(2026, 8, 13), end_date=date(2026, 8, 27),
            status="active", velocity=0, capacity=240,
            created_by=ADMIN_ID,
        )
        s.add(sp1); s.add(sp2)
        await s.flush()
        for t in [T[0], T[1], T[2]]:
            s.add(SprintTask(id=str(uuid.uuid4()), sprint_id=sp1.id, task_id=t.id))
        for t in [T[3], T[4], T[5], T[6]]:
            s.add(SprintTask(id=str(uuid.uuid4()), sprint_id=sp2.id, task_id=t.id))
        await s.flush()
        print("Sprints: 2")

        # === 5. OKR ===
        okr = Objective(
            id=str(uuid.uuid4()),
            objective="成功交付PMI中国 AI-PM v2.0，成为行业领先的 AI 驱动项目管理平台",
            year="2026", quarter="Q3", owner="系统管理员", progress=29,
            key_results=json.dumps([
                {"id": "kr-1", "title": "8/27 前完成 v2.0 上线发布", "target": 1.0, "current": 0.29, "unit": "项", "progress": 29},
                {"id": "kr-2", "title": "系统可用性 ≥ 99.5%", "target": 99.5, "current": 0, "unit": "%", "progress": 0},
                {"id": "kr-3", "title": "首批 10 家客户接入", "target": 10.0, "current": 0, "unit": "家", "progress": 0},
            ], ensure_ascii=False),
            project_id=PID,
        )
        s.add(okr); await s.flush()
        print("OKR: 1 with 3 KRs")

        # === 6. 风险 ===
        r1 = Risk(
            id=str(uuid.uuid4()), project_id=PID,
            name="关键路径人员风险",
            description="架构师张伟同时参与 3 个项目，本项目投入可能不足 80%。",
            category="resource", probability=0.6, impact=0.7, risk_score=0.42,
            status="identified",
            response_strategy="mitigate",
            response_plan="启用备份架构师王明；与 PMO 协调减负。",
            owner_id=ADMIN_ID,
        )
        r2 = Risk(
            id=str(uuid.uuid4()), project_id=PID,
            name="OpenAI 接口稳定性",
            description="AI Agent 依赖 OpenAI，海外 API 不稳定可能影响 RAG 检索。",
            category="technical", probability=0.4, impact=0.8, risk_score=0.32,
            status="monitoring",
            response_strategy="mitigate",
            response_plan="切到 gpt-4o-mini + DeepSeek 双供应商；本地缓存。",
            owner_id=ADMIN_ID,
        )
        s.add(r1); s.add(r2); await s.flush()
        print("Risks: 2")

        # === 7. 变更请求 ===
        cr = ChangeRequest(
            id=str(uuid.uuid4()), project_id=PID,
            project_name="PMI中国 AI-PM 示例项目",
            title="增加多租户数据隔离",
            description="客户要求按组织 ID 严格隔离数据，PG RLS + 应用层双重防护。",
            reason="提升企业客户信任度，支持 SaaS 化交付",
            impact="范围: 架构 + 后端 + 部署\n进度: +5 工作日\n成本: +¥12000\n质量: 高",
            category="范围变更",
            priority="high", status="in_review",
            requested_by="系统管理员",
        )
        s.add(cr); await s.flush()
        print("ChangeRequests: 1")

        # === 8. 资源（5 个）===
        res_data = [
            ("王明", "PM", Decimal("50.0"), ["PM", "Agile", "PMBOK"]),
            ("张伟", "Tech Lead", Decimal("80.0"), ["Python", "FastAPI", "AI", "架构"]),
            ("陈刚", "后端开发", Decimal("100.0"), ["Python", "FastAPI", "PG", "AI"]),
            ("周琳", "前端开发", Decimal("100.0"), ["React", "TS", "AntD", "Vite"]),
            ("孙鹏", "QA", Decimal("60.0"), ["测试", "自动化", "JMeter"]),
        ]
        resources = []
        for name, role, alloc, skills in res_data:
            r = Resource(
                id=str(uuid.uuid4()),
                name=name,
                resource_type="person",
                skills=skills,
                capacity=Decimal("8.0"),
                cost_rate=Decimal("300.00"),
                department=role,
                is_active=True,
            )
            s.add(r)
            resources.append(r)
        await s.flush()
        print(f"Resources: {len(resources)}")

        # === 9. 资源分配（按日工时 × 范围天数）===
        for r, (name, role, alloc, _) in zip(resources, res_data):
            hours_per_day = Decimal("4.0")  # 半日~全日，按 100% 满档 8h，50% 4h
            s.add(ResourceAllocation(
                id=str(uuid.uuid4()),
                project_id=PID, resource_id=r.id,
                task_title=f"PMI中国 AI-PM 示例项目 - {role}",
                start_date=date(2026, 7, 29), end_date=date(2026, 8, 27),
                hours_per_day=hours_per_day,
                daily_hours=json.dumps({}, ensure_ascii=False),
                priority=3, status="in_progress",
                notes=f"投入 {alloc}% 满档 ({float(hours_per_day)}h/日)，覆盖项目周期",
            ))
        await s.flush()
        print(f"ResourceAllocations: {len(res_data)}")

        # === 10. EVM 快照 ===
        snapshots = []
        for lbl, dt_s, pv_v, ev_v, ac_v in [
            ("W1-启动", date(2026, 7, 30), 5000, 5000, 4500),
            ("W1-需求完成", date(2026, 8, 3), 15000, 15000, 14000),
            ("W2-设计中", date(2026, 8, 10), 30000, 24000, 26000),
        ]:
            pv = Decimal(pv_v); ev = Decimal(ev_v); ac = Decimal(ac_v)
            cv = ev - ac
            sv = ev - pv
            cpi = (ev / ac) if ac else Decimal("1.0")
            spi = (ev / pv) if pv else Decimal("1.0")
            eac = (Decimal("100000") / cpi) if cpi else Decimal("100000")
            etc = eac - ac
            vac = Decimal("100000") - eac
            tcpi = ((Decimal("100000") - ev) / (Decimal("100000") - ac)) if (Decimal("100000") - ac) > 0 else Decimal("1.0")
            snapshots.append(EVMSnapshot(
                id=str(uuid.uuid4()), project_id=PID,
                snapshot_date=dt_s,
                planned_value=pv, earned_value=ev, actual_cost=ac,
                cost_variance=cv, schedule_variance=sv,
                cost_performance_index=cpi, schedule_performance_index=spi,
                estimate_at_completion=eac, estimate_to_complete=etc,
                variance_at_completion=vac, to_complete_performance_index=tcpi,
            ))
            s.add(snapshots[-1])
        await s.flush()
        print(f"EVM snapshots: {len(snapshots)}")

        # === 11. 里程碑 ===
        ms_list = [
            Milestone(id=str(uuid.uuid4()), project_id=PID, name="项目启动会",
                      due_date=date(2026, 7, 30), status="completed",
                      description="正式 kick-off，干系人对齐"),
            Milestone(id=str(uuid.uuid4()), project_id=PID, name="设计评审通过",
                      due_date=date(2026, 8, 10), status="pending",
                      description="架构 & DB 设计评审"),
            Milestone(id=str(uuid.uuid4()), project_id=PID, name="v2.0 正式上线",
                      due_date=date(2026, 8, 27), status="pending",
                      description="灰度发布 → 全量发布"),
        ]
        for m in ms_list:
            s.add(m)
        await s.flush()
        print(f"Milestones: {len(ms_list)}")

        # === 12. 预算（一个 ProjectBudget + 4 个 BudgetCategory） ===
        pb = ProjectBudget(
            id=str(uuid.uuid4()),
            project_id=PID,
            total_budget=Decimal("100000"),
            currency="CNY",
            labor_rate=Decimal("300"),
            overhead_rate=Decimal("0.15"),
            start_date=date(2026, 7, 29),
            end_date=date(2026, 8, 27),
            status="active",
            created_by=ADMIN_ID,
        )
        s.add(pb)
        await s.flush()
        pb_data = [
            ("人力", 60000, 28000),
            ("云服务", 20000, 9000),
            ("软件许可", 15000, 6000),
            ("差旅", 5000, 0),
        ]
        for cname, allocated, spent in pb_data:
            s.add(BudgetCategory(
                id=str(uuid.uuid4()),
                budget_id=pb.id,
                name=cname,
                allocated_amount=Decimal(allocated),
                spent_amount=Decimal(spent),
                description=f"{cname} 预算",
            ))
        await s.flush()
        print(f"ProjectBudget: 1 with {len(pb_data)} categories")

        # === 13. 知识库 + 3 文档 ===
        kb = KnowledgeBase(
            id=str(uuid.uuid4()),
            name="PMI中国 AI-PM 项目知识库",
            description="v2.0 项目相关文档：需求、设计、API、测试报告、运维手册。",
            visibility="private",
            project_id=PID,
            embedding_model="text-embedding-3-small",
            created_by=ADMIN_ID,
        )
        s.add(kb); await s.flush()
        KBID = kb.id
        docs_data = [
            ("PRD-v2.0.md", "PMI中国 AI-PM v2.0 产品需求文档", "# v2.0 PRD\n\n## 1. 背景\n\n## 2. 目标\n- 提升 RAG 检索准确率\n- 多 Agent 协作\n- PMBOK 8 性能域对齐\n\n## 3. 范围\n..."),
            ("架构设计.md", "系统架构设计文档", "# 架构\n\n## 微服务\n- ai-pm-api\n- ai-pm-agent\n- ai-pm-rag\n\n## 数据库\n- PostgreSQL 16 + pgvector\n- Redis (cache)\n\n## AI 模型\n- DeepSeek-Chat\n- gpt-4o-mini"),
            ("API 文档.md", "OpenAPI 3.0 接口文档", "# API\n\n| 端点 | 方法 | 用途 |\n|---|---|---|\n| /projects | GET | 列项目 |\n| /projects | POST | 创项目 |\n| /tasks | POST | 创任务 |\n"),
        ]
        for fname, ftitle, fcontent in docs_data:
            s.add(KnowledgeDocument(
                id=str(uuid.uuid4()),
                kb_id=KBID, title=ftitle,
                content=fcontent,
                source_type="text",
                file_name=fname,
                file_size=len(fcontent),
                mime_type="text/markdown",
                status="ready",
                chunk_count=3,
                meta_data={"source": "示例 seed", "version": "v2.0"},
            ))
        await s.flush()
        print(f"KnowledgeBase: 1 with {len(docs_data)} docs")

        # === 14. 白板（WBS 拆解） ===
        wb = Whiteboard(
            id=str(uuid.uuid4()),
            title="项目 WBS 拆解 - v2.0",
            notes=[
                {"id": "n1", "type": "start", "label": "项目启动"},
                {"id": "n2", "type": "task", "label": "需求调研"},
                {"id": "n3", "type": "task", "label": "架构设计"},
                {"id": "n4", "type": "task", "label": "后端开发"},
                {"id": "n5", "type": "task", "label": "前端开发"},
                {"id": "n6", "type": "task", "label": "集成测试"},
                {"id": "n7", "type": "end", "label": "上线发布"},
                {"id": "e12", "type": "edge", "from": "n1", "to": "n2"},
                {"id": "e23", "type": "edge", "from": "n2", "to": "n3"},
                {"id": "e34", "type": "edge", "from": "n3", "to": "n4"},
                {"id": "e25", "type": "edge", "from": "n2", "to": "n5"},
                {"id": "e46", "type": "edge", "from": "n4", "to": "n6"},
                {"id": "e56", "type": "edge", "from": "n5", "to": "n6"},
                {"id": "e67", "type": "edge", "from": "n6", "to": "n7"},
            ],
        )
        s.add(wb); await s.flush()
        print("Whiteboard: 1")

        # === 15. 评论 ===
        comments_data = [
            (T[2], "架构初稿已发飞书群，请陈刚、周琳、孙鹏 review。"),
            (T[3], "FastAPI 升级到 0.115，asyncpg 同步走 0.30。"),
            (T[4], "AntD 5.21 升级完成，Tabs/Panel API 有破坏性变更。"),
            (T[0], "启动会 7/30 16:00 已开完，纪要见知识库。"),
            (T[1], "PRD v1.2 已发版，客户反馈 12 条 positive。"),
        ]
        for tgt, txt in comments_data:
            s.add(Comment(
                id=str(uuid.uuid4()),
                content=txt,
                task_id=tgt.id,
                project_id=PID,
                user_id=ADMIN_ID,
            ))
        await s.flush()
        print(f"Comments: {len(comments_data)}")

        # === 16. 通知 ===
        notif_data = [
            ("task_assigned", "任务分配", "您被分配了任务：系统架构设计", "task", T[2].id),
            ("risk_alert", "风险预警", "新风险登记：OpenAI 接口稳定性", "risk", r2.id),
            ("sprint_started", "Sprint 启动", "Sprint 2 - 开发与上线 已开始", "sprint", sp2.id),
            ("okr_update", "OKR 更新", "OKR「成功交付PMI中国 AI-PM v2.0」进度更新为 29%", "objective", okr.id),
            ("change_review", "变更待审", "新变更请求：增加多租户数据隔离", "change_request", cr.id),
        ]
        for ntype, title, content, rel_type, rel_id in notif_data:
            s.add(Notification(
                id=str(uuid.uuid4()),
                user_id=ADMIN_ID, type=ntype,
                title=title, content=content,
                related_type=rel_type, related_id=rel_id,
                is_read=False,
            ))
        await s.flush()
        print(f"Notifications: {len(notif_data)}")

        await s.commit()
        # 写入 manifest，供 _verify_demo.py 读取（避免 ID 硬编码导致校验落空）
        manifest_path = os.path.join(BASE_DIR, ".seed_demo_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump({"project_id": PID, "knowledge_base_id": KBID}, mf, ensure_ascii=False, indent=2)

        print("\n=== SEED COMPLETE ===")
        print(f"Project ID: {PID}")
        print(f"KnowledgeBase ID: {KBID}")
        print(f"Manifest: {manifest_path}")


asyncio.run(main())
