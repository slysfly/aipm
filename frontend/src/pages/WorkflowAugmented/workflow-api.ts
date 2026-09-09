/**
 * AIPM 智能工作流编排 - API集成层
 * 独立模块，等待用户确认后集成到App.tsx
 */

import axios from 'axios';

const API_BASE = '/api/v1';

// ============ Agent目录API ============
export const agentApi = {
  /**
   * 获取全部Agent目录
   */
  listAgents: async (): Promise<any> => {
    const response = await axios.get(`${API_BASE}/agents`);
    return response.data;
  },
  
  /**
   * 获取Agent详情
   */
  getAgent: async (agentId: string): Promise<any> => {
    const response = await axios.get(`${API_BASE}/agents/${agentId}`);
    return response.data;
  },
  
  /**
   * 运行单个Agent
   */
  runAgent: async (agentId: string, options: {
    projectId?: string;
    input?: string;
    tools?: string[];
  }): Promise<any> => {
    const response = await axios.post(
      `${API_BASE}/agents/run`,
      { agent_type: agentId, ...options }
    );
    return response.data;
  },
  
  /**
   * 检查工具可用性
   */
  checkTool: async (agentId: string, toolId: string): Promise<boolean> => {
    const response = await axios.get(`${API_BASE}/agents/${agentId}/tools/${toolId}/status`);
    return response.data.available;
  },
};

// ============ 工作流API ============
export const workflowApi = {
  /**
   * 获取工作流列表
   */
  listWorkflows: async (): Promise<any> => {
    const response = await axios.get(`${API_BASE}/workflows`);
    return response.data;
  },
  
  /**
   * 创建工作流
   */
  createWorkflow: async (data: {
    name: string;
    description?: string;
    steps: any[];
  }): Promise<any> => {
    const response = await axios.post(`${API_BASE}/workflows`, data);
    return response.data;
  },
  
  /**
   * 获取工作流详情
   */
  getWorkflow: async (workflowId: string): Promise<any> => {
    const response = await axios.get(`${API_BASE}/workflows/${workflowId}`);
    return response.data;
  },
  
  /**
   * 更新工作流
   */
  updateWorkflow: async (workflowId: string, data: any): Promise<any> => {
    const response = await axios.patch(`${API_BASE}/workflows/${workflowId}`, data);
    return response.data;
  },
  
  /**
   * 删除工作流
   */
  deleteWorkflow: async (workflowId: string): Promise<void> => {
    await axios.delete(`${API_BASE}/workflows/${workflowId}`);
  },
  
  /**
   * 验证工作流连接
   */
  validateWorkflow: async (steps: any[]): Promise<any> => {
    const response = await axios.post(`${API_BASE}/workflows/validate`, { steps });
    return response.data;
  },
  
  /**
   * 执行工作流
   */
  runWorkflow: async (workflowId: string, projectId?: string): Promise<any> => {
    const response = await axios.post(
      `${API_BASE}/workflows/${workflowId}/run`,
      { project_id: projectId }
    );
    return response.data;
  },
  
  /**
   * 获取工作流运行状态
   */
  getWorkflowRun: async (runId: string): Promise<any> => {
    const response = await axios.get(`${API_BASE}/workflows/runs/${runId}`);
    return response.data;
  },
  
  /**
   * 生成分享链接
   */
  shareWorkflow: async (workflowId: string, days?: number): Promise<any> => {
    const response = await axios.post(
      `${API_BASE}/workflows/${workflowId}/share`,
      { days: days || 30 }
    );
    return response.data;
  },
  
  /**
   * 获取分享的工作流
   */
  getSharedWorkflow: async (token: string): Promise<any> => {
    const response = await axios.get(`${API_BASE}/workflows/share/${token}`);
    return response.data;
  },
};

// ============ 模板管理API ============
export const templateApi = {
  /**
   * 获取预设模板列表
   */
  listTemplates: async (): Promise<any[]> => {
    // 本地预设模板
    return [
      {
        id: 'pmbok_full',
        name: 'PMBOK全流程',
        description: '完整的PMBOK六阶段工作流',
        badge: '标准模板',
        nodeCount: 5,
        edgeCount: 4,
      },
      {
        id: 'minimal',
        name: '极简工作流',
        description: '快速开始，仅3步核心流程',
        badge: '极简',
        nodeCount: 3,
        edgeCount: 2,
      },
    ];
  },
  
  /**
   * 获取模板详情
   */
  getTemplate: async (templateId: string): Promise<any> => {
    // 从本地模板库返回
    const templates: Record<string, any> = {
      pmbok_full: {
        name: 'PMBOK全流程',
        description: '完整的PMBOK六阶段工作流',
        badge: '标准模板',
        nodes: [
          { id: 'init', agentId: 'decision', x: 100, y: 300 },
          { id: 'plan', agentId: 'wbs', x: 350, y: 300 },
          { id: 'exec', agentId: 'report', x: 600, y: 300 },
          { id: 'monitor', agentId: 'evm', x: 850, y: 300 },
          { id: 'close', agentId: 'compliance', x: 1100, y: 300 },
        ],
        edges: [
          { id: 'e1', source: 'init', target: 'plan' },
          { id: 'e2', source: 'plan', target: 'exec' },
          { id: 'e3', source: 'exec', target: 'monitor' },
          { id: 'e4', source: 'monitor', target: 'close' },
        ],
      },
      minimal: {
        name: '极简工作流',
        description: '快速开始，仅3步核心流程',
        badge: '极简',
        nodes: [
          { id: 'step1', agentId: 'decision', x: 150, y: 300 },
          { id: 'step2', agentId: 'risk', x: 450, y: 300 },
          { id: 'step3', agentId: 'report', x: 750, y: 300 },
        ],
        edges: [
          { id: 'e1', source: 'step1', target: 'step2' },
          { id: 'e2', source: 'step2', target: 'step3' },
        ],
      },
    };
    
    return templates[templateId] || null;
  },
};

