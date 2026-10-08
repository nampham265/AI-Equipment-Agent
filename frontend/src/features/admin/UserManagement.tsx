import React, { useState, useEffect, useCallback } from 'react'
import type { UserAccount } from '../../types'
import {
  getAdminUsers,
  createAdminUser,
  updateUserRole,
  updateUserActive,
  extractErrorMessage,
} from '../../lib/api'

export function UserManagement() {
  const [users, setUsers] = useState<UserAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Add User Form State
  const [newEmail, setNewEmail] = useState('')
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState<'USER' | 'MANAGER'>('USER')
  const [submitting, setSubmitting] = useState(false)
  const [actionLoadingEmail, setActionLoadingEmail] = useState<string | null>(null)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAdminUsers()
      setUsers(data)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadUsers()
  }, [loadUsers])

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newEmail.trim() || !newName.trim()) {
      setError('Vui lòng điền đầy đủ email và họ tên người dùng.')
      return
    }

    setSubmitting(true)
    setError(null)
    setSuccessMsg(null)
    try {
      await createAdminUser({
        user_email: newEmail.trim(),
        user_name: newName.trim(),
        role: newRole,
      })
      setSuccessMsg(`Đã tạo thành công tài khoản: ${newEmail.trim()} (${newRole})`)
      setNewEmail('')
      setNewName('')
      setNewRole('USER')
      await loadUsers()
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggleRole = async (user: UserAccount) => {
    if (user.role === 'ADMIN') return
    const targetRole: 'USER' | 'MANAGER' = user.role === 'USER' ? 'MANAGER' : 'USER'
    setActionLoadingEmail(user.user_email)
    setError(null)
    setSuccessMsg(null)
    try {
      const updated = await updateUserRole(user.user_email, targetRole)
      setUsers((prev) =>
        prev.map((u) => (u.user_email === user.user_email ? updated : u))
      )
      setSuccessMsg(`Đã chuyển vai trò của ${user.user_name} sang ${targetRole}.`)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setActionLoadingEmail(null)
    }
  }

  const handleToggleActive = async (user: UserAccount) => {
    const targetActive = !user.is_active
    setActionLoadingEmail(user.user_email)
    setError(null)
    setSuccessMsg(null)
    try {
      const updated = await updateUserActive(user.user_email, targetActive)
      setUsers((prev) =>
        prev.map((u) => (u.user_email === user.user_email ? updated : u))
      )
      setSuccessMsg(
        `Đã ${targetActive ? 'kích hoạt lại' : 'vô hiệu hóa'} tài khoản ${user.user_name}.`
      )
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setActionLoadingEmail(null)
    }
  }

  return (
    <div style={{ marginTop: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 600, margin: 0 }}>
            Quản lý Người dùng & Phân quyền
          </h2>
        </div>
        <button className="btn btn--outline btn--sm" onClick={loadUsers} disabled={loading}>
          {loading ? 'Đang tải...' : 'Làm mới'}
        </button>
      </div>

      {error && (
        <div className="alert alert--error" role="alert" style={{ marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      {successMsg && (
        <div className="alert alert--info" role="status" style={{ marginBottom: '1rem' }}>
          {successMsg}
        </div>
      )}

      {/* Form Add User */}
      <div
        style={{
          background: 'var(--color-surface, #fff)',
          border: '1px solid var(--color-border, #e2e8f0)',
          borderRadius: '8px',
          padding: '1.25rem',
          marginBottom: '1.5rem',
        }}
      >
        <h3 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '1rem' }}>
          Thêm người dùng mới
        </h3>
        <form onSubmit={handleCreateUser} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 260px' }}>
            <label style={{ display: 'block', fontSize: '1rem', fontWeight: 600, marginBottom: '0.45rem' }}>
              Email tài khoản *
            </label>
            <input
              type="email"
              className="form-control"
              placeholder="vd: nguyenvana@st.ueh.edu.vn"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              disabled={submitting}
              required
            />
          </div>

          <div style={{ flex: '1 1 220px' }}>
            <label style={{ display: 'block', fontSize: '1rem', fontWeight: 600, marginBottom: '0.45rem' }}>
              Họ và tên *
            </label>
            <input
              type="text"
              className="form-control"
              placeholder="vd: Nguyễn Văn A"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              disabled={submitting}
              required
            />
          </div>

          <div style={{ flex: '0 0 180px' }}>
            <label style={{ display: 'block', fontSize: '1rem', fontWeight: 600, marginBottom: '0.45rem' }}>
              Vai trò *
            </label>
            <select
              className="form-control"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as 'USER' | 'MANAGER')}
              disabled={submitting}
            >
              <option value="USER">USER (Người dùng)</option>
              <option value="MANAGER">MANAGER (Quản lý)</option>
            </select>
          </div>

          <div>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={submitting}
              style={{ minWidth: '140px', justifyContent: 'center', padding: '0.65rem 1.25rem' }}
            >
              {submitting ? 'Đang lưu...' : '+ Thêm người dùng'}
            </button>
          </div>
        </form>
      </div>

      {/* Users Table */}
      {loading ? (
        <div className="loading">Đang tải danh sách tài khoản...</div>
      ) : users.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">Chưa có người dùng nào được cấu hình trong bảng Users.</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Họ và tên</th>
                <th>Vai trò</th>
                <th>Trạng thái</th>
                <th style={{ textAlign: 'right' }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const isItemLoading = actionLoadingEmail === u.user_email
                return (
                  <tr key={u.user_email}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.98rem' }}>
                      {u.user_email}
                    </td>
                    <td style={{ fontWeight: 600, fontSize: '1.02rem' }}>{u.user_name}</td>
                    <td>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.25rem 0.65rem',
                          borderRadius: '6px',
                          fontSize: '0.88rem',
                          fontWeight: 600,
                          backgroundColor:
                            u.role === 'ADMIN'
                              ? '#fef3c7'
                              : u.role === 'MANAGER'
                              ? '#e0e7ff'
                              : '#f1f5f9',
                          color:
                            u.role === 'ADMIN'
                              ? '#92400e'
                              : u.role === 'MANAGER'
                              ? '#3730a3'
                              : '#475569',
                          border: `1px solid ${
                            u.role === 'ADMIN'
                              ? '#fde68a'
                              : u.role === 'MANAGER'
                              ? '#c7d2fe'
                              : '#cbd5e1'
                          }`,
                        }}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.25rem 0.65rem',
                          borderRadius: '6px',
                          fontSize: '0.88rem',
                          fontWeight: 600,
                          backgroundColor: u.is_active ? '#dcfce7' : '#fee2e2',
                          color: u.is_active ? '#166534' : '#991b1b',
                          border: `1px solid ${u.is_active ? '#bbf7d0' : '#fecaca'}`,
                        }}
                      >
                        {u.is_active ? 'Hoạt động' : 'Vô hiệu hóa'}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {u.role === 'ADMIN' ? (
                        <span style={{ fontSize: '0.95rem', color: 'var(--color-text-muted)', fontWeight: 500 }}>
                          Tài khoản Quản trị viên
                        </span>
                      ) : (
                        <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                          <button
                            type="button"
                            className="btn btn--outline btn--sm"
                            disabled={isItemLoading}
                            onClick={() => handleToggleRole(u)}
                            title={`Chuyển sang ${u.role === 'USER' ? 'MANAGER' : 'USER'}`}
                          >
                            Đổi thành {u.role === 'USER' ? 'Quản lý' : 'Người dùng'}
                          </button>
                          <button
                            type="button"
                            className={`btn btn--sm ${u.is_active ? 'btn--danger' : 'btn--primary'}`}
                            disabled={isItemLoading}
                            onClick={() => handleToggleActive(u)}
                          >
                            {u.is_active ? 'Vô hiệu hóa' : 'Kích hoạt'}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
