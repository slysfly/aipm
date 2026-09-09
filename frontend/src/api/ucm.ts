/**
 * 用户管理子系统 (UCM) 前端 API 封装
 * 后端路由前缀 /api/v1/ucm
 */
import { get, post, put, del } from "./http";

// ── 组织 / 部门 / 成员 ──────────────────────────────────────
export const listOrganizations = (params?: any) => get("/ucm/organizations", params);
export const getOrgTree = () => get("/ucm/organizations/tree");
export const createOrganization = (body: any) => post("/ucm/organizations", body);
export const getOrganization = (id: string) => get(`/ucm/organizations/${id}`);
export const updateOrganization = (id: string, body: any) => put(`/ucm/organizations/${id}`, body);
export const deleteOrganization = (id: string) => del(`/ucm/organizations/${id}`);

export const listDepartments = (orgId: string) => get(`/ucm/organizations/${orgId}/departments`);
export const createDepartment = (orgId: string, body: any) => post(`/ucm/organizations/${orgId}/departments`, body);
export const deleteDepartment = (orgId: string, deptId: string) => del(`/ucm/organizations/${orgId}/departments/${deptId}`);

export const listMembers = (orgId: string) => get(`/ucm/organizations/${orgId}/members`);
export const addMember = (orgId: string, body: any) => post(`/ucm/organizations/${orgId}/members`, body);
export const updateMember = (orgId: string, userId: string, body: any) => put(`/ucm/organizations/${orgId}/members/${userId}`, body);
export const removeMember = (orgId: string, userId: string) => del(`/ucm/organizations/${orgId}/members/${userId}`);

// 组织充值（默认用户 → 开通/续期套餐）
export const rechargeOrg = (orgId: string, body: any) => post(`/ucm/organizations/${orgId}/recharge`, body);

// ── 用户选择器（组织/部门/成员表单用） ────────────────────────
// 复用 /api/v1/kb-users（kb-users 路由与 ucm 同进程，逻辑一致）：
//   - 同组织用户优先，超管看全部
//   - 支持 q= 模糊搜索 username/full_name/email
//   - 排除自己
export type UserPickerItem = {
  id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
  department?: string | null;
};
export const listUsersForPicker = (q?: string) => {
  const params: any = {};
  if (q && q.trim()) params.q = q.trim();
  return get<UserPickerItem[]>("/kb-users", params);
};

// ── 功能模块 / 套餐 / 开通 ───────────────────────────────────
export const listFeatures = () => get("/ucm/features");
export const createFeature = (body: any) => post("/ucm/features", body);

export const listPlans = () => get("/ucm/plans");
export const createPlan = (body: any) => post("/ucm/plans", body);
export const updatePlan = (id: string, body: any) => put(`/ucm/plans/${id}`, body);

export const getGrants = (orgId: string) => get(`/ucm/organizations/${orgId}/grants`);
export const grantFeature = (orgId: string, body: any) => post(`/ucm/organizations/${orgId}/grants`, body);
export const revokeFeature = (orgId: string, featureCode: string) => del(`/ucm/organizations/${orgId}/grants/${featureCode}`);

// ── 管理权限开通（三档角色：super_admin / admin / user） ────────
export type AdminUserItem = {
  id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
  is_active?: boolean;
  organization_id?: string | null;
  role: "super_admin" | "admin" | "user";
  is_superuser: boolean;
  is_org_admin: boolean;
  last_login?: string | null;
  created_at?: string | null;
};
export const listAdminUsers = (params?: { q?: string }) => get<{ items: AdminUserItem[]; total: number }>("/ucm/grants/users", params);
export const setUserRole = (userId: string, body: { role: string; reason?: string }) => post(`/ucm/grants/users/${userId}/set-role`, body);

// ── 收费 / 退费 ─────────────────────────────────────────────
export const listOrders = (params?: any) => get("/ucm/orders", params);
export const createOrder = (body: any) => post("/ucm/orders", body);
export const payOrder = (orderId: string, body: any) => post(`/ucm/orders/${orderId}/pay`, body);

export const listRefunds = () => get("/ucm/refunds");
export const createRefund = (body: any) => post("/ucm/refunds", body);
export const approveRefund = (id: string) => post(`/ucm/refunds/${id}/approve`);
export const rejectRefund = (id: string) => post(`/ucm/refunds/${id}/reject`);

export const listTransactions = () => get("/ucm/transactions");

// ── 等级 ────────────────────────────────────────────────────
export const listLevels = () => get("/ucm/user-levels");
export const createLevel = (body: any) => post("/ucm/user-levels", body);
export const getUserLevel = (userId: string) => get(`/ucm/users/${userId}/level`);
export const setUserLevel = (userId: string, body: any) => post(`/ucm/users/${userId}/level`, body);
export const getLevelRecords = (userId: string) => get(`/ucm/users/${userId}/level-records`);

// ── 看板 ────────────────────────────────────────────────────
export const getDashboardSummary = () => get("/ucm/summary");
