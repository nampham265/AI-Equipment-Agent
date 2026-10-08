import axios from 'axios'
import type {
  Equipment,
  AvailabilityInfo,
  EquipmentRequest,
  CreateRequestPayload,
  AgentMessagePayload,
  AgentResponse,
  ManagerSummary,
  RequestWithDetails,
  CurrentUser,
  HealthStatus,
  UserAccount,
  DevUser,
} from '../types'

const client = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,  // send session cookie automatically
})


// ── Auth ───────────────────────────────────────────────────────────────────
export async function getMe(): Promise<CurrentUser> {
  const res = await client.get('/me')
  return res.data
}

export async function devLogin(email?: string, name?: string): Promise<CurrentUser> {
  const res = await axios.post('/auth/dev-login', { email, name }, { withCredentials: true })
  return res.data
}

export async function getDevUsers(): Promise<DevUser[]> {
  const res = await axios.get('/auth/dev-users', { withCredentials: true })
  return res.data
}

export async function logout(): Promise<void> {
  await axios.post('/auth/logout', {}, { withCredentials: true })
}

export async function getHealthStatus(): Promise<HealthStatus> {
  const res = await client.get('/health/integrations')
  return res.data
}

// ── Admin (User Management) ────────────────────────────────────────────────
export async function getAdminUsers(): Promise<UserAccount[]> {
  const res = await client.get('/admin/users')
  return res.data
}

export async function createAdminUser(payload: {
  user_email: string
  user_name: string
  role: 'USER' | 'MANAGER'
}): Promise<UserAccount> {
  const res = await client.post('/admin/users', payload)
  return res.data
}

export async function updateUserRole(
  userEmail: string,
  role: 'USER' | 'MANAGER'
): Promise<UserAccount> {
  const res = await client.patch(`/admin/users/${encodeURIComponent(userEmail)}/role`, { role })
  return res.data
}

export async function updateUserActive(
  userEmail: string,
  isActive: boolean
): Promise<UserAccount> {
  const res = await client.patch(`/admin/users/${encodeURIComponent(userEmail)}/active`, {
    is_active: isActive,
  })
  return res.data
}

// ── Equipment ──────────────────────────────────────────────────────────────
export async function searchEquipment(q: string): Promise<Equipment[]> {
  const res = await client.get('/equipment', { params: { q } })
  return res.data
}

export async function getEquipment(equipmentId: string): Promise<Equipment> {
  const res = await client.get(`/equipment/${equipmentId}`)
  return res.data
}

export async function getAvailability(
  equipmentId: string,
  neededFrom: string,
  neededTo: string
): Promise<AvailabilityInfo> {
  const res = await client.get(`/equipment/${equipmentId}/availability`, {
    params: { needed_from: neededFrom, needed_to: neededTo },
  })
  return res.data
}

// ── Agent ──────────────────────────────────────────────────────────────────
export async function sendAgentMessage(payload: AgentMessagePayload): Promise<AgentResponse> {
  const res = await client.post('/agent/message', payload)
  return res.data
}

// ── Requests (user) ────────────────────────────────────────────────────────
export async function createRequest(payload: CreateRequestPayload): Promise<EquipmentRequest> {
  const res = await client.post('/requests', payload)
  return res.data
}

export async function getMyRequests(): Promise<EquipmentRequest[]> {
  const res = await client.get('/requests/mine')
  return res.data
}

export async function cancelRequest(requestId: number): Promise<EquipmentRequest> {
  const res = await client.post(`/requests/${requestId}/cancel`)
  return res.data
}

export async function markReturned(requestId: number): Promise<EquipmentRequest> {
  const res = await client.post(`/requests/${requestId}/mark-returned`)
  return res.data
}

// ── Manager ────────────────────────────────────────────────────────────────
export async function getManagerRequests(status?: string): Promise<RequestWithDetails[]> {
  const res = await client.get('/manager/requests', { params: status ? { status } : {} })
  return res.data
}

export async function getManagerSummary(): Promise<ManagerSummary> {
  const res = await client.get('/manager/summary')
  return res.data
}

export async function approveRequest(requestId: number): Promise<EquipmentRequest> {
  const res = await client.post(`/manager/requests/${requestId}/approve`)
  return res.data
}

export async function rejectRequest(requestId: number, reason?: string): Promise<EquipmentRequest> {
  const res = await client.post(`/manager/requests/${requestId}/reject`, reason ? { reason } : undefined)
  return res.data
}

export async function markBorrowed(requestId: number): Promise<EquipmentRequest> {
  const res = await client.post(`/manager/requests/${requestId}/mark-borrowed`)
  return res.data
}

export async function updateRequestPriority(
  requestId: number,
  finalPriorityLevel: string
): Promise<EquipmentRequest> {
  const res = await client.patch(`/manager/requests/${requestId}/priority`, {
    final_priority_level: finalPriorityLevel,
  })
  return res.data
}

export interface ConflictDetail {
  pair_key?: string
  equipment_id: string
  equipment_name: string

  // Request A
  request_id_a?: string
  id_a?: number
  requester_name_a?: string
  requester_email_a?: string
  project_a?: string
  needed_from_a?: string
  needed_to_a?: string
  status_a?: string

  // Request B
  request_id_b?: string
  id_b?: number
  requester_name_b?: string
  requester_email_b?: string
  project_b?: string
  needed_from_b?: string
  needed_to_b?: string
  status_b?: string

  // Overlap
  overlap_days?: number
  overlap_duration?: string
  overlap_from?: string
  overlap_to?: string

  // Aliases / Compatibility
  request_id: string
  id: number
  requester_name: string
  requester_email: string
  project: string
  needed_from: string
  needed_to: string
  status: string
  conflicting_with_id: string
  conflicting_requester_name: string
  conflicting_project: string
  conflicting_needed_from: string
  conflicting_needed_to: string
  conflicting_status: string
}

export async function getManagerConflicts(): Promise<ConflictDetail[]> {
  const res = await client.get('/manager/conflicts')
  return res.data
}

export interface ReturnReviewItem {
  id: number
  display_id: string
  requester_name: string
  requester_email: string
  equipment_id: string
  equipment_name: string
  project: string
  quantity: number
  needed_from: string
  needed_to: string
  status: string
  return_condition: string
  return_condition_note: string
  returned_at: string
}

export async function getManagerReturnsReview(): Promise<ReturnReviewItem[]> {
  const res = await client.get('/manager/returns-review')
  return res.data
}

// ── Error helpers ──────────────────────────────────────────────────────────
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    if (typeof data === 'object' && data !== null) {
      if (typeof data.detail === 'string') return data.detail
      if (Array.isArray(data.detail)) {
        return data.detail.map((d: { msg?: string }) => d.msg ?? String(d)).join('; ')
      }
    }
    return error.message
  }
  return 'Đã xảy ra lỗi không xác định.'
}
