import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Card, Typography, Tag, Input, Select, Space, App, Drawer,
  Spin, Empty, Table, Tooltip, Alert,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  ApartmentOutlined, NodeIndexOutlined, RobotOutlined, CodeOutlined,
  ThunderboltOutlined, ExperimentOutlined, AppstoreOutlined, TagsOutlined,
  DatabaseOutlined,
} from "@ant-design/icons";
import { pmbokV3Api } from "../api";

const { Title, Text, Paragraph } = Typography;

// ============ 品牌色（通维绿系）============
const BRAND_GREEN = "#27ae60";
const BRAND_DARK_GREEN = "#16a085";
const BRAND_PURPLE = "#6366F1";

// ============ 三层映射维度 ============
const PROCESS_GROUPS = ["启动", "规划", "执行", "监控", "收尾"];
const KNOWLEDGE_AREAS = [
  "整合", "范围", "进度", "成本", "质量",
  "资源", "沟通", "风险", "采购", "干系人",
];

// 来源体系着色
const SYSTEM_COLOR: Record<string, string> = {
  PMBOK: BRAND_GREEN,
  CPMAI: "#F59E0B",
  TAI: BRAND_PURPLE,
};

// ============ 类型契约（后端 V3 数据驱动，字段缺失均兜底）============
interface SkillBoundTo {
  agents?: string[];
  principles?: any[];
  workflows?: any[];
}
interface SkillItem {
  id: string;
  name_cn?: string;
  name_en?: string;
  category?: string;
  source_system?: string;
  source_layers?: string[];
  reuse_count?: number;
  automation_mode?: string;
  definition?: string;
  prompt_template?: string;
  quality_criteria?: string[];
  bound_to?: SkillBoundTo;
  used_by_agent_count?: number;
}
interface AgentItem {
  id: string;
  code?: string;
  name_cn?: string;
  process_group?: string;
  knowledge_area?: string;
  skill_count?: number;
}
interface StatsData {
  skills_total?: number;
  agents_total?: number;
  workflows_total?: number;
  principles_total?: number;
  process_groups?: Record<string, number>;
  knowledge_areas?: { name: string; agents: number; skills: number }[];
  by_system?: Record<string, number>;
}

// 把任意数字安全格式化为千分位；null/undefined/NaN 返回兜底符
const fmt = (n: number | undefined | null, fallback = "—") =>
  typeof n === "number" && !Number.isNaN(n) ? n.toLocaleString("zh-CN") : fallback;

