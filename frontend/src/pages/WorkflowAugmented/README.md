# 智能工作流编排增强版

> 独立页面，不影响现有代码

## 快速开始

### 1. 添加路由（修改 App.tsx）

```typescript
// 在 import 区域添加
const WorkflowAugmented = lazy(() => import("./pages/WorkflowAugmented/WorkflowAugmented"));

// 在 <Routes> 中添加
<Route path="/workflow-augmented" element={<WorkflowAugmented />} />
```

### 2. 添加菜单入口（修改 MainLayout.tsx）

```typescript
{
  label: '智能工作流编排',
  icon: <ThunderboltOutlined />,
  path: '/workflow-augmented',
}
```

### 3. 构建部署

```bash
cd frontend
npm run build
```

## 功能特性

### 1. Agent集成
- ✅ 读取AIPM全部10个领域Agent
- ✅ 显示Agent状态（在线/离线）
- ✅ 显示Agent准确率
- ✅ 显示Agent输入/输出/工具

### 2. 可视化编排
- ✅ 拖拽添加Agent节点
- ✅ 点击添加Agent节点
- ✅ 自动连线验证
- ✅ 实时错误提示

### 3. 智能验证
- ✅ 输入输出类型匹配检查
- ✅ 循环依赖检测
- ✅ 工具可用性检查
- ✅ 孤立节点警告

### 4. 工作流程
- ✅ 一键运行
- ✅ 实时进度显示
- ✅ 执行历史查看
- ✅ 导出工作流JSON

### 5. 视觉体验
- ✅ 深色科技风主题
- ✅ 玻璃态节点效果
- ✅ 动态连线动画
- ✅ 平滑过渡效果

## 预置模板

### PMBOK全流程模板
```
决策建议 → WBS生成 → 报告生成 → EVM分析 → 合规审计
```
- 节点数：5
- 连线数：4
- 适用场景：完整项目管理流程

### 极简工作流模板
```
决策建议 → 风险检测 → 报告生成
```
- 节点数：3
- 连线数：2
- 适用场景：快速启动项目

## 技术栈

- React 18 + TypeScript
- React Flow 11.x（可视化引擎）
- Framer Motion（动画）
- Axios（API调用）
- CSS Modules + Tailwind

## 风险控制

- ✅ 新建独立目录 `WorkflowAugmented/`
- ✅ 不修改任何现有文件
- ✅ 独立路由 `/workflow-augmented`
- ✅ 可随时启用或禁用
- ✅ 回滚只需删除文件和移除路由

## API端点

### 已有API（复用）
- `GET /api/v1/agents` - 获取Agent目录
- `POST /api/v1/agents/run` - 运行Agent
- `GET /api/v1/workflows` - 获取工作流列表
- `POST /api/v1/workflows` - 创建工作流
- `POST /api/v1/workflows/{id}/run` - 执行工作流

### 新增API（可选）
如需高级功能，可考虑新增：
- `GET /api/v1/agents/{id}/tools` - 获取Agent工具列表
- `GET /api/v1/agents/{id}/tools/{toolId}/status` - 检查工具可用性
- `POST /api/v1/workflows/validate` - 验证工作流连接

## 下一步

等待用户确认：
1. 路由路径是否使用 `/workflow-augmented`
2. 菜单入口位置
3. 是否需要同步修改App.tsx和MainLayout.tsx
4. 开发启动时间

---

**当前状态**：开发完成，等待集成确认
