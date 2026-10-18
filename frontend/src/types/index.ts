// ── Equipment ──────────────────────────────────────────────────────────────
export interface Equipment {
  equipment_id: string
  equipment_name: string
  category: string | null
  description: string | null
  quantity_total: number
  unit: string | null
  location: string | null
}

export interface AvailabilityInfo {
  equipment_id: string
  needed_from: string
  needed_to: string
  quantity_total: number
  committed_quantity: number
  available_quantity: number
  competing_pending_requests: CompetingRequest[]
}

export interface CompetingRequest {
  id: number
  requester_name: string
  quantity: number
  needed_from: string
  needed_to: string
  project: string
}

// ── Requests ───────────────────────────────────────────────────────────────
export type PriorityLevel = 'Critical' | 'High' | 'Medium' | 'Low' | 'Needs review'
export type RequestStatus =
  | 'Pending'
  | 'Approved'
  | 'Rejected'
  | 'Borrowed'
  | 'Returned'
  | 'Cancelled'

export interface EquipmentRequest {
  id: number
  display_id: string
  requester_name: string
  requester_email: string | null
  project: string
  equipment_id: string
  equipment_name?: string
  quantity: number
  needed_from: string
  needed_to: string
  purpose: string
  priority_level: PriorityLevel
  priority_reason: string
  final_priority_level?: PriorityLevel | null
  priority_reviewed_by?: string | null
  priority_reviewed_at?: string | null
  status: RequestStatus
  return_condition?: string | null
  return_condition_note?: string | null
  returned_at?: string | null
  created_at: string
  modified_at: string
  rejection_reason?: string | null
}

export type RequestRead = EquipmentRequest

export interface CreateRequestPayload {
  project: string
  equipment_id: string
  quantity: number
  needed_from: string
  needed_to: string
  purpose: string
}

// ── Agent ──────────────────────────────────────────────────────────────────
export interface BorrowFormPrefill {
  equipment_id?: string
  equipment_name?: string
  project?: string
  quantity?: number
  needed_from?: string
  needed_to?: string
  purpose?: string
}

export interface ReturnFormPrefillData {
  request_id: number
  display_id: string
  equipment_id: string
  equipment_name: string
  project: string
  quantity: number
  needed_from?: string
  needed_to?: string
}

export type AgentAction =
  | { type: 'show_borrow_form'; prefill: BorrowFormPrefill }
  | { type: 'show_return_form'; prefill: ReturnFormPrefillData }
  | { type: 'show_my_requests' }
  | { type: 'show_equipment_list'; query?: string }

export interface AgentMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface AgentMessagePayload {
  message: string
  conversation_history: AgentMessage[]
  conversation_id?: string
}

export interface AgentResponse {
  reply: string
  action?: AgentAction
  equipment_results?: Equipment[]
}

// ── Manager ────────────────────────────────────────────────────────────────
export interface ManagerSummary {
  pending_count: number
  approved_count: number
  borrowed_count: number
  conflicts_count: number
}

export interface RequestWithDetails extends EquipmentRequest {
  competing_approved_borrowed: CompetingRequest[]
  competing_pending: CompetingRequest[]
}

// ── Auth & Users ───────────────────────────────────────────────────────────
export type Role = 'USER' | 'MANAGER' | 'ADMIN'

export interface CurrentUser {
  email: string
  name: string
  role: Role
  is_manager: boolean
  is_admin: boolean
}

export interface UserAccount {
  user_email: string
  user_name: string
  role: Role
  is_active: boolean
}

export interface DevUser {
  email: string
  name: string
  role: Role
  is_active: boolean
}

export interface IntegrationStatus {
  status: 'connected' | 'not_configured' | 'error' | 'configured'
  message?: string
  model?: string
}

export interface HealthStatus {
  excel?: IntegrationStatus & {
    path?: string
    detail?: string
  }
  gemini: IntegrationStatus
  microsoft_graph: IntegrationStatus & {
    site?: string
    equipment_list?: string
    requests_list?: string
  }
  email: IntegrationStatus
}
