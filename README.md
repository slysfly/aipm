# 通维 AIPM / Tongwei AIPM

**AIPM（AI-PM · 智能项目管理系统）** is an AI-augmented project-management platform built for the PMI China AI Project-Management community, developed by 北京通维管理咨询有限公司 (Beijing Tongwei Management Consulting Co., Ltd.).

通维 AIPM 是北京通维管理咨询有限公司面向 PMI 中国·AI 项目管理社区打造的 **AI 增强型智能项目管理平台**。

---

## 🌐 Language / 当前版本说明

> **Currently this release ships the Chinese (Simplified) version only.**
> The full English localization is planned for a future release. /
>
> **当前版本仅含中文（简体）界面与文档。** 英文完整版计划在后续版本提供。

> **This repository currently contains the Chinese version only. The complete bilingual (EN) localization is on the roadmap.** /
> **本仓库当前仅包含中文版。完整的中英双语（英文）本地化已列入后续路线图。**

---

## ✨ Highlights / 特性

- **130 AI Agents** across PMBOK, CPMAI and more (100% coverage of the 10 PMBOK knowledge areas). / 覆盖 130 个 AI Agent（PMBOK、CPMAI 等，100% 覆盖 PMBOK 十大知识领域）。
- **49 PMBOK Skills** — the full set of PMBOK 49 processes, difficulty-tagged. / 49 个 PMBOK 技能（覆盖全部 49 过程，含难度分级）。
- **13 Workflows** (87 nodes) with a visual canvas. / 13 条工作流（87 节点），可视化画布。
- **RAG + LLM** pipeline (BAAI/bge-small-zh-v1.5) for context-aware answers. / 基于 RAG + 大模型的上下文感知问答。
- **Unified SSO** across all Tongwei sub-sites. / 通维各子站统一 SSO 认证。
- **PWA + Service Worker** for offline-ready access. / PWA + Service Worker，支持离线访问。

---

## 📦 Contents / 仓库结构

| Directory | Description / 说明 |
|---|---|
| `backend/` | FastAPI (Python 3.12) service, SQLite seed DB, Agent/Skill/Workflow libraries / 后端 FastAPI + SQLite 种子库 + Agent/Skill/Workflow 库 |
| `frontend/` | React + TypeScript + Vite + Ant Design 5 SPA / 前端 React + Vite + Ant Design |
| `backend/requirements.txt` | Python dependencies / Python 依赖 |
| `frontend/package.json` | Node dependencies / Node 依赖 |
| `LICENSE` | MIT / MIT 协议 |

---

## 🚀 Quick Start / 快速开始

### Backend / 后端

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m app.main          # serves on :8000
```

### Frontend / 前端

```bash
cd frontend
npm install
npm run dev                # dev server
npm run build              # production build -> dist/
```

> **Note / 提示**：数据库 `backend/tw_ai_pms.db` 为种子库（本仓库未包含，请从部署环境获取）。`.env` 需自行配置（参考 `.env.example`）。

### 演示账号 / Demo Credentials

- **AIPM 地址 / AIPM URL**: https://aipm.pmi.bj.cn
- **账号 / Username**: `admin`
- **密码 / Password**: `admin123`

> ⚠️ 演示环境账号仅用于体验，生产环境请务必修改密码。 /
> Demo credentials are for trial only — change the password in production.

---

## ⚖️ License / 开源协议

This project is licensed under the **MIT License** — see [LICENSE](./LICENSE).

本项目采用 **MIT 协议** 开源，详见 [LICENSE](./LICENSE)。

---

## 🏢 关于通维 / About Tongwei

- **公司 / Company**: 北京通维管理咨询有限公司
- **品牌 / Brand**: 通维咨询
- **口号 / Slogan**: 通万物之变，维四海之安
- **产品 / Products**: AIPM · AI问道（AI-Wendao）
- **核心方法 / Core Methodology**: OCE-TRANSFORM™

## 👥 社区 / Community

本项目的用户社区与技术支持方：

- **使用方 / User Community**: PMI 中国 AI 项目管理社区
- **技术支持 / Technical Support**: 北京通维管理咨询有限公司
- **官网 / Official Site**: https://www.pmi.bj.cn
- **AIPM / AIPM**: https://aipm.pmi.bj.cn
- **联系 / Contact**: [jiafei@twzx.bj.cn](mailto:jiafei@twzx.bj.cn)
- 需要进社区群的，请通过邮箱联系 / To join the community group, please reach out via email。
- **官网联系方式状态 / Official-site contact status**：官网（www.pmi.bj.cn）联系方式页面尚在完善中，最新联系方式以本仓库与邮箱为准 / The official site's contact page is still being finalized; refer to this repo and the email above for the latest contact info。

详见 [COMMUNITY.md](./COMMUNITY.md) / See [COMMUNITY.md](./COMMUNITY.md) for details。

> *本仓库当前仅含中文版。完整双语版本见后续发布。*
