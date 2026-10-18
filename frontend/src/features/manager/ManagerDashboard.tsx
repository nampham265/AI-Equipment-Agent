import { useState, useEffect, useCallback } from 'react'
import type { RequestWithDetails, ManagerSummary, RequestStatus } from '../../types'
import {
  getManagerRequests,
  getManagerSummary,
  getManagerConflicts,
  getManagerReturnsReview,
  approveRequest,
  rejectRequest,
  markBorrowed,
  updateRequestPriority,
  extractErrorMessage,
} from '../../lib/api'
import type { ConflictDetail, ReturnReviewItem } from '../../lib/api'
import { StatusBadge } from '../../components/StatusBadge'
import { PriorityBadge } from '../../components/PriorityBadge'
import { useAuth } from '../../app/AuthContext'

const STATUS_FILTER_OPTIONS: { label: string; value: string }[] = [
  { label: 'Chờ duyệt', value: 'Pending' },
  { label: 'Đã duyệt', value: 'Approved' },
  { label: 'Đang mượn', value: 'Borrowed' },
  { label: 'Tất cả', value: '' },
]

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('vi-VN')
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('vi-VN', {
    dateStyle: 'short',
    timeStyle: 'short',
  })
}

interface ConfirmModalState {
  request: RequestWithDetails
  action: 'approve' | 'reject' | 'borrow'
}