// ============ 组件 ============
const PmbokSkills: React.FC = () => {
  const { message } = App.useApp();

  // 全量 Skill（用于矩阵聚合 / 复用度合计 / 工作流去重 / 本地兜底过滤）
  const [allSkills, setAllSkills] = useState<SkillItem[]>([]);
  // Agent 映射：id -> {process_group, knowledge_area}
  const [agentMap, setAgentMap] = useState<Map<string, { pg: string; ka: string }>>(new Map());
  const [stats, setStats] = useState<StatsData | null>(null);

  const [initialLoading, setInitialLoading] = useState(true);

  // 列表过滤 / 分页
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [sourceSystem, setSourceSystem] = useState<string | undefined>(undefined);
  const [pgFilter, setPgFilter] = useState<string | undefined>(undefined);
  const [kaFilter, setKaFilter] = useState<string | undefined>(undefined);

  const [tableItems, setTableItems] = useState<SkillItem[]>([]);
  const [tableTotal, setTableTotal] = useState(0);
  const [tableLoading, setTableLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);

  // 抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeSkill, setActiveSkill] = useState<SkillItem | null>(null);

  // ============ 计算某个 skill 覆盖的 (pg|ka) 单元集合 ============
  const skillCells = useCallback(
    (s: SkillItem): Set<string> => {
      const cells = new Set<string>();
      const agentIds = s.bound_to?.agents || [];
      for (const aid of agentIds) {
        const m = agentMap.get(aid);
        if (m && PROCESS_GROUPS.includes(m.pg) && KNOWLEDGE_AREAS.includes(m.ka)) {
          cells.add(`${m.pg}|${m.ka}`);
        }
      }
      return cells;
    },
    [agentMap],
  );

  // ============ 矩阵聚合（行=过程组 列=知识领域，数字=该交叉 skill 数）============
  const matrix = useMemo(() => {
    const m: Record<string, Record<string, number>> = {};
    PROCESS_GROUPS.forEach((pg) => {
      m[pg] = {};
      KNOWLEDGE_AREAS.forEach((ka) => (m[pg][ka] = 0));
    });
    for (const s of allSkills) {
      // 同一 skill 在同一 (pg,ka) 单元只计一次（避免多 agent 同单元重复计数）
      const cells = skillCells(s);
      cells.forEach((c) => {
        const [pg, ka] = c.split("|");
        if (m[pg] && m[pg][ka] !== undefined) m[pg][ka] += 1;
      });
    }
    return m;
  }, [allSkills, skillCells]);

  const matrixMax = useMemo(() => {
    let max = 0;
    PROCESS_GROUPS.forEach((pg) =>
      KNOWLEDGE_AREAS.forEach((ka) => (max = Math.max(max, matrix[pg]?.[ka] || 0))),
    );
    return max;
  }, [matrix]);

  // ============ 统计卡片数据（优先 stats()，否则本地聚合兜底）============
  const summary = useMemo(() => {
    const totalSkills = stats?.skills_total ?? allSkills.length;
    // 过程组完成度：至少覆盖 1 个 skill 的过程组数 / 5
    let pgDone = 0;
    PROCESS_GROUPS.forEach((pg) => {
      const rowSum = KNOWLEDGE_AREAS.reduce((s, ka) => s + (matrix[pg]?.[ka] || 0), 0);
      if (rowSum > 0) pgDone += 1;
    });
    // 知识领域覆盖：至少覆盖 1 个 skill 的知识领域数 / 10
    let kaCovered = 0;
    KNOWLEDGE_AREAS.forEach((ka) => {
      const colSum = PROCESS_GROUPS.reduce((s, pg) => s + (matrix[pg]?.[ka] || 0), 0);
      if (colSum > 0) kaCovered += 1;
    });
    // 活跃调用次数：reuse_count 合计
    const reuseSum = allSkills.reduce((s, x) => s + (Number(x.reuse_count) || 0), 0);
    // 已绑定工作流数：bound_to.workflows 去重
    const wfSet = new Set<string>();
    allSkills.forEach((x) => (x.bound_to?.workflows || []).forEach((w: any) => wfSet.add(String(w))));

    return {
      totalSkills,
      pgDone,
      kaCovered,
      reuseSum,
      wfCount: wfSet.size,
      hasData: allSkills.length > 0 || !!stats,
    };
  }, [stats, allSkills, matrix]);

  // ============ 本地兜底过滤（接口未就绪时仍可筛选）============
  const filterLocal = useCallback(
    (list: SkillItem[]): SkillItem[] => {
      const q = debouncedSearch.trim().toLowerCase();
      return list.filter((s) => {
        if (q && !`${s.name_cn || ""} ${s.name_en || ""}`.toLowerCase().includes(q)) return false;
        if (category && s.category !== category) return false;
        if (sourceSystem && s.source_system !== sourceSystem) return false;
        if (pgFilter || kaFilter) {
          const cells = skillCells(s);
          let hit = true;
          if (pgFilter && kaFilter) hit = cells.has(`${pgFilter}|${kaFilter}`);
          else if (pgFilter) hit = [...cells].some((c) => c.startsWith(`${pgFilter}|`));
          else if (kaFilter) hit = [...cells].some((c) => c.endsWith(`|${kaFilter}`));
          if (!hit) return false;
        }
        return true;
      });
    },
    [debouncedSearch, category, sourceSystem, pgFilter, kaFilter, skillCells],
  );

  // ============ 防抖搜索：延迟500ms后执行搜索 ============
  useEffect(() => {
    const timer = setTimeout(() => { setDebouncedSearch(search); }, 500);
    return () => clearTimeout(timer);
  }, [search]);

  // ============ 加载列表 ============
  const loadSkills = useCallback(
    async (nextPage = page, nextSize = pageSize) => {
      setTableLoading(true);
      try {
        const params: any = { page: nextPage, size: nextSize };
        if (debouncedSearch.trim()) params.search = debouncedSearch.trim();
        if (category) params.category = category;
        if (sourceSystem) params.source_system = sourceSystem;
        if (pgFilter) params.process_group = pgFilter;
        if (kaFilter) params.knowledge_area = kaFilter;
        const res = await pmbokV3Api.skills(params);
        const items: SkillItem[] = Array.isArray(res?.items) ? res.items : [];
        const total: number = typeof res?.total === "number" ? res.total : items.length;
        setTableItems(items);
        setTableTotal(total);
      } catch (e: any) {
        // 接口未就绪：用全量数据本地兜底过滤 + 分页
        const filtered = filterLocal(allSkills);
        const start = (nextPage - 1) * nextSize;
        setTableItems(filtered.slice(start, start + nextSize));
        setTableTotal(filtered.length);
      } finally {
        setTableLoading(false);
      }
    },
    [page, pageSize, debouncedSearch, category, sourceSystem, pgFilter, kaFilter, allSkills, filterLocal],
  );

  // ============ 初始加载：stats + agents(映射) + 全量 skills ============
  useEffect(() => {
    (async () => {
      setInitialLoading(true);
      try {
        // 三者并行，任一失败不影响其余
        const [statsRes, agentsRes, skillsRes] = await Promise.all([
          pmbokV3Api.stats().catch(() => null),
          pmbokV3Api.agents({ size: 1000 }).catch(() => null),
          pmbokV3Api.skills({ size: 1000 }).catch(() => null),
        ]);

        if (statsRes) setStats(statsRes);

        // 构建 agent -> (pg,ka) 映射
        const am = new Map<string, { pg: string; ka: string }>();
        const agItems: AgentItem[] = agentsRes?.items || agentsRes?.data?.items || [];
        for (const a of agItems) {
          if (a?.id) am.set(a.id, { pg: a.process_group || "", ka: a.knowledge_area || "" });
        }
        setAgentMap(am);

        // 全量 skills（用于矩阵 / 聚合 / 兜底）
        const skItems: SkillItem[] = skillsRes?.items || skillsRes?.data?.items || [];
        setAllSkills(skItems);
      } catch (e: any) {
        // 整体失败也保持空态而非红屏
        setAllSkills([]);
        setAgentMap(new Map());
      } finally {
        setInitialLoading(false);
        setTableLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 全量数据/筛选变化时刷新列表
  useEffect(() => {
    if (initialLoading) return;
    setPage(1);
    loadSkills(1, pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, category, sourceSystem, pgFilter, kaFilter, initialLoading]);

  // ============ 矩阵单元格点击 ============
  const handleCellClick = (pg: string, ka: string) => {
    const isOn = pgFilter === pg && kaFilter === ka;
    if (isOn) {
      setPgFilter(undefined);
      setKaFilter(undefined);
    } else {
      setPgFilter(pg);
      setKaFilter(ka);
    }
  };

  // ============ 类别 / 来源体系 下拉选项 ============
  const categoryOptions = useMemo(() => {
    const set = new Set<string>();
    allSkills.forEach((s) => s.category && set.add(s.category));
    return [...set].map((c) => ({ value: c, label: c }));
  }, [allSkills]);
  const systemOptions = ["PMBOK", "CPMAI", "TAI"].map((s) => ({ value: s, label: s }));

  // ============ 抽屉明细 ============
  const openDrawer = (s: SkillItem) => {
    setActiveSkill(s);
    setDrawerOpen(true);
  };

  // ============ 表格列 ============
  const columns: ColumnsType<SkillItem> = [
    {
      title: "名称",
      dataIndex: "name_cn",
      key: "name_cn",
      render: (v: any, r) => (
        <Space direction="vertical" size={0}>
          <Text strong>{v || "—"}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.name_en || ""}</Text>
        </Space>
      ),
    },
    { title: "英文", dataIndex: "name_en", key: "name_en", responsive: ["lg"], render: (v: any) => v || "—" },
    { title: "类别", dataIndex: "category", key: "category", responsive: ["md"], render: (v: any) => v || "—" },
    {
      title: "来源体系",
      dataIndex: "source_system",
      key: "source_system",
      render: (v: any) => {
        const c = SYSTEM_COLOR[v] || "#64748B";
        return <Tag color={c} style={{ borderRadius: 10 }}>{v || "—"}</Tag>;
      },
    },
    {
      title: "复用度",
      dataIndex: "reuse_count",
      key: "reuse_count",
      sorter: (a, b) => (Number(a.reuse_count) || 0) - (Number(b.reuse_count) || 0),
      render: (v: any) => <Text strong style={{ color: BRAND_DARK_GREEN }}>{fmt(Number(v) || 0)}</Text>,
    },
    {
      title: "关联 Agent",
      key: "agents",
      render: (_v: any, r) => {
        const n = r.bound_to?.agents?.length || 0;
        return <Tag icon={<RobotOutlined />} color={n ? "green" : "default"}>{n}</Tag>;
      },
    },
    {
      title: "自动化模式",
      dataIndex: "automation_mode",
      key: "automation_mode",
      responsive: ["md"],
      render: (v: any) => {
        if (!v) return "—";
        const map: Record<string, string> = {
          manual: "#94A3B8", auto: BRAND_GREEN, "semi-auto": "#F59E0B", hybrid: BRAND_PURPLE,
        };
        return <Tag color={map[String(v).toLowerCase()] || "default"}>{v}</Tag>;
      },
    },
  ];

  // ============ 统计卡片渲染 ============
  const StatCard: React.FC<{ label: string; value: React.ReactNode; sub: string; icon: React.ReactNode }> = ({
    label, value, sub, icon,
  }) => (
    <div
      className="card-hover"
      style={{
        flex: 1, minWidth: 0, borderRadius: 16, padding: "16px 18px",
        background: `linear-gradient(135deg, ${BRAND_GREEN}, ${BRAND_DARK_GREEN})`,
        color: "#fff", position: "relative", overflow: "hidden",
      }}
    >
      <div style={{ position: "absolute", right: 12, top: 10, opacity: 0.25, fontSize: 28 }}>{icon}</div>
      <div style={{ fontSize: 12, opacity: 0.92 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, marginTop: 4, lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontSize: 11, opacity: 0.85, marginTop: 4 }}>{sub}</div>
    </div>
  );

  if (initialLoading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spin />
        <p style={{ marginTop: 12, color: "#64748B" }}>加载 PMBOK Skills 库…</p>
      </div>
    );
  }

  return (
    <div className="page-container" style={{ maxWidth: 1500 }}>
      {/* ===== 页头 ===== */}
      <div className="page-header">
        <Title level={3} style={{ margin: 0, display: "flex", alignItems: "center", gap: 10 }}>
          <AppstoreOutlined style={{ color: BRAND_GREEN }} />
          PMBOK Skills 库
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          覆盖 PMBOK 第6/7版 ITTO 框架 · 248 个原子化 SOP · 跨 Skill / Agent / Workflow 三层复用
        </Text>
      </div>

      {/* ===== 统计卡区（5 列等宽）===== */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        <StatCard label="总 Skill 数" value={summary.hasData ? fmt(summary.totalSkills) : "—"} sub="原子化工具技术" icon={<TagsOutlined />} />
        <StatCard
          label="过程组完成度"
          value={summary.hasData ? `${summary.pgDone}/5` : "—"}
          sub="5 大过程组已完成"
          icon={<NodeIndexOutlined />}
        />
        <StatCard
          label="知识领域覆盖"
          value={summary.hasData ? `${summary.kaCovered}/10` : "—"}
          sub="10 大知识领域已覆盖"
          icon={<ApartmentOutlined />}
        />
        <StatCard label="活跃调用次数" value={summary.hasData ? fmt(summary.reuseSum) : "—"} sub="Skill 复用度合计" icon={<ThunderboltOutlined />} />
        <StatCard label="已绑定工作流数" value={summary.hasData ? fmt(summary.wfCount) : "—"} sub="跨 Workflow 复用" icon={<ExperimentOutlined />} />
      </div>

      {/* ===== 矩阵视图（核心差异化卖点）===== */}
      <Card
        size="small"
        style={{ marginBottom: 20, borderRadius: 14 }}
        title={
          <Space>
            <DatabaseOutlined style={{ color: BRAND_GREEN }} />
            <Text strong>过程组 × 知识领域 矩阵</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>单元格 = 该交叉下的 Skill 数 · 点击可按过程组+知识领域筛选下方列表</Text>
          </Space>
        }
        extra={
          (pgFilter || kaFilter) && (
            <Tag
              color={BRAND_GREEN}
              closable
              onClose={() => { setPgFilter(undefined); setKaFilter(undefined); }}
              style={{ borderRadius: 10 }}
            >
              筛选：{pgFilter || "*"} / {kaFilter || "*"}
            </Tag>
          )
        }
      >
        {allSkills.length === 0 ? (
          <Empty description="暂无 Skill 数据（接口未就绪，稍后自动加载）" style={{ padding: "24px 0" }} />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <div style={{ minWidth: 720 }}>
              {/* 表头：知识领域 */}
              <div style={{ display: "grid", gridTemplateColumns: `96px repeat(${KNOWLEDGE_AREAS.length}, 1fr)`, gap: 4 }}>
                <div />
                {KNOWLEDGE_AREAS.map((ka) => (
                  <div key={ka} style={{ textAlign: "center", fontSize: 12, fontWeight: 600, color: "#475569", padding: "4px 0" }}>
                    {ka}
                  </div>
                ))}
              </div>
              {/* 每行：过程组 + 单元 */}
              {PROCESS_GROUPS.map((pg) => (
                <div
                  key={pg}
                  style={{ display: "grid", gridTemplateColumns: `96px repeat(${KNOWLEDGE_AREAS.length}, 1fr)`, gap: 4, marginTop: 4 }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 600, color: BRAND_DARK_GREEN }}>
                    {pg}
                  </div>
                  {KNOWLEDGE_AREAS.map((ka) => {
                    const count = matrix[pg]?.[ka] || 0;
                    const intensity = matrixMax > 0 ? (count / matrixMax) : 0;
                    const bg = count === 0 ? "#F1F5F9" : `rgba(39,174,96,${0.12 + 0.88 * intensity})`;
                    const selected = pgFilter === pg && kaFilter === ka;
                    return (
                      <Tooltip key={ka} title={`${pg} · ${ka}：${count} 个 Skill`}>
                        <div
                          onClick={() => handleCellClick(pg, ka)}
                          style={{
                            textAlign: "center", padding: "12px 0", borderRadius: 8,
                            background: bg, cursor: "pointer",
                            color: intensity > 0.55 ? "#fff" : "#0F172A",
                            fontWeight: 700, fontSize: 14,
                            border: selected ? `2px solid ${BRAND_PURPLE}` : "1px solid transparent",
                            transition: "all .15s",
                          }}
                        >
                          {count || "·"}
                        </div>
                      </Tooltip>
                    );
                  })}
                </div>
              ))}
              {/* 色阶图例 */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>少</Text>
                {[0.15, 0.4, 0.65, 0.9].map((t) => (
                  <span key={t} style={{ width: 28, height: 12, borderRadius: 4, background: `rgba(39,174,96,${t})`, display: "inline-block" }} />
                ))}
                <Text type="secondary" style={{ fontSize: 11 }}>多</Text>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* ===== Skill 列表 ===== */}
      <Card size="small" style={{ borderRadius: 14 }} title={<Text strong><TagsOutlined /> Skill 清单</Text>}>
        <Space wrap style={{ marginBottom: 12, width: "100%", justifyContent: "space-between" }}>
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="搜索名称 / 英文"
              style={{ width: 220 }}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onSearch={(v) => setSearch(v)}
            />
            <Select
              allowClear
              placeholder="类别"
              style={{ width: 160 }}
              value={category}
              onChange={setCategory}
              options={categoryOptions}
            />
            <Select
              allowClear
              placeholder="来源体系"
              style={{ width: 150 }}
              value={sourceSystem}
              onChange={setSourceSystem}
              options={systemOptions}
            />
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>共 {fmt(tableTotal)} 个</Text>
        </Space>

        {tableLoading ? (
          <div style={{ padding: 48, textAlign: "center" }}><Spin /></div>
        ) : tableItems.length === 0 ? (
          <Empty description="无匹配 Skill（接口未就绪或筛选无结果）" style={{ padding: "32px 0" }} />
        ) : (
          <Table<SkillItem>
            rowKey={(r) => r.id}
            size="middle"
            columns={columns}
            dataSource={tableItems}
            pagination={{
              current: page,
              pageSize,
              total: tableTotal,
              showSizeChanger: true,
              onChange: (p, ps) => { setPage(p); setPageSize(ps); loadSkills(p, ps); },
            }}
            onRow={(r) => ({ onClick: () => openDrawer(r), style: { cursor: "pointer" } })}
            scroll={{ x: 800 }}
          />
        )}
      </Card>

      {/* ===== 明细抽屉 ===== */}
      <Drawer
        title={
          <Space>
            <CodeOutlined style={{ color: BRAND_GREEN }} />
            <span>{activeSkill?.name_cn || "Skill 详情"}</span>
            {activeSkill?.source_system && (
              <Tag color={SYSTEM_COLOR[activeSkill.source_system] || "default"}>{activeSkill.source_system}</Tag>
            )}
          </Space>
        }
        placement="right"
        width={640}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
      >
        {activeSkill ? (
          <Space direction="vertical" size={14} style={{ width: "100%" }}>
            <Alert
              type="info"
              showIcon
              message="原子化 SOP（Skill 层）"
              description="可被 Agent / Workflow / Principle 三层复用的标准化工具技术单元。"
            />

            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>定义 / Definition</Text>
              <Paragraph style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>
                {activeSkill.definition || "—"}
              </Paragraph>
            </div>

            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>Prompt 模板</Text>
              <pre
                style={{
                  marginTop: 4, background: "#0F172A", color: "#E2E8F0", padding: 12,
                  borderRadius: 8, fontSize: 12, overflowX: "auto", whiteSpace: "pre-wrap",
                }}
              >
                {activeSkill.prompt_template || "—"}
              </pre>
            </div>

            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>质量判定标准（quality_criteria）</Text>
              <ul style={{ marginTop: 4, paddingLeft: 18, marginBottom: 0 }}>
                {(activeSkill.quality_criteria && activeSkill.quality_criteria.length) ? (
                  activeSkill.quality_criteria.map((qc, i) => <li key={i} style={{ fontSize: 13 }}>{qc}</li>)
                ) : (
                  <Text type="secondary">—</Text>
                )}
              </ul>
            </div>

            <div style={{ display: "flex", gap: 24 }}>
              <Space>
                <RobotOutlined style={{ color: BRAND_GREEN }} />
                <Text>关联 Agent 数：</Text>
                <Text strong>{activeSkill.bound_to?.agents?.length || 0}</Text>
              </Space>
              <Space>
                <ExperimentOutlined style={{ color: BRAND_PURPLE }} />
                <Text>关联工作流数：</Text>
                <Text strong>{activeSkill.bound_to?.workflows?.length || 0}</Text>
              </Space>
            </div>

            {activeSkill.automation_mode && (
              <Space>
                <Text type="secondary" style={{ fontSize: 12 }}>自动化模式：</Text>
                <Tag color={BRAND_GREEN}>{activeSkill.automation_mode}</Tag>
              </Space>
            )}
          </Space>
        ) : (
          <div style={{ padding: 48, textAlign: "center" }}><Spin /></div>
        )}
      </Drawer>
    </div>
  );
};

export default PmbokSkills;
