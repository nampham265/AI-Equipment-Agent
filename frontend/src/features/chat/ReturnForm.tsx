import { useState, useEffect } from 'react'
import type { RequestRead } from '../../types'
import { extractErrorMessage } from '../../lib/api'

export interface ReturnFormPrefill {
  request_id: number
  display_id: string
  equipment_id: string
  equipment_name: string
  project: string
  quantity: number
  max_quantity?: number
  return_condition?: string
  return_condition_note?: string
  needed_from?: string
  needed_to?: string
}

interface Props {
  prefill: ReturnFormPrefill
  onSubmitted: (returned: RequestRead) => void
  onCancel: () => void
}

const RETURN_CONDITIONS = [
  'Nguyên trạng như khi nhận',
  'Có hao mòn nhẹ, vẫn sử dụng bình thường',
  'Hư hỏng nhẹ',
  'Hư hỏng nặng',
  'Hư hỏng nhưng đã khắc phục',
  'Cần kiểm tra thêm',
] as const

const ATTENTION_CONDITIONS = new Set(['Hư hỏng nhẹ', 'Hư hỏng nặng', 'Cần kiểm tra thêm'])

export function ReturnForm({ prefill, onSubmitted, onCancel }: Props) {
  const maxQty = prefill.max_quantity || prefill.quantity || 1
  const [returnQuantity, setReturnQuantity] = useState<number>(prefill.quantity || maxQty)
  const [returnCondition, setReturnCondition] = useState<string>(prefill.return_condition || '')
  const [returnConditionNote, setReturnConditionNote] = useState<string>(prefill.return_condition_note || '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (prefill.quantity !== undefined) {
      setReturnQuantity(prefill.quantity)
    }
    if (prefill.return_condition) {
      setReturnCondition(prefill.return_condition)
    }
    if (prefill.return_condition_note !== undefined) {
      setReturnConditionNote(prefill.return_condition_note || '')
    }
  }, [prefill])

  const needsAttention = ATTENTION_CONDITIONS.has(returnCondition)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!returnCondition) {
      setError('Vui lòng chọn tình trạng khi trả.')
      return
    }
    if (returnQuantity < 1 || returnQuantity > maxQty) {
      setError(`Số lượng trả phải từ 1 đến ${maxQty}.`)
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const resp = await fetch(`/api/requests/${prefill.request_id}/return`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          return_condition: returnCondition,
          return_condition_note: returnConditionNote.trim() || null,
          quantity: returnQuantity,
        }),
        credentials: 'include',
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        throw new Error(data?.detail || `Lỗi ${resp.status}`)
      }
      const returned: RequestRead = await resp.json()
      onSubmitted(returned)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  function formatDate(iso?: string) {
    if (!iso) return ''
    return new Date(iso).toLocaleDateString('vi-VN')
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="borrow-form"
      style={{ maxWidth: 520 }}
      aria-label="Form trả thiết bị"
    >
      <div className="borrow-form__header">
        <h3 className="borrow-form__title">Trả thiết bị</h3>
        <p className="borrow-form__subtitle">Xác nhận trả thiết bị đang mượn</p>
      </div>

      {/* Read-only summary */}
      <div className="form-section" style={{ marginBottom: '1rem' }}>
        <div
          style={{
            background: 'var(--color-bg-secondary, #f8fafc)',
            border: '1px solid var(--color-border, #e2e8f0)',
            borderRadius: 8,
            padding: '0.85rem 1rem',
            fontSize: '0.9rem',
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: '1rem', rowGap: '0.35rem' }}>
            <span style={{ color: 'var(--color-text-muted)', fontWeight: 500 }}>Thiết bị:</span>
            <span style={{ fontWeight: 600 }}>
              {prefill.equipment_name}{' '}
              <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>({prefill.equipment_id})</span>
            </span>

            <span style={{ color: 'var(--color-text-muted)', fontWeight: 500 }}>Mã phiếu:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--color-primary)' }}>
              {prefill.display_id}
            </span>

            <span style={{ color: 'var(--color-text-muted)', fontWeight: 500 }}>Dự án:</span>
            <span>{prefill.project}</span>

            {prefill.needed_from && prefill.needed_to && (
              <>
                <span style={{ color: 'var(--color-text-muted)', fontWeight: 500 }}>Thời gian mượn:</span>
                <span>
                  {formatDate(prefill.needed_from)} → {formatDate(prefill.needed_to)}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Editable quantity stepper */}
      <div className="form-group">
        <label className="form-label" htmlFor="return-quantity">
          Số lượng hoàn trả <span style={{ color: 'var(--color-danger)' }}>*</span>
        </label>
        <p className="form-hint" style={{ marginBottom: '0.4rem', fontSize: '0.82rem', color: 'var(--color-text-muted)' }}>
          Hỗ trợ hoàn trả toàn bộ hoặc trả từng phần (1 đến {maxQty} cái).
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            type="button"
            className="btn btn--outline"
            style={{ width: 36, height: 36, padding: 0, fontWeight: 700 }}
            onClick={() => setReturnQuantity((prev) => Math.max(1, prev - 1))}
            disabled={submitting || returnQuantity <= 1}
            aria-label="Giảm số lượng trả"
          >
            -
          </button>
          <input
            id="return-quantity"
            type="number"
            className="form-control"
            style={{ width: 85, textAlign: 'center', fontWeight: 600 }}
            min={1}
            max={maxQty}
            value={returnQuantity}
            onChange={(e) => {
              const val = parseInt(e.target.value, 10)
              if (!isNaN(val)) {
                setReturnQuantity(Math.min(maxQty, Math.max(1, val)))
              }
            }}
            disabled={submitting}
            required
          />
          <button
            type="button"
            className="btn btn--outline"
            style={{ width: 36, height: 36, padding: 0, fontWeight: 700 }}
            onClick={() => setReturnQuantity((prev) => Math.min(maxQty, prev + 1))}
            disabled={submitting || returnQuantity >= maxQty}
            aria-label="Tăng số lượng trả"
          >
            +
          </button>
          <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
            / Tổng đang mượn {maxQty} cái
            {returnQuantity < maxQty && (
              <span style={{ color: 'var(--color-primary)', fontWeight: 600, marginLeft: 8 }}>
                (Trả từng phần {returnQuantity}/{maxQty})
              </span>
            )}
          </span>
        </div>
      </div>

      {/* Return condition */}
      <div className="form-group">
        <label className="form-label" htmlFor="return-condition">
          Tình trạng khi trả <span style={{ color: 'var(--color-danger)' }}>*</span>
        </label>
        <p className="form-hint" style={{ marginBottom: '0.4rem', fontSize: '0.82rem', color: 'var(--color-text-muted)' }}>
          Vui lòng chọn tình trạng thực tế của thiết bị tại thời điểm trả.
        </p>
        <select
          id="return-condition"
          className="form-control"
          value={returnCondition}
          onChange={(e) => setReturnCondition(e.target.value)}
          required
          disabled={submitting}
        >
          <option value="">-- Chọn tình trạng --</option>
          {RETURN_CONDITIONS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      {/* Attention warning */}
      {needsAttention && (
        <div
          className="alert alert--warning"
          role="alert"
          style={{ fontSize: '0.85rem', padding: '0.6rem 0.85rem', marginTop: '-0.25rem', marginBottom: '0.5rem' }}
        >
          Tình trạng này sẽ được đánh dấu để quản lý kiểm tra thêm.
        </div>
      )}

      {/* Note */}
      <div className="form-group">
        <label className="form-label" htmlFor="return-note">
          Ghi chú tình trạng khi trả
        </label>
        <p className="form-hint" style={{ marginBottom: '0.4rem', fontSize: '0.82rem', color: 'var(--color-text-muted)' }}>
          Mô tả ngắn vấn đề hoặc thay đổi của thiết bị, nếu có.
        </p>
        <textarea
          id="return-note"
          className="form-control"
          rows={3}
          value={returnConditionNote}
          onChange={(e) => setReturnConditionNote(e.target.value)}
          placeholder="Ví dụ: Vỏ ngoài bị trầy xước nhẹ ở góc phải..."
          disabled={submitting}
        />
      </div>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      <div className="borrow-form__actions">
        <button
          type="button"
          className="btn btn--outline btn--sm"
          onClick={onCancel}
          disabled={submitting}
        >
          Hủy bỏ
        </button>
        <button
          type="submit"
          className="btn btn--primary btn--sm"
          disabled={submitting || !returnCondition}
        >
          {submitting ? (
            <>
              <span className="spinner" style={{ marginRight: '0.35rem', width: 13, height: 13 }} />
              Đang xử lý...
            </>
          ) : (
            'Xác nhận trả thiết bị'
          )}
        </button>
      </div>
    </form>
  )
}