export function ManagerDashboard() {
  const { user } = useAuth()
  const [summary, setSummary] = useState<ManagerSummary | null>(null)
  const [requests, setRequests] = useState<RequestWithDetails[]>([])
  const [conflictsList, setConflictsList] = useState<ConflictDetail[]>([])
  const [returnsReviewList, setReturnsReviewList] = useState<ReturnReviewItem[]>([])
  const [showConflictsModal, setShowConflictsModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('Pending')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [priorityInputs, setPriorityInputs] = useState<Record<number, string>>({})
  const [savingPriorityId, setSavingPriorityId] = useState<number | null>(null)
  const [confirmModal, setConfirmModal] = useState<ConfirmModalState | null>(null)
  const [rejectReason, setRejectReason] = useState<string>('')
  const [modalError, setModalError] = useState<string | null>(null)
  const [successFeedback, setSuccessFeedback] = useState<{ requestId: number; message: string } | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sum, reqs, conflicts, returnsRev] = await Promise.all([
        getManagerSummary(),
        getManagerRequests(statusFilter || undefined),
        getManagerConflicts().catch(() => [] as ConflictDetail[]),
        getManagerReturnsReview().catch(() => [] as ReturnReviewItem[]),
      ])
      setSummary(sum)
      setRequests(reqs)
      setConflictsList(conflicts)
      setReturnsReviewList(returnsRev)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    loadData()
  }, [loadData])

  const executeAction = async () => {
    if (!confirmModal) return
    const { request, action } = confirmModal
    setActionLoading(request.id)
    setModalError(null)

    try {
      let updated: Awaited<ReturnType<typeof approveRequest>>
      if (action === 'approve') {
        updated = await approveRequest(request.id)
      } else if (action === 'reject') {
        updated = await rejectRequest(request.id, rejectReason.trim() || undefined)
      } else {
        updated = await markBorrowed(request.id)
      }

      setRequests((prev) =>
        prev.map((r) =>
          r.id === request.id ? { ...r, ...updated } : r
        )
      )

      const actionName = action === 'approve' ? 'duyệt' : action === 'reject' ? 'từ chối' : 'bàn giao thiết bị cho'
      setSuccessFeedback({
        requestId: request.id,
        message: `Đã ${actionName} yêu cầu ${request.display_id} thành công`,
      })
      setTimeout(() => {
        setSuccessFeedback((prev) => (prev?.requestId === request.id ? null : prev))
      }, 5000)

      setConfirmModal(null)
      setRejectReason('')
      // Reload summary
      getManagerSummary().then(setSummary).catch(() => {})
    } catch (err) {
      setModalError(extractErrorMessage(err))
    } finally {
      setActionLoading(null)
    }
  }

  const handleSavePriority = async (requestId: number) => {
    const chosen = priorityInputs[requestId]
    if (!chosen) return
    setSavingPriorityId(requestId)
    setActionError(null)
    try {
      const updated = await updateRequestPriority(requestId, chosen)
      setRequests((prev) =>
        prev.map((r) => (r.id === requestId ? { ...r, ...updated } : r))
      )
    } catch (err) {
      setActionError(extractErrorMessage(err))
    } finally {
      setSavingPriorityId(null)
    }
  }

  const visibleRequests =
    statusFilter
      ? requests.filter((r) => r.status === (statusFilter as RequestStatus))
      : requests

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Điều hành & Phê duyệt Thiết bị</h1>
          <p className="page-subtitle">Tổng quan yêu cầu mượn, cảnh báo xung đột lịch và phê duyệt ưu tiên</p>
        </div>
        <button className="btn btn--outline btn--sm" onClick={loadData} title="Làm mới dữ liệu">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          <span>Làm mới</span>
        </button>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="summary-cards">
          <div className="summary-card">
            <div className="summary-card__count">{summary.pending_count}</div>
            <div className="summary-card__label">Chờ duyệt</div>
          </div>
          <div className="summary-card">
            <div className="summary-card__count">{summary.approved_count}</div>
            <div className="summary-card__label">Đã duyệt</div>
          </div>
          <div className="summary-card">
            <div className="summary-card__count">{summary.borrowed_count}</div>
            <div className="summary-card__label">Đang mượn</div>
          </div>
          <div
            className="summary-card"
            style={{ cursor: 'pointer', transition: 'transform 0.15s ease' }}
            onClick={() => setShowConflictsModal(true)}
            title="Nhấn để xem chi tiết danh sách xung đột lịch"
          >
            <div className="summary-card__count" style={{ color: summary.conflicts_count > 0 ? 'var(--color-danger)' : undefined }}>
              {summary.conflicts_count}
            </div>
            <div className="summary-card__label">Cặp xung đột lịch</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--color-primary, #0284c7)', marginTop: '0.35rem', fontWeight: 600 }}>
              Xem chi tiết →
            </div>
          </div>
        </div>
      )}

      {/* Cần kiểm tra tình trạng thiết bị (Returns needing attention) */}
      {returnsReviewList.length > 0 && (
        <div
          className="card"
          style={{
            borderLeft: '4px solid #f59e0b',
            marginBottom: '1.5rem',
            padding: '1.1rem 1.25rem',
            background: 'var(--color-bg-surface, #ffffff)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.85rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '1.15rem' }}>⚠️</span>
              <h2 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700 }}>
                Cần kiểm tra tình trạng thiết bị ({returnsReviewList.length})
              </h2>
            </div>
            <span className="badge badge--warning" style={{ fontSize: '0.8rem', padding: '0.2rem 0.6rem' }}>
              Cần quản lý xem xét
            </span>
          </div>

          <div className="table-wrapper" style={{ overflowX: 'auto' }}>
            <table style={{ fontSize: '0.9rem', marginBottom: 0 }}>
              <thead>
                <tr>
                  <th>Mã YC</th>
                  <th>Người trả</th>
                  <th>Thiết bị</th>
                  <th>Dự án</th>
                  <th>Ngày trả</th>
                  <th>Tình trạng</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {returnsReviewList.map((item) => (
                  <tr key={item.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{item.display_id}</td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{item.requester_name}</div>
                      {item.requester_email && (
                        <div className="text-muted" style={{ fontSize: '0.8rem' }}>{item.requester_email}</div>
                      )}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{item.equipment_name}</div>
                      <div className="text-muted" style={{ fontSize: '0.8rem' }}>
                        {item.equipment_id} ({item.quantity} cái)
                      </div>
                    </td>
                    <td>{item.project}</td>
                    <td>{item.returned_at ? formatDateTime(item.returned_at) : '—'}</td>
                    <td>
                      <span className="badge badge--warning" style={{ fontWeight: 600 }}>
                        {item.return_condition}
                      </span>
                    </td>
                    <td style={{ maxWidth: 260, color: item.return_condition_note ? 'inherit' : 'var(--color-text-muted)' }}>
                      {item.return_condition_note || 'Không có ghi chú'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {actionError && (
        <div className="alert alert--error" role="alert">
          {actionError}
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
      ) : visibleRequests.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">Không có yêu cầu nào phù hợp.</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Mã YC</th>
                <th>Người gửi</th>
                <th>Thiết bị</th>
                <th>Dự án</th>
                <th>SL</th>
                <th>Ngày mượn</th>
                <th>Ngày trả</th>
                <th>Ưu tiên</th>
                <th>Trạng thái</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {visibleRequests.map((req) => (
                <>
                  <tr
                    key={req.id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setExpandedId(expandedId === req.id ? null : req.id)}
                  >
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 600 }}>
                      {req.display_id}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600, fontSize: '1rem' }}>{req.requester_name}</div>
                      {req.requester_email && (
                        <div className="text-muted" style={{ fontSize: '0.875rem' }}>
                          {req.requester_email}
                        </div>
                      )}
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
                      {req.final_priority_level ? (
                        <div>
                          <PriorityBadge level={req.final_priority_level} />
                          <div style={{ fontSize: '0.75rem', color: 'var(--color-primary, #0284c7)', marginTop: '2px', fontWeight: 600 }}>Quản lý duyệt</div>
                        </div>
                      ) : (
                        <div>
                          <PriorityBadge level={req.priority_level} />
                          <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '2px' }}>AI đề xuất</div>
                        </div>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={req.status} />
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {(() => {
                        const isOwn = !!(req.requester_email && user?.email && req.requester_email.toLowerCase() === user.email.toLowerCase())
                        return (
                          <div>
                            <div className="action-buttons">
                              {req.status === 'Pending' && (
                                <>
                                  <button
                                    className="btn btn--primary btn--sm"
                                    disabled={actionLoading === req.id || isOwn}
                                    title={isOwn ? 'Bạn không thể tự duyệt yêu cầu của chính mình' : undefined}
                                    onClick={() => {
                                      setModalError(null)
                                      setRejectReason('')
                                      setConfirmModal({ request: req, action: 'approve' })
                                    }}
                                  >
                                    Duyệt
                                  </button>
                                  <button
                                    className="btn btn--danger btn--sm"
                                    disabled={actionLoading === req.id || isOwn}
                                    title={isOwn ? 'Bạn không thể tự từ chối yêu cầu của chính mình' : undefined}
                                    onClick={() => {
                                      setModalError(null)
                                      setRejectReason('')
                                      setConfirmModal({ request: req, action: 'reject' })
                                    }}
                                  >
                                    Từ chối
                                  </button>
                                </>
                              )}
                              {req.status === 'Approved' && (
                                <button
                                  className="btn btn--outline btn--sm"
                                  disabled={actionLoading === req.id || isOwn}
                                  title={isOwn ? 'Bạn không thể tự bàn giao thiết bị cho yêu cầu của chính mình' : undefined}
                                  onClick={() => {
                                    setModalError(null)
                                    setRejectReason('')
                                    setConfirmModal({ request: req, action: 'borrow' })
                                  }}
                                >
                                  Bàn giao
                                </button>
                              )}
                              {isOwn && (
                                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                                  (Yêu cầu của bạn)
                                </span>
                              )}
                            </div>
                            {successFeedback?.requestId === req.id && (
                              <div className="in-context-success" role="status">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="20 6 9 17 4 12" />
                                </svg>
                                <span>{successFeedback.message}</span>
                              </div>
                            )}
                          </div>
                        )
                      })()}
                    </td>
                  </tr>

                  {/* Expanded row */}
                  {expandedId === req.id && (
                    <tr key={`${req.id}-detail`}>
                      <td colSpan={10} style={{ padding: 0 }}>
                        <div className="expand-panel">
                          <div className="expand-panel__section">
                            <div className="expand-panel__label">Mục đích</div>
                            <div className="expand-panel__value">{req.purpose}</div>
                          </div>

                          <div className="expand-panel__section">
                            <div className="expand-panel__label">Ưu tiên AI đề xuất</div>
                            <div className="expand-panel__value">
                              <PriorityBadge level={req.priority_level} />
                              <p style={{ marginTop: '0.4rem', fontSize: '0.95rem', lineHeight: '1.6' }}>
                                {req.priority_reason}
                              </p>
                            </div>
                          </div>

                          <div className="expand-panel__section">
                            <div className="expand-panel__label">Mức ưu tiên chính thức (Quản lý duyệt)</div>
                            <div className="expand-panel__value">
                              {req.final_priority_level ? (
                                <div style={{ marginBottom: '0.6rem' }}>
                                  <PriorityBadge level={req.final_priority_level} />
                                  <span style={{ marginLeft: '0.5rem', fontSize: '0.9rem', color: 'var(--color-text-secondary)' }}>
                                    Xác nhận bởi {req.priority_reviewed_by || 'Quản lý'} {req.priority_reviewed_at ? `(${formatDateTime(req.priority_reviewed_at)})` : ''}
                                  </span>
                                </div>
                              ) : (
                                <p style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                                  Chưa có đánh giá chính thức từ Quản lý (đang dùng đề xuất AI: <strong>{req.priority_level}</strong>).
                                </p>
                              )}

                              {(() => {
                                const isOwn = !!(req.requester_email && user?.email && req.requester_email.toLowerCase() === user.email.toLowerCase())
                                return (
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.4rem' }}>
                                    <select
                                      className="form-control"
                                      style={{ width: 'auto', padding: '0.35rem 0.6rem', fontSize: '0.9rem' }}
                                      value={priorityInputs[req.id] ?? req.final_priority_level ?? req.priority_level}
                                      onChange={(e) => setPriorityInputs((prev) => ({ ...prev, [req.id]: e.target.value }))}
                                      disabled={isOwn}
                                    >
                                      <option value="Critical">Critical (Khẩn cấp)</option>
                                      <option value="High">High (Cao)</option>
                                      <option value="Medium">Medium (Trung bình)</option>
                                      <option value="Low">Low (Thấp)</option>
                                      <option value="Needs review">Needs review (Cần xem xét)</option>
                                    </select>
                                    <button
                                      className="btn btn--outline btn--sm"
                                      disabled={savingPriorityId === req.id || isOwn}
                                      title={isOwn ? 'Người gửi không thể tự điều chỉnh mức ưu tiên của chính mình' : undefined}
                                      onClick={() => handleSavePriority(req.id)}
                                    >
                                      {savingPriorityId === req.id ? 'Đang lưu...' : 'Lưu mức ưu tiên'}
                                    </button>
                                    {isOwn && (
                                      <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                                        (Không thể tự sửa trên yêu cầu của bạn)
                                      </span>
                                    )}
                                  </div>
                                )
                              })()}
                            </div>
                          </div>

                          {req.competing_approved_borrowed?.length > 0 && (
                            <div className="expand-panel__section">
                              <div className="expand-panel__label">
                                Xung đột (đã xác nhận: Approved/Borrowed)
                              </div>
                              {req.competing_approved_borrowed.map((c) => (
                                <div key={c.id} className="conflict-warning" style={{ fontSize: '0.9rem', padding: '0.6rem 0.85rem' }}>
                                  {c.requester_name} — {c.project} — {c.quantity} đơn vị —{' '}
                                  {formatDate(c.needed_from)} đến {formatDate(c.needed_to)}
                                </div>
                              ))}
                            </div>
                          )}

                          {req.competing_pending?.length > 0 && (
                            <div className="expand-panel__section">
                              <div className="expand-panel__label">
                                Đang chờ xem xét (Pending)
                              </div>
                              {req.competing_pending.map((c) => (
                                <div
                                  key={c.id}
                                  style={{
                                    fontSize: '0.9rem',
                                    color: 'var(--color-text-secondary)',
                                    marginBottom: '0.35rem',
                                  }}
                                >
                                  {c.requester_name} — {c.project} — {c.quantity} đơn vị —{' '}
                                  {formatDate(c.needed_from)} đến {formatDate(c.needed_to)}
                                </div>
                              ))}
                            </div>
                          )}

                          {req.rejection_reason && (
                            <div className="expand-panel__section" style={{ borderLeft: '3px solid var(--color-danger, #ef4444)', paddingLeft: '0.75rem' }}>
                              <div className="expand-panel__label" style={{ color: 'var(--color-danger, #ef4444)' }}>
                                Lý do từ chối từ Quản lý
                              </div>
                              <div className="expand-panel__value" style={{ color: 'var(--color-text, #1f2937)', fontWeight: 500 }}>
                                {req.rejection_reason}
                              </div>
                            </div>
                          )}

                          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginTop: '0.75rem' }}>
                            Gửi lúc: {formatDateTime(req.created_at)} · Cập nhật: {formatDateTime(req.modified_at)}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* In-Context Confirm Modal */}
      {confirmModal && (
        <div
          className="modal-backdrop"
          onClick={() => actionLoading === null && setConfirmModal(null)}
          role="presentation"
        >
          <div
            className="modal-dialog"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-modal-title"
          >
            <div className="modal-header">
              <h3 id="confirm-modal-title" className="modal-title">
                {confirmModal.action === 'approve' && 'Xác nhận duyệt yêu cầu'}
                {confirmModal.action === 'reject' && 'Xác nhận từ chối yêu cầu'}
                {confirmModal.action === 'borrow' && 'Xác nhận bàn giao thiết bị'}
              </h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setConfirmModal(null)}
                disabled={actionLoading !== null}
                aria-label="Đóng"
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              <div className="modal-summary-grid">
                <span className="modal-summary-label">Mã yêu cầu:</span>
                <span className="modal-summary-val" style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                  {confirmModal.request.display_id}
                </span>

                <span className="modal-summary-label">Người gửi:</span>
                <span className="modal-summary-val">
                  <strong>{confirmModal.request.requester_name}</strong>
                  {confirmModal.request.requester_email && (
                    <span className="text-muted" style={{ marginLeft: '0.4rem', fontSize: '0.85rem' }}>
                      ({confirmModal.request.requester_email})
                    </span>
                  )}
                </span>

                <span className="modal-summary-label">Thiết bị:</span>
                <span className="modal-summary-val">
                  <strong>{confirmModal.request.equipment_name ?? confirmModal.request.equipment_id}</strong>
                  <span className="text-muted" style={{ marginLeft: '0.4rem', fontSize: '0.85rem' }}>
                    [{confirmModal.request.equipment_id}]
                  </span>
                </span>

                <span className="modal-summary-label">Số lượng:</span>
                <span className="modal-summary-val">{confirmModal.request.quantity}</span>

                <span className="modal-summary-label">Dự án:</span>
                <span className="modal-summary-val">{confirmModal.request.project}</span>

                <span className="modal-summary-label">Thời gian:</span>
                <span className="modal-summary-val">
                  {formatDate(confirmModal.request.needed_from)} → {formatDate(confirmModal.request.needed_to)}
                </span>

                <span className="modal-summary-label">Mục đích:</span>
                <span className="modal-summary-val">{confirmModal.request.purpose}</span>

                <span className="modal-summary-label">Ưu tiên:</span>
                <span className="modal-summary-val">
                  <PriorityBadge level={confirmModal.request.final_priority_level ?? confirmModal.request.priority_level} />
                  {confirmModal.request.final_priority_level ? ' (Quản lý duyệt)' : ' (AI đề xuất)'}
                </span>
              </div>

              {confirmModal.request.competing_approved_borrowed?.length > 0 && (
                <div className="alert alert--warning" style={{ marginTop: '1rem', fontSize: '0.9rem' }}>
                  <strong>Cảnh báo xung đột:</strong> Thiết bị này đã có {confirmModal.request.competing_approved_borrowed.length} lịch mượn trùng thời gian được duyệt/đang mượn!
                </div>
              )}

              {confirmModal.action === 'reject' && (
                <div style={{ marginTop: '1rem' }}>
                  <label htmlFor="modal-reject-reason" className="form-label" style={{ fontWeight: 600, fontSize: '0.92rem' }}>
                    Lý do từ chối (tùy chọn):
                  </label>
                  <textarea
                    id="modal-reject-reason"
                    className="form-control"
                    rows={2}
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Nhập lý do từ chối yêu cầu nếu có..."
                    disabled={actionLoading !== null}
                  />
                </div>
              )}

              {modalError && (
                <div className="alert alert--error" role="alert" style={{ marginTop: '1rem' }}>
                  {modalError}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn--outline btn--sm"
                onClick={() => setConfirmModal(null)}
                disabled={actionLoading !== null}
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                className={`btn btn--sm ${confirmModal.action === 'reject' ? 'btn--danger' : 'btn--primary'}`}
                onClick={executeAction}
                disabled={actionLoading !== null}
              >
                {actionLoading !== null ? <span className="spinner" style={{ marginRight: '0.4rem', width: '14px', height: '14px' }} /> : null}
                {confirmModal.action === 'approve' && 'Xác nhận duyệt'}
                {confirmModal.action === 'reject' && 'Xác nhận từ chối'}
                {confirmModal.action === 'borrow' && 'Xác nhận bàn giao'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Conflicts Detail Modal */}
      {showConflictsModal && (
        <div
          className="modal-backdrop"
          onClick={() => setShowConflictsModal(false)}
          role="presentation"
        >
          <div
            className="modal-dialog"
            style={{ maxWidth: 840, width: '90%' }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="conflicts-modal-title"
          >
            <div className="modal-header">
              <h3 id="conflicts-modal-title" className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span>⚠️ Chi tiết các cặp xung đột lịch mượn</span>
                <span className="badge badge--danger" style={{ fontSize: '0.8rem' }}>
                  {conflictsList.length} cặp xung đột
                </span>
              </h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowConflictsModal(false)}
                aria-label="Đóng"
              >
                &times;
              </button>
            </div>

            <div className="modal-body" style={{ maxHeight: '65vh', overflowY: 'auto' }}>
              {conflictsList.length === 0 ? (
                <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                  <p className="empty-state__title">Hiện tại không có xung đột lịch nào được ghi nhận.</p>
                </div>
              ) : (
                <div className="table-wrapper">
                  <table style={{ fontSize: '0.88rem' }}>
                    <thead>
                      <tr>
                        <th>Thiết bị</th>
                        <th>Khoảng thời gian trùng lặp</th>
                        <th>Đơn yêu cầu A</th>
                        <th>Đơn yêu cầu B</th>
                      </tr>
                    </thead>
                    <tbody>
                      {conflictsList.map((c, idx) => {
                        const reqIdA = c.request_id_a || c.request_id
                        const reqIdB = c.request_id_b || c.conflicting_with_id
                        const nameA = c.requester_name_a || c.requester_name
                        const nameB = c.requester_name_b || c.conflicting_requester_name
                        const projA = c.project_a || c.project
                        const projB = c.project_b || c.conflicting_project
                        const statusA = c.status_a || c.status
                        const statusB = c.status_b || c.conflicting_status
                        const fromA = c.needed_from_a || c.needed_from
                        const toA = c.needed_to_a || c.needed_to
                        const fromB = c.needed_from_b || c.conflicting_needed_from
                        const toB = c.needed_to_b || c.conflicting_needed_to
                        const overlapStr = c.overlap_duration || `${formatDate(fromB)} - ${formatDate(toA)}`

                        return (
                          <tr key={c.pair_key || `${c.id}-${c.conflicting_with_id}-${idx}`}>
                            <td style={{ verticalAlign: 'top', minWidth: 160 }}>
                              <div style={{ fontWeight: 600 }}>{c.equipment_name}</div>
                              <div className="text-muted" style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>
                                {c.equipment_id}
                              </div>
                            </td>
                            <td style={{ verticalAlign: 'top', minWidth: 150 }}>
                              <span className="badge badge--danger" style={{ fontWeight: 600, fontSize: '0.8rem' }}>
                                {overlapStr}
                              </span>
                            </td>
                            <td style={{ verticalAlign: 'top', minWidth: 190, background: 'var(--color-bg-secondary, #f8fafc)' }}>
                              <div>
                                <strong style={{ fontFamily: 'var(--font-mono)' }}>{reqIdA}</strong>
                                <span style={{ marginLeft: '0.4rem' }}>
                                  <StatusBadge status={statusA as any} />
                                </span>
                              </div>
                              <div style={{ fontWeight: 600, marginTop: '0.25rem' }}>{nameA}</div>
                              <div className="text-muted" style={{ fontSize: '0.8rem' }}>Dự án: {projA}</div>
                              <div style={{ fontSize: '0.8rem', marginTop: '0.2rem', color: 'var(--color-text-secondary)' }}>
                                📅 {formatDate(fromA)} → {formatDate(toA)}
                              </div>
                            </td>
                            <td style={{ verticalAlign: 'top', minWidth: 190, background: 'var(--color-bg-secondary, #f8fafc)' }}>
                              <div>
                                <strong style={{ fontFamily: 'var(--font-mono)' }}>{reqIdB}</strong>
                                <span style={{ marginLeft: '0.4rem' }}>
                                  <StatusBadge status={statusB as any} />
                                </span>
                              </div>
                              <div style={{ fontWeight: 600, marginTop: '0.25rem' }}>{nameB}</div>
                              <div className="text-muted" style={{ fontSize: '0.8rem' }}>Dự án: {projB}</div>
                              <div style={{ fontSize: '0.8rem', marginTop: '0.2rem', color: 'var(--color-text-secondary)' }}>
                                📅 {formatDate(fromB)} → {formatDate(toB)}
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn--primary btn--sm"
                onClick={() => setShowConflictsModal(false)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
