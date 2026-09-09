"""
PMI中国AI项目管理社区 - 关键路径 / CPM 算法模块（PMBOK 增强版）

支持：
  - 四种依赖关系类型：FS / FF / SS / SF（PMBOK 第6章 活动排序）
  - 正/负延隔时间（Lag）
  - 完整前向/后向传递（含多关系约束）
  - AON 紧前逻辑关系图数据生成
  - 甘特图条形数据输出

PMBOK 参考：
  - PMBOK®指南 第6章 项目进度管理
  - 6.3.2.2 紧前绘图法（Precedence Diagramming Method, PDM / AON）
  - 表 6-3 依赖关系类型与延隔
"""

from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from collections import defaultdict, deque
import math


@dataclass
class TaskNode:
    """任务节点（含完整时间参数）"""
    id: str
    name: str
    duration: int              # 工期（天，>=1）
    earliest_start: int = 0    # ES — 最早开始
    earliest_finish: int = 0   # EF — 最早完成
    latest_start: int = 0      # LS — 最晚开始
    latest_finish: int = 0     # LF — 最晚完成
    total_float: int = 0       # TF — 总浮动
    free_float: int = 0        # FF — 自由浮动
    is_critical: bool = False


@dataclass
class Dependency:
    """依赖关系（PMBOK 四种类型）"""
    predecessor_id: str
    successor_id: str
    dependency_type: str = "FS"   # FS | FF | SS | SF
    lag_time: int = 0             # 延隔天数（正=滞后，负=提前）


# ── PMBOK 依赖类型前向传递约束 ────────────────────────────────────────
# FS: successor.EF >= predecessor.EF + lag  →  successor.ES >= predecessor.EF + lag
# SS: successor.ES >= predecessor.ES + lag
# FF: successor.EF >= predecessor.EF + lag  →  successor.ES >= predecessor.EF + lag - dur
# SF: successor.EF >= predecessor.ES + lag →  successor.ES >= predecessor.ES + lag - dur

def _forward_constraint(
    pred: TaskNode,
    succ: TaskNode,
    dep_type: str,
    lag: int,
) -> int:
    """根据依赖类型计算紧前约束下 successor 的最小 ES"""
    if dep_type == "FS":
        return pred.earliest_finish + lag          # 完成→开始
    elif dep_type == "SS":
        return pred.earliest_start + lag            # 开始→开始
    elif dep_type == "FF":
        return pred.earliest_finish + lag - succ.duration  # 完成→完成
    elif dep_type == "SF":
        return pred.earliest_start + lag - succ.duration   # 开始→完成
    else:
        return pred.earliest_finish + lag           # 默认 FS


# ── PMBOK 依赖类型后向传递约束 ────────────────────────────────────────
# FS: predecessor.LF <= successor.LS - lag
# SS: predecessor.LS <= successor.LS - lag
# FF: predecessor.LF <= successor.LF - lag
# SF: predecessor.LS <= successor.LF - lag

def _backward_constraint(
    pred: TaskNode,
    succ: TaskNode,
    dep_type: str,
    lag: int,
) -> Optional[int]:
    """
    根据依赖类型计算约束下 predecessor 的最大 LF 或 LS。
    返回 None 表示该关系不约束 predecessor 的 LF。
    返回 int 时为 predecessor 的 LF 上限。
    """
    if dep_type == "FS":
        return succ.latest_start - lag             # predecessor.LF ≤ successor.LS - lag
    elif dep_type == "SS":
        return None                                 # 不直接约束 LF
    elif dep_type == "FF":
        return succ.latest_finish - lag            # predecessor.LF ≤ successor.LF - lag
    elif dep_type == "SF":
        return None                                 # 不直接约束 LF
    else:
        return succ.latest_start - lag


def _backward_ls_constraint(
    pred: TaskNode,
    succ: TaskNode,
    dep_type: str,
    lag: int,
) -> Optional[int]:
    """根据依赖类型计算约束下 predecessor 的最大 LS 上限。返回 None 表示不约束 LS。"""
    if dep_type == "SS":
        return succ.latest_start - lag             # predecessor.LS ≤ successor.LS - lag
    elif dep_type == "SF":
        return succ.latest_finish - lag            # predecessor.LS ≤ successor.LF - lag
    elif dep_type == "FS" or dep_type == "FF":
        return None                                 # 已在 LF 约束中处理
    else:
        return None


