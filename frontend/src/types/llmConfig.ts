/** LLM 配置相关类型定义 */

export interface RoleConfig {
  role: string;
  display_name: string;
  group: string;
  default_model: string;
  current_model: string;
}

export interface ModelOption {
  name: string;
  display_name: string;
}

export interface LLMConfigResponse {
  roles: Record<string, RoleConfig>;
  available_models: ModelOption[];
}

export interface LLMConfigUpdateResponse {
  roles: Record<string, RoleConfig>;
}
