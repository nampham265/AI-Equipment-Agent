import { useState, useEffect } from 'react'
import type { Equipment, BorrowFormPrefill, EquipmentRequest } from '../../types'
import { createRequest, searchEquipment, extractErrorMessage } from '../../lib/api'

interface BorrowFormProps {
  prefill: BorrowFormPrefill
  onSubmitted: (request: EquipmentRequest) => void
  onCancel: () => void
}

interface FormState {
  project: string
  equipment_id: string
  quantity: string
  needed_from: string
  needed_to: string
  purpose: string
}

interface FormErrors {
  project?: string
  equipment_id?: string
  quantity?: string
  needed_from?: string
  needed_to?: string
  purpose?: string
  _submit?: string
}

export function BorrowForm({ prefill, onSubmitted, onCancel }: BorrowFormProps) {
  const today = new Date().toISOString().split('T')[0]

  const [form, setForm] = useState<FormState>({
    project: prefill.project ?? '',
    equipment_id: prefill.equipment_id ?? '',
    quantity: prefill.quantity ? String(prefill.quantity) : '1',
    needed_from: prefill.needed_from ?? today,
    needed_to: prefill.needed_to ?? today,
    purpose: prefill.purpose ?? '',
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitting, setSubmitting] = useState(false)
  const [equipmentList, setEquipmentList] = useState<Equipment[]>([])
  const [loadingEquipment, setLoadingEquipment] = useState(true)

  useEffect(() => {
    setLoadingEquipment(true)
    searchEquipment('')
      .then(setEquipmentList)
      .catch(() => setEquipmentList([]))
      .finally(() => setLoadingEquipment(false))
  }, [])

  const set = (field: keyof FormState) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }))
    setErrors((prev) => ({ ...prev, [field]: undefined, _submit: undefined }))
  }

  const validate = (): FormErrors => {
    const errs: FormErrors = {}
    if (!form.project.trim()) errs.project = 'Vui lòng nhập tên dự án.'
    if (!form.equipment_id) errs.equipment_id = 'Vui lòng chọn thiết bị.'
    const qty = parseInt(form.quantity, 10)
    if (!form.quantity || isNaN(qty) || qty < 1) errs.quantity = 'Số lượng phải là số nguyên dương.'
    if (!form.needed_from) errs.needed_from = 'Vui lòng chọn ngày bắt đầu.'
    if (!form.needed_to) errs.needed_to = 'Vui lòng chọn ngày dự kiến trả.'
    if (form.needed_from && form.needed_to && form.needed_to < form.needed_from) {
      errs.needed_to = 'Ngày dự kiến trả không được trước ngày bắt đầu.'
    }
    if (!form.purpose.trim()) errs.purpose = 'Vui lòng mô tả mục đích sử dụng.'
    return errs
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      return
    }

    setSubmitting(true)
    setErrors({})
    try {
      const request = await createRequest({
        project: form.project.trim(),
        equipment_id: form.equipment_id,
        quantity: parseInt(form.quantity, 10),
        needed_from: form.needed_from,
        needed_to: form.needed_to,
        purpose: form.purpose.trim(),
      })
      onSubmitted(request)
    } catch (err) {
      setErrors({ _submit: extractErrorMessage(err) })
    } finally {
      setSubmitting(false)
    }
  }

  const selectedEquipment = equipmentList.find((e) => e.equipment_id === form.equipment_id)

  return (
    <div className="borrow-form-card">
      <h3 className="borrow-form-card__title">Yêu cầu mượn thiết bị</h3>

      <form onSubmit={handleSubmit} noValidate>
        {errors._submit && (
          <div className="alert alert--error" role="alert">
            {errors._submit}
          </div>
        )}

        <div className="form-group">
          <label className="form-label form-label--required" htmlFor="bf-project">
            Dự án
          </label>
          <input
            id="bf-project"
            type="text"
            className={`form-control${errors.project ? ' form-control--error' : ''}`}
            value={form.project}
            onChange={set('project')}
            placeholder="Tên dự án"
            maxLength={200}
            disabled={submitting}
          />
          {errors.project && <span className="form-error">{errors.project}</span>}
        </div>

        <div className="form-group">
          <label className="form-label form-label--required" htmlFor="bf-equipment">
            Thiết bị
          </label>
          {loadingEquipment ? (
            <div className="text-muted">Đang tải danh sách thiết bị...</div>
          ) : (
            <select
              id="bf-equipment"
              className={`form-control${errors.equipment_id ? ' form-control--error' : ''}`}
              value={form.equipment_id}
              onChange={set('equipment_id')}
              disabled={submitting}
            >
              <option value="">-- Chọn thiết bị --</option>
              {equipmentList.map((eq) => (
                <option key={eq.equipment_id} value={eq.equipment_id}>
                  {eq.equipment_name} ({eq.equipment_id})
                </option>
              ))}
            </select>
          )}
          {errors.equipment_id && <span className="form-error">{errors.equipment_id}</span>}
          {selectedEquipment && (
            <span className="form-hint">
              Tổng số lượng kiểm kê: {selectedEquipment.quantity_total} {selectedEquipment.unit ?? 'đơn vị'}.
              Xem dashboard để biết số lượng khả dụng theo ngày.
            </span>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label className="form-label form-label--required" htmlFor="bf-quantity">
              Số lượng
            </label>
            <input
              id="bf-quantity"
              type="number"
              className={`form-control${errors.quantity ? ' form-control--error' : ''}`}
              value={form.quantity}
              onChange={set('quantity')}
              min={1}
              disabled={submitting}
            />
            {errors.quantity && <span className="form-error">{errors.quantity}</span>}
          </div>

          <div className="form-group" />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label className="form-label form-label--required" htmlFor="bf-from">
              Ngày bắt đầu
            </label>
            <input
              id="bf-from"
              type="date"
              className={`form-control${errors.needed_from ? ' form-control--error' : ''}`}
              value={form.needed_from}
              onChange={set('needed_from')}
              disabled={submitting}
            />
            {errors.needed_from && <span className="form-error">{errors.needed_from}</span>}
          </div>

          <div className="form-group">
            <label className="form-label form-label--required" htmlFor="bf-to">
              Ngày dự kiến trả
            </label>
            <input
              id="bf-to"
              type="date"
              className={`form-control${errors.needed_to ? ' form-control--error' : ''}`}
              value={form.needed_to}
              onChange={set('needed_to')}
              min={form.needed_from}
              disabled={submitting}
            />
            {errors.needed_to && <span className="form-error">{errors.needed_to}</span>}
          </div>
        </div>

        <div className="form-group">
          <label className="form-label form-label--required" htmlFor="bf-purpose">
            Mục đích sử dụng
          </label>
          <textarea
            id="bf-purpose"
            className={`form-control${errors.purpose ? ' form-control--error' : ''}`}
            value={form.purpose}
            onChange={set('purpose')}
            rows={2}
            placeholder="Mô tả mục đích sử dụng thiết bị"
            maxLength={500}
            disabled={submitting}
          />
          {errors.purpose && <span className="form-error">{errors.purpose}</span>}
        </div>

        <div className="form-actions">
          <button type="submit" className="btn btn--primary btn--sm" disabled={submitting}>
            {submitting ? <span className="spinner" /> : null}
            {submitting ? 'Đang gửi...' : 'Gửi yêu cầu'}
          </button>
          <button
            type="button"
            className="btn btn--outline btn--sm"
            onClick={onCancel}
            disabled={submitting}
          >
            Hủy
          </button>
        </div>
      </form>
    </div>
  )
}