class GanttAlgorithmService:
    """甘特图 / CPM 算法服务（PMBOK 增强版）"""

    @staticmethod
    def compute_cpm_schedule(
        tasks: List[Dict],
        dependencies: List[Dict],
    ) -> Dict:
        """
        关键路径法（CPM）完整调度计算 —— 支持 FS/FF/SS/SF 四种依赖 + 延隔。

        Args:
            tasks: 任务列表，每个含 id, name, duration（工期，天，>=1）
            dependencies: 依赖列表，每个含 predecessor_id, successor_id,
                          dependency_type（默认"FS"）, lag_time（默认0）

        Returns:
            {
                "tasks": {task_id: TaskNode},
                "critical_path": [有序关键路径任务ID列表],
                "project_end": 项目总工期（天）,
                "dependencies": [Dependency 对象列表]
            }
        """
        if not tasks:
            return {"tasks": {}, "critical_path": [], "project_end": 0, "dependencies": []}

        # 构建节点
        nodes = {
            t['id']: TaskNode(
                id=t['id'],
                name=t['name'],
                duration=max(1, int(t.get('duration', 1))),
            )
            for t in tasks
        }

        # 解析依赖（带类型和延隔）
        deps: List[Dependency] = []
        successors: Dict[str, List[Tuple[str, Dependency]]] = defaultdict(list)
        predecessors: Dict[str, List[Tuple[str, Dependency]]] = defaultdict(list)

        for dep in dependencies:
            pred_id = dep.get('predecessor_id')
            succ_id = dep.get('successor_id')
            dep_type = dep.get('dependency_type', 'FS')
            lag = int(dep.get('lag_time', 0))
            if pred_id in nodes and succ_id in nodes and pred_id != succ_id:
                d = Dependency(
                    predecessor_id=pred_id,
                    successor_id=succ_id,
                    dependency_type=dep_type,
                    lag_time=lag,
                )
                deps.append(d)
                successors[pred_id].append((succ_id, d))
                predecessors[succ_id].append((pred_id, d))

        # 拓扑排序（Kahn 算法，自动跳过环）
        indeg = {nid: len(predecessors[nid]) for nid in nodes}
        queue = deque([nid for nid in nodes if indeg[nid] == 0])
        topo: List[str] = []
        while queue:
            nid = queue.popleft()
            topo.append(nid)
            for _, d in successors[nid]:
                indeg[d.successor_id] -= 1
                if indeg[d.successor_id] == 0:
                    queue.append(d.successor_id)

        # ═══ 前向传递（Forward Pass）：计算 ES / EF ═══
        for nid in topo:
            node = nodes[nid]
            if not predecessors[nid]:
                node.earliest_start = 0
            else:
                # 取所有紧前关系的最大约束值
                max_es = 0
                for _, d in predecessors[nid]:
                    pred_node = nodes[d.predecessor_id]
                    constraint_es = _forward_constraint(
                        pred_node, node, d.dependency_type, d.lag_time
                    )
                    max_es = max(max_es, constraint_es)
                node.earliest_start = max_es
            node.earliest_finish = node.earliest_start + node.duration

        project_end = max((n.earliest_finish for n in nodes.values()), default=0)

        # ═══ 后向传递（Backward Pass）：计算 LS / LF ═══
        for nid in reversed(topo):
            node = nodes[nid]
            if not successors[nid]:
                node.latest_finish = project_end
            else:
                # 取所有紧后关系的最小约束值（LF 约束）
                min_lf = float('inf')
                for _, d in successors[nid]:
                    succ_node = nodes[d.successor_id]
                    lf_constr = _backward_constraint(
                        node, succ_node, d.dependency_type, d.lag_time
                    )
                    if lf_constr is not None:
                        min_lf = min(min_lf, lf_constr)
                if min_lf == float('inf'):
                    node.latest_finish = project_end
                else:
                    node.latest_finish = min_lf
            node.latest_start = node.latest_finish - node.duration

        # 第二遍后向传递：处理 SS/SF 对 LS 的约束
        changed = True
        iterations = 0
        while changed and iterations < len(nodes) * 2:
            changed = False
            iterations += 1
            for nid in reversed(topo):
                node = nodes[nid]
                if not successors[nid]:
                    continue
                for _, d in successors[nid]:
                    succ_node = nodes[d.successor_id]
                    ls_constr = _backward_ls_constraint(
                        node, succ_node, d.dependency_type, d.lag_time
                    )
                    if ls_constr is not None and ls_constr < node.latest_start:
                        old_ls = node.latest_start
                        node.latest_start = ls_constr
                        node.latest_finish = node.latest_start + node.duration
                        if node.latest_start != old_ls:
                            changed = True

        # ═══ 浮动时间与关键路径判定 ═══
        for node in nodes.values():
            node.total_float = node.latest_start - node.earliest_start
            if successors[node.id]:
                node.free_float = min(
                    nodes[s].earliest_start for s, _ in successors[node.id]
                ) - node.earliest_finish
            else:
                node.free_float = 0
            node.is_critical = node.total_float <= 0

        # ═══ 有序关键路径提取（拓扑序内的关键子链） ═══
        critical_ids = [nid for nid in topo if nodes[nid].is_critical]
        crit_pred = {nid: [p for p, _ in predecessors[nid] if nodes[p].is_critical] for nid in critical_ids}
        crit_succ = {nid: [s for s, _ in successors[nid] if nodes[s].is_critical] for nid in critical_ids}
        c_indeg = {nid: len(crit_pred[nid]) for nid in critical_ids}
        ordered: List[str] = []
        q = deque(sorted(
            [nid for nid in critical_ids if c_indeg[nid] == 0],
            key=lambda x: (nodes[x].earliest_start, x),
        ))
        while q:
            nid = q.popleft()
            ordered.append(nid)
            for s in sorted(crit_succ[nid], key=lambda x: (nodes[x].earliest_start, x)):
                c_indeg[s] -= 1
                if c_indeg[s] == 0:
                    q.append(s)
        for nid in critical_ids:
            if nid not in ordered:
                ordered.append(nid)

        return {
            "tasks": nodes,
            "critical_path": ordered,
            "project_end": project_end,
            "dependencies": deps,
        }

    @staticmethod
    def generate_network_diagram_data(
        nodes: Dict[str, TaskNode],
        dependencies: List[Dependency],
        task_names: Dict[str, str],
        task_extra: Optional[Dict[str, Dict]] = None,
    ) -> Dict:
        """
        生成 AON 紧前逻辑关系图数据（PMBOK Activity-on-Node Network Diagram）。

        节点布局采用层次算法（按 ES 分层），边携带依赖类型标签。

        Returns:
            {
                "nodes": [{id, name, x, y, es, ef, ls, lf, tf, ff, isCritical, ...}],
                "edges": [{source, target, label, type}],
                "layout": {width, height, levels}
            }
        """
        if not nodes:
            return {"nodes": [], "edges": [], "layout": {"width": 800, "height": 600, "levels": 0}}

        extra = task_extra or {}

        # 按 ES 分层（同一 ES 值归入一层）
        es_groups: Dict[int, List[str]] = defaultdict(list)
        for nid, n in nodes.items():
            es_groups[n.earliest_start].append(nid)

        levels = sorted(es_groups.keys())
        level_count = len(levels)
        level_map = {es: idx for idx, es in enumerate(levels)}

        # 布局参数
        NODE_W, NODE_H = 160, 80       # 节点尺寸
        H_GAP, V_GAP = 40, 30          # 水平/垂直间距
        MARGIN = 60

        # 计算每层宽度
        level_widths = {es: len(members) * (NODE_W + H_GAP) - H_GAP for es, members in es_groups.items()}
        max_width = max(level_widths.values()) if level_widths else NODE_W
        canvas_w = max_width + 2 * MARGIN
        canvas_h = level_count * (NODE_H + V_GAP) - V_GAP + 2 * MARGIN

        # 生成节点数据
        diagram_nodes = []
        for es in levels:
            members = es_groups[es]
            lvl_idx = level_map[es]
            y = MARGIN + lvl_idx * (NODE_H + V_GAP)
            row_w = len(members) * (NODE_W + H_GAP) - H_GAP
            x_start = MARGIN + (max_width - row_w) // 2
            for col, nid in enumerate(members):
                n = nodes[nid]
                x = x_start + col * (NODE_W + H_GAP)
                ex = extra.get(nid, {})
                node_data = {
                    "id": nid,
                    "name": task_names.get(nid, n.name),
                    "shortName": (task_names.get(nid, n.name)[:12] + "..") if len(task_names.get(nid, n.name)) > 12 else task_names.get(nid, n.name),
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "es": n.earliest_start,
                    "ef": n.earliest_finish,
                    "ls": n.latest_start,
                    "lf": n.latest_finish,
                    "tf": n.total_float,
                    "ff": n.free_float,
                    "isCritical": n.is_critical,
                    "duration": n.duration,
                    "level": lvl_idx,
                    "progress": ex.get("progress", 0),
                    "status": ex.get("status", ""),
                    "wbsCode": ex.get("wbs_code", ""),
                }
                diagram_nodes.append(node_data)

        # 生成边数据（依赖关系）
        diagram_edges = []
        type_labels = {
            "FS": "FS",
            "FF": "FF",
            "SS": "SS",
            "SF": "SF",
        }
        for d in dependencies:
            if d.predecessor_id in nodes and d.successor_id in nodes:
                label = type_labels.get(d.dependency_type, "FS")
                if d.lag_time != 0:
                    sign = "+" if d.lag_time > 0 else ""
                    label += f"{sign}{d.lag_time}d"
                diagram_edges.append({
                    "source": d.predecessor_id,
                    "target": d.successor_id,
                    "label": label,
                    "type": d.dependency_type,
                    "lag": d.lag_time,
                })

        return {
            "nodes": diagram_nodes,
            "edges": diagram_edges,
            "layout": {
                "width": canvas_w,
                "height": canvas_h,
                "levels": level_count,
                "nodeSize": {"w": NODE_W, "h": NODE_H},
            },
        }

    @staticmethod
    def generate_gantt_bar_data(
        nodes: Dict[str, TaskNode],
        anchor_date: date,
        task_info: Dict[str, Dict],
        critical_ids: Set[str],
    ) -> List[Dict]:
        """
        生成 echarts 甘特图条形数据。

        Returns:
            [{taskId, name, start, end, progress, status, priority, isCritical,
              es, ef, ls, lf, tf, wbsCode, assigneeName, ...}]
        """
        bars = []
        for nid, n in nodes.items():
            info = task_info.get(nid, {})
            start = anchor_date + timedelta(days=n.earliest_start)
            end = anchor_date + timedelta(days=n.earliest_finish)
            bars.append({
                "taskId": nid,
                "name": info.get("name", n.name),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration": n.duration,
                "progress": info.get("progress", 0),
                "status": info.get("status", ""),
                "priority": info.get("priority", 2),
                "isCritical": nid in critical_ids,
                "es": n.earliest_start,
                "ef": n.earliest_finish,
                "ls": n.latest_start,
                "lf": n.latest_finish,
                "tf": n.total_float,
                "ff": n.free_float,
                "wbsCode": info.get("wbs_code", ""),
                "assigneeName": info.get("assignee_name"),
                "dependencyIds": info.get("dependency_ids", []),
            })
        # 排序：ES → 关键优先 → WBS → 名称
        bars.sort(key=lambda b: (b["es"], not b["isCritical"], b["wbsCode"] or "zzz", b["name"]))
        return bars

    @staticmethod
    def detect_circular_dependencies(
        tasks: List[str],
        dependencies: List[Tuple[str, str]],
    ) -> List[List[str]]:
        """检测循环依赖（DFS 三色标记）"""
        graph = defaultdict(list)
        for pred, succ in dependencies:
            graph[pred].append(succ)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {t: WHITE for t in tasks}
        cycles = []

        def dfs(node: str, path: List[str]) -> Optional[List[str]]:
            color[node] = GRAY
            path.append(node)
            for neighbor in graph[node]:
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    cycle_start = path.index(neighbor) if neighbor in path else 0
                    return path[cycle_start:] + [neighbor]
                if color[neighbor] == WHITE:
                    result = dfs(neighbor, path.copy())
                    if result:
                        return result
            path.pop()
            color[node] = BLACK
            return None

        for task in tasks:
            if color.get(task) == WHITE:
                cycle = dfs(task, [])
                if cycle:
                    cycles.append(cycle)

        return cycles