// ============ 连接验证器 ============
export class ConnectionValidator {
  /**
   * 验证两个Agent之间的连接是否合法
   */
  static validateConnection(
    sourceAgent: any,
    targetAgent: any
  ): { valid: boolean; errors: string[]; warnings: string[] } {
    const errors: string[] = [];
    const warnings: string[] = [];
    
    // 1. 检查输入输出匹配
    const hasCommonOutput = sourceAgent.outputs?.some(output =>
      targetAgent.inputs?.some(input => 
        this.isCompatible(output, input)
      )
    );
    
    if (!hasCommonOutput) {
      warnings.push(`${sourceAgent.name} 的输出与 ${targetAgent.name} 的输入类型不匹配`);
    }
    
    // 2. 检查循环依赖（简化检查）
    // 实际应该在Graph级别做拓扑排序检查
    
    // 3. 检查工具可用性
    const unavailableTools = sourceAgent.tools?.filter(tool => 
      !this.isToolAvailable(tool)
    );
    
    if (unavailableTools.length > 0) {
      warnings.push(`${sourceAgent.name} 有 ${unavailableTools.length} 个工具不可用`);
    }
    
    return {
      valid: errors.length === 0,
      errors,
      warnings,
    };
  }
  
  /**
   * 检查类型兼容性
   */
  private static isCompatible(output: string, input: string): boolean {
    const outputKeywords = output.toLowerCase().split(/\s+/);
    const inputKeywords = input.toLowerCase().split(/\s+/);
    
    return outputKeywords.some(keyword => 
      keyword.length > 2 && inputKeywords.some(ik => ik.includes(keyword))
    );
  }
  
  /**
   * 检查工具是否可用
   */
  private static isToolAvailable(tool: string): boolean {
    // 简化版：所有工具都返回可用
    // 实际应该调用后端API检查
    return true;
  }
  
  /**
   * 验证整个工作流
   */
  static validateWorkflow(
    nodes: any[],
    edges: any[]
  ): ValidationStatus {
    const errors: string[] = [];
    const warnings: string[] = [];
    
    // 1. 检查孤立节点
    const connectedNodeIds = new Set<string>();
    edges.forEach(edge => {
      connectedNodeIds.add(edge.source);
      connectedNodeIds.add(edge.target);
    });
    
    nodes.forEach(node => {
      if (!connectedNodeIds.has(node.id)) {
        warnings.push(`${node.data.agentName} 未连接到工作流`);
      }
    });
    
    // 2. 检查循环依赖
    if (this.hasCycle(nodes, edges)) {
      errors.push('检测到循环依赖，请调整节点连接');
    }
    
    // 3. 检查工具可用性
    nodes.forEach(node => {
      if (node.data.toolStatus) {
        Object.entries(node.data.toolStatus).forEach(([tool, status]) => {
          if (status === 'unavailable') {
            warnings.push(`${node.data.agentName} 的工具「${tool}」不可用`);
          }
        });
      }
    });
    
    return {
      isValid: errors.length === 0,
      errors,
      warnings,
    };
  }
  
  /**
   * 检查是否存在循环依赖
   */
  private static hasCycle(nodes: any[], edges: any[]): boolean {
    const adjacencyList: Record<string, string[]> = {};
    nodes.forEach(node => {
      adjacencyList[node.id] = [];
    });
    
    edges.forEach(edge => {
      if (adjacencyList[edge.source]) {
        adjacencyList[edge.source].push(edge.target);
      }
    });
    
    const visited = new Set<string>();
    const recStack = new Set<string>();
    
    const dfs = (nodeId: string): boolean => {
      visited.add(nodeId);
      recStack.add(nodeId);
      
      for (const neighbor of adjacencyList[nodeId] || []) {
        if (!visited.has(neighbor)) {
          if (dfs(neighbor)) return true;
        } else if (recStack.has(neighbor)) {
          return true;
        }
      }
      
      recStack.delete(nodeId);
      return false;
    };
    
    for (const nodeId of Object.keys(adjacencyList)) {
      if (!visited.has(nodeId)) {
        if (dfs(nodeId)) return true;
      }
    }
    
    return false;
  }
}

export interface ValidationStatus {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}
