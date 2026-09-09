"""
全量 CRUD 端点验证脚本
测试 Projects / Tasks / Risks / OKRs / Reports 的增删改查
"""
# 本文件是「连真实服务端的手工验证脚本」（硬编码 token + localhost:8000），
# 不是 pytest 单元测试用例；标记为 __test__=False 以免 pytest 误收集其中的 def test(...) 报错。
__test__ = False

import httpx
import json
import sys
from datetime import date

BASE = "http://localhost:8000/api/v1"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwYjg2ZmZhMi03NjQ1LTRiOWItYWZlNi1mNjE1MDZmMDRjMWIiLCJleHAiOjE3ODQzMTE1MTIsInR5cGUiOiJhY2Nlc3MifQ.UdFrJSqlvsn14sYAzkjHWC4LBJVwfacefTGdmU5XkRs"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

results = {"pass": 0, "fail": 0, "details": []}

def test(name, condition, detail=""):
    if condition:
        results["pass"] += 1
        print(f"  [PASS] {name}")
        results["details"].append({"test": name, "status": "PASS", "detail": detail})
    else:
        results["fail"] += 1
        print(f"  [FAIL] {name} - {detail}")
        results["details"].append({"test": name, "status": "FAIL", "detail": detail})

def main():
    client = httpx.Client(timeout=30)
    
    # ===================== PROJECTS =====================
    print("\n========== 1. Projects CRUD ==========")
    
    # CREATE
    proj_data = {
        "name": "CRUD验证项目",
        "description": "全量CRUD端点验证用项目",
        "industry_type": "technology",
        "project_type": "development",
        "priority": 2,
    }
    r = client.post(f"{BASE}/projects", json=proj_data, headers=HEADERS)
    test("POST /projects (创建)", r.status_code == 201, f"status={r.status_code}, body={r.text[:200]}")
    if r.status_code == 201:
        proj_id = r.json().get("id", "")
    else:
        proj_id = ""
    
    # LIST
    r = client.get(f"{BASE}/projects?page=1&page_size=5", headers=HEADERS)
    test("GET /projects (列表)", r.status_code == 200 and r.json().get("total", 0) > 0, f"status={r.status_code}, total={r.json().get('total','?')}")
    
    # READ (if created)
    if proj_id:
        r = client.get(f"{BASE}/projects/{proj_id}", headers=HEADERS)
        test(f"GET /projects/{{id}} (读取)", r.status_code == 200 and r.json().get("name") == "CRUD验证项目", f"name={r.json().get('name','?')}")
        
        # UPDATE
        r = client.put(f"{BASE}/projects/{proj_id}", json={"name": "CRUD验证项目-已更新", "priority": 1}, headers=HEADERS)
        test(f"PUT /projects/{{id}} (更新)", r.status_code == 200 and r.json().get("name") == "CRUD验证项目-已更新", f"name={r.json().get('name','?')}")
        
        # DELETE
        r = client.delete(f"{BASE}/projects/{proj_id}", headers=HEADERS)
        test(f"DELETE /projects/{{id}} (删除)", r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}")
    else:
        test("后续测试依赖项目创建", False, "项目创建失败，跳过依赖测试")
        proj_id = None
        return
    
    # ===================== TASKS =====================
    print("\n========== 2. Tasks CRUD ==========")
    
    # Need a project ID for tasks - create a new one
    r = client.post(f"{BASE}/projects", json={"name": "Task测试项目"}, headers=HEADERS)
    if r.status_code == 201:
        task_proj_id = r.json().get("id", "")
    else:
        task_proj_id = ""
        test("创建Task测试项目", False, f"status={r.status_code}")
    
    if task_proj_id:
        # CREATE Task
        task_data = {
            "project_id": task_proj_id,
            "name": "CRUD测试任务",
            "description": "全量CRUD验证测试任务",
            "priority": 2,
            "status": "todo",
            "estimated_hours": 8,
            "planned_start": "2026-07-18T00:00:00",
            "planned_end": "2026-07-25T00:00:00",
        }
        r = client.post(f"{BASE}/tasks", json=task_data, headers=HEADERS)
        test("POST /tasks (创建)", r.status_code == 201, f"status={r.status_code}, body={r.text[:200]}")
        task_id = r.json().get("id", "") if r.status_code == 201 else ""
        
        # LIST
        r = client.get(f"{BASE}/tasks?project_id={task_proj_id}&page_size=10", headers=HEADERS)
        test("GET /tasks (列表)", r.status_code == 200 and r.json().get("total", 0) >= 0, f"status={r.status_code}")
        
        if task_id:
            # READ
            r = client.get(f"{BASE}/tasks/{task_id}", headers=HEADERS)
            test(f"GET /tasks/{{id}} (读取)", r.status_code == 200 and r.json().get("name") == "CRUD测试任务", f"name={r.json().get('name','?')}")
            
            # UPDATE
            r = client.put(f"{BASE}/tasks/{task_id}", json={"name": "CRUD测试任务-已更新", "priority": 1}, headers=HEADERS)
            test(f"PUT /tasks/{{id}} (更新)", r.status_code == 200 and r.json().get("name") == "CRUD测试任务-已更新", f"name={r.json().get('name','?')}")
            
            # DELETE
            r = client.delete(f"{BASE}/tasks/{task_id}", headers=HEADERS)
            test(f"DELETE /tasks/{{id}} (删除)", r.status_code == 200, f"status={r.status_code}")
    
    # ===================== RISKS =====================
    print("\n========== 3. Risks CRUD ==========")
    
    r = client.post(f"{BASE}/projects", json={"name": "Risk测试项目"}, headers=HEADERS)
    risk_proj_id = r.json().get("id", "") if r.status_code == 201 else ""
    
    if risk_proj_id:
        # CREATE
        risk_data = {
            "project_id": risk_proj_id,
            "name": "CRUD测试风险",
            "description": "全量CRUD验证风险项",
            "category": "technical",
            "probability": 0.6,
            "impact": 0.7,
        }
        r = client.post(f"{BASE}/risks", json=risk_data, headers=HEADERS)
        test("POST /risks (创建)", r.status_code == 201, f"status={r.status_code}, body={r.text[:200]}")
        risk_id = r.json().get("id", "") if r.status_code == 201 else ""
        
        # LIST
        r = client.get(f"{BASE}/risks?project_id={risk_proj_id}", headers=HEADERS)
        test("GET /risks (列表)", r.status_code == 200 and len(r.json()) >= 0, f"status={r.status_code}")
        
        if risk_id:
            # READ
            r = client.get(f"{BASE}/risks/{risk_id}", headers=HEADERS)
            test(f"GET /risks/{{id}} (读取)", r.status_code == 200 and r.json().get("name") == "CRUD测试风险", f"name={r.json().get('name','?')}")
            
            # UPDATE
            r = client.put(f"{BASE}/risks/{risk_id}", json={"name": "CRUD测试风险-已更新", "probability": 0.8}, headers=HEADERS)
            test(f"PUT /risks/{{id}} (更新)", r.status_code == 200 and "已更新" in r.json().get("name", ""), f"name={r.json().get('name','?')}")
            
            # DELETE
            r = client.delete(f"{BASE}/risks/{risk_id}", headers=HEADERS)
            test(f"DELETE /risks/{{id}} (删除)", r.status_code == 200 and r.json().get("ok") == True, f"status={r.status_code}")
    
    # ===================== OKRs =====================
    print("\n========== 4. OKRs CRUD ==========")
    
    # CREATE
    okr_data = {
        "objective": "CRUD验证O1: 提升产品质量",
        "year": "2026",
        "quarter": "Q3",
        "owner": "admin",
        "keyResults": [
            {"title": "KR1: 缺陷率降低", "target": 100, "current": 30, "unit": "%", "progress": 30},
        ]
    }
    r = client.post(f"{BASE}/okrs", json=okr_data, headers=HEADERS)
    test("POST /okrs (创建)", r.status_code == 201, f"status={r.status_code}, body={r.text[:200]}")
    okr_id = r.json().get("id", "") if r.status_code == 201 else ""
    
    # LIST
    r = client.get(f"{BASE}/okrs", headers=HEADERS)
    test("GET /okrs (列表)", r.status_code == 200 and r.json().get("total", 0) >= 0, f"status={r.status_code}")
    
    if okr_id:
        # READ
        r = client.get(f"{BASE}/okrs/{okr_id}", headers=HEADERS)
        test(f"GET /okrs/{{id}} (读取)", r.status_code == 200 and "CRUD验证O1" in r.json().get("objective", ""), f"objective={r.json().get('objective','?')[:30]}")
        
        # UPDATE
        r = client.put(f"{BASE}/okrs/{okr_id}", json={"objective": "CRUD验证O1-已更新: 极致产品质量"}, headers=HEADERS)
        test(f"PUT /okrs/{{id}} (更新)", r.status_code == 200 and "已更新" in r.json().get("objective", ""), f"objective={r.json().get('objective','?')[:30]}")
        
        # DELETE
        r = client.delete(f"{BASE}/okrs/{okr_id}", headers=HEADERS)
        test(f"DELETE /okrs/{{id}} (删除)", r.status_code == 200 and r.json().get("ok") == True, f"status={r.status_code}")
    
    # ===================== REPORTS =====================
    print("\n========== 5. Reports 访问 ==========")
    
    # Templates
    r = client.get(f"{BASE}/reports/templates", headers=HEADERS)
    test("GET /reports/templates", r.status_code == 200, f"status={r.status_code}")
    
    # Daily report
    r = client.get(f"{BASE}/reports/daily?report_date=2026-07-18", headers=HEADERS)
    test("GET /reports/daily", r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}")
    
    # Weekly report
    r = client.get(f"{BASE}/reports/weekly", headers=HEADERS)
    test("GET /reports/weekly", r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}")
    
    # Project status report (create a project first)
    r = client.post(f"{BASE}/projects", json={"name": "Report测试项目"}, headers=HEADERS)
    report_proj_id = r.json().get("id", "") if r.status_code == 201 else ""
    
    if report_proj_id:
        # 项目状态报告依赖AI引擎，需配置LLM API Key
        r = client.get(f"{BASE}/reports/projects/{report_proj_id}/status", headers=HEADERS)
        ai_available = r.status_code == 200
        test("GET /reports/projects/{id}/status (需AI)", ai_available, f"status={r.status_code}{(', 未配置AI Key, 预期行为' if not ai_available else '')}")
        
        # Burndown
        r = client.get(f"{BASE}/reports/burndown?project_id={report_proj_id}", headers=HEADERS)
        test("GET /reports/burndown", r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}")
        
        # Velocity uses date_trunc (PostgreSQL), may fail on SQLite
        r = client.get(f"{BASE}/reports/velocity?project_id={report_proj_id}", headers=HEADERS)
        velocity_ok = r.status_code == 200
        test("GET /reports/velocity", velocity_ok, f"status={r.status_code}{(', date_trunc仅PG支持, SQLite环境预期行为' if not velocity_ok else '')}")
        
        # EVM
        r = client.get(f"{BASE}/reports/evm?project_id={report_proj_id}", headers=HEADERS)
        test("GET /reports/evm", r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}")
        
        # Cumulative Flow
        r = client.get(f"{BASE}/reports/cumulative-flow?project_id={report_proj_id}", headers=HEADERS)
        test("GET /reports/cumulative-flow", r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}")
        
        # Project Progress
        r = client.get(f"{BASE}/reports/project-progress?project_id={report_proj_id}&period=week", headers=HEADERS)
        test("GET /reports/project-progress", r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}")
    
    # ===================== SUMMARY =====================
    print("\n" + "=" * 50)
    print(f"测试总览: {results['pass']} 通过, {results['fail']} 失败")
    print("=" * 50)
    
    # Output JSON for record keeping
    print("\n--- JSON 结果 ---")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    
    return results

if __name__ == "__main__":
    main()
