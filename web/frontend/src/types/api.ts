export type TabId =
  | 'overview'
  | 'chat'
  | 'agents'
  | 'sessions'
  | 'tools'
  | 'skills'
  | 'plugins'
  | 'memory'
  | 'settings'
  | 'config'

export interface ProviderInfo {
  label: string
  has_key: boolean
  is_available: boolean
  is_current: boolean
  base_url?: string
  default_base_url?: string
  current_model?: string
  available_models?: string[]
  key_source?: string
}

export interface SystemStatus {
  model?: { current?: string; model?: string; available?: string[] }
  tools?: { count?: number; names?: string[] }
  skills?: { count?: number }
  sessions?: { latest_id?: string; count?: number }
  agents?: AgentInfo[]
  uptime_seconds?: number
  harness?: { total_cost_usd?: number; session_id?: string }
  tasks?: { total_tasks?: number; by_status?: Record<string, number> }
}

export interface AgentInfo {
  agent_id?: string
  id?: string
  name?: string
  status?: string
  model?: string
  budget?: {
    turns_used?: number
    max_turns?: number
    tokens_used?: number
    max_tokens?: number
  }
}

export interface OrchestratorRun {
  run_id: string
  skill: string
  task: string
  session_id?: string
  status: string
  current_stage?: string | null
  stage_index?: number
  stage_total?: number
  snapshot?: { output?: string } | null
  error?: string | null
  logs?: string[]
  started_at?: string
  finished_at?: string | null
}

export type AgentsSubTab = 'worker' | 'specialist'

export interface SessionInfo {
  session_id?: string
  id?: string
  created_at?: string
  updated_at?: string
  message_count?: number
  session_title?: string
  project_name?: string
}

export interface SessionMemoryEntry {
  session_id?: string
  topic?: string
  summary?: string
  content?: string
  memory_type?: string
  created_at?: string
  updated_at?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  tool_calls?: ToolCallInfo[]
  attachments?: ChatAttachmentRef[]
}

export interface UploadMeta {
  id: string
  filename: string
  path: string
  mime: string
  size: number
  session_id?: string
  url: string
}

export interface ChatAttachmentRef {
  id: string
  filename: string
  mime: string
  url: string
  session_id?: string
}

export interface ToolCallInfo {
  id?: string
  name: string
  arguments?: unknown
  result?: string | null
}

export interface ToolInfo {
  name: string
  description?: string
  category?: string
  read_only?: boolean
  source?: string
  parameters?: Record<string, unknown>
  requires?: string[]
}

export interface SkillInfo {
  name: string
  display_name?: string
  description?: string
  skill_type?: string
  user_invocable?: boolean
  is_hidden?: boolean
  aliases?: string[]
  loaded_from?: string
  version?: string
}

export interface SkillDetail extends SkillInfo {
  when_to_use?: string
  execution_context?: string
  allowed_tools?: string[]
  argument_hint?: string
}

export interface SkillStats {
  total?: number
  total_skills?: number
  total_aliases?: number
  by_type?: Record<string, number>
  by_source?: Record<string, number>
  conditional_skills?: number
  activated_skills?: number
}

export interface PluginInfo {
  name: string
  version?: string
  description?: string
  status?: string
  author?: string
  error_message?: string
}

export interface MemoryEntry {
  id?: string
  text?: string
  metadata?: Record<string, unknown>
  [key: string]: unknown
}

export interface MemorySearchResult {
  text?: string
  score?: number
  metadata?: Record<string, unknown>
  [key: string]: unknown
}

export interface SystemEvent {
  event_type: string
  data: unknown
  timestamp?: string
}

export interface WsChatMessage {
  type: string
  session_id?: string
  delta?: string
  tool_call?: { id?: string; name?: string; arguments?: unknown }
  tool_call_id?: string
  content?: string
  error?: string
}

export type ToastLevel = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  level: ToastLevel
  message: string
}
