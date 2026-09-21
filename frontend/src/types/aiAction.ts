// AI 项目经理「直接操作系统」操作卡片相关类型

export interface AiAction {
  action: string; // create_task | update_task_status
  name?: string; // create_task 标题（必填）
  description?: string;
  priority?: number; // 1-5 整数
  status?: string; // update_task_status 目标状态
  task_ref?: string; // update_task_status 引用的 8 位短 ID（或完整 UUID）
  task_id?: string; // 兼容字段
  planned_start?: string; // YYYY-MM-DD
  planned_end?: string;
  [k: string]: any;
}

export interface AiActionResult {
  action_type: string;
  task_id?: string;
  status: string; // ok | error
  error?: string;
  created_task_id?: string;
}
