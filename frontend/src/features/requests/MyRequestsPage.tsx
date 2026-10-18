import { useState, useEffect, useCallback } from 'react'
import type { EquipmentRequest, RequestStatus } from '../../types'
import { getMyRequests, cancelRequest, markReturned, extractErrorMessage } from '../../lib/api'
import { StatusBadge } from '../../components/StatusBadge'

const STATUS_FILTER_OPTIONS: { label: string; value: string }[] = [
  { label: 'Tất cả', value: '' },
  { label: 'Chờ duyệt', value: 'Pending' },
  { label: 'Đã duyệt', value: 'Approved' },
  { label: 'Đang mượn', value: 'Borrowed' },
  { label: 'Đã trả', value: 'Returned' },
  { label: 'Đã từ chối', value: 'Rejected' },
  { label: 'Đã hủy', value: 'Cancelled' },
]

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('vi-VN')
}

export function MyRequestsPage() {
  const [requests, setRequests] = useState<EquipmentRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [confirmAction, setConfirmAction] = useState<{
    requestId: number
    action: 'cancel' | 'return'
    displayId: string
  } | null>(null)

  const loadRequests = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getMyRequests()
      setRequests(data)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRequests()
  }, [loadRequests])

  const filtered = statusFilter
    ? requests.filter((r) => r.status === (statusFilter as RequestStatus))
    : requests

  const handleCancel = async (requestId: number) => {
    setActionLoading(requestId)
    setActionError(null)
    try {
      const updated = await cancelRequest(requestId)
      setRequests((prev) => prev.map((r) => (r.id === requestId ? updated : r)))
    } catch (err) {
      setActionError(extractErrorMessage(err))
    } finally {
      setActionLoading(null)
      setConfirmAction(null)
    }
  }

  const handleReturn = async (requestId: number) => {
    setActionLoading(requestId)
    setActionError(null)
    try {
      const updated = await markReturned(requestId)
      setRequests((prev) => prev.map((r) => (r.id === requestId ? updated : r)))
    } catch (err) {
      setActionError(extractErrorMessage(err))
    } finally {
      setActionLoading(null)
      setConfirmAction(null)
    }
  }

  const executeConfirmedAction = () => {
    if (!confirmAction) return
    if (confirmAction.action === 'cancel') handleCancel(confirmAction.requestId)
    else handleReturn(confirmAction.requestId)
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Yêu cầu mượn của tôi</h1>
          <p className="page-subtitle">Theo dõi trạng thái xét duyệt và tiến độ mượn trả thiết bị của bạn</p>
        </div>
        <button className="btn btn--outline btn--sm" onClick={loadRequests} title="Làm mới dữ liệu">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          <span>Làm mới</span>
        </button>
      </div>

      {actionError && (
        <div className="alert alert--error" role="alert">
          {actionError}
        </div>
      )}

      {/* Confirmation dialog */}
      {confirmAction && (
        <div className="alert alert--warning" role="dialog" aria-modal="true">
          <p style={{ marginBottom: '0.5rem' }}>
            {confirmAction.action === 'cancel'
              ? `Bạn chắc chắn muốn hủy yêu cầu ${confirmAction.displayId}?`
              : `Bạn xác nhận đã hoàn trả thiết bị của yêu cầu ${confirmAction.displayId}?`}
          </p>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn--danger btn--sm"
              onClick={executeConfirmedAction}
              disabled={actionLoading !== null}
            >
              {actionLoading !== null ? <span className="spinner" /> : null}
              Xác nhận
            </button>
            <button
              className="btn btn--outline btn--sm"
              onClick={() => setConfirmAction(null)}
              disabled={actionLoading !== null}
            >
              Hủy bỏ
            </button>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div className="filter-tabs" role="tablist" aria-label="Lọc theo trạng thái">
        {STATUS_FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            role="tab"
            aria-selected={statusFilter === opt.value}
            className={`filter-tab${statusFilter === opt.value ? ' filter-tab--active' : ''}`}
            onClick={() => setStatusFilter(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading">Đang tải...</div>
      ) : error ? (
        <div className="alert alert--error">{error}</div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">Không có yêu cầu nào.</p>
          <p className="text-muted">
            Hãy vào trang Trò chuyện để gửi yêu cầu mượn thiết bị.
          </p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Mã yêu cầu</th>
                <th>Thiết bị</th>
                <th>Dự án</th>
                <th>Số lượng</th>
                <th>Ngày mượn</th>
                <th>Ngày trả</th>
                <th>Trạng thái</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((req) => (
                <tr key={req.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 600 }}>
                    {req.display_id}
                  </td>
                  <td>
                    <div style={{ fontWeight: 600, fontSize: '1rem' }}>{req.equipment_name ?? req.equipment_id}</div>
                    <div className="text-muted" style={{ fontSize: '0.875rem' }}>
                      {req.equipment_id}
                    </div>
                  </td>
                  <td>{req.project}</td>
                  <td>{req.quantity}</td>
                  <td>{formatDate(req.needed_from)}</td>
                  <td>{formatDate(req.needed_to)}</td>
                  <td>
                    <StatusBadge status={req.status} />
                    {req.rejection_reason && (
                      <div
                        style={{
                          fontSize: '0.8rem',
                          color: 'var(--color-danger, #d9383a)',
                          marginTop: '0.25rem',
                          maxWidth: '220px',
                          lineHeight: '1.3',
                        }}
                        title={req.rejection_reason}
                      >
                        Lý do: {req.rejection_reason}
                      </div>
                    )}
                  </td>
                  <td>
                    <div className="action-buttons">
                      {req.status === 'Pending' && (
                        <button
                          className="btn btn--outline btn--sm"
                          onClick={() =>
                            setConfirmAction({
                              requestId: req.id,
                              action: 'cancel',
                              displayId: req.display_id,
                            })
                          }
                          disabled={actionLoading === req.id}
                        >
                          Hủy
                        </button>
                      )}
                      {req.status === 'Borrowed' && (
                        <button
                          className="btn btn--outline btn--sm"
                          onClick={() =>
                            setConfirmAction({
                              requestId: req.id,
                              action: 'return',
                              displayId: req.display_id,
                            })
                          }
                          disabled={actionLoading === req.id}
                        >
                          Xác nhận trả
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
