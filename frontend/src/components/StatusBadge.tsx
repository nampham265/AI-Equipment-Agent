import type { RequestStatus } from '../types'

const STATUS_LABELS: Record<RequestStatus, string> = {
  Pending: 'Chờ duyệt',
  Approved: 'Đã duyệt',
  Rejected: 'Đã từ chối',
  Borrowed: 'Đang mượn',
  Returned: 'Đã trả',
  Cancelled: 'Đã hủy',
}

interface StatusBadgeProps {
  status: RequestStatus
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-badge__dot" />
      <span>{STATUS_LABELS[status] ?? status}</span>
    </span>
  )
}
