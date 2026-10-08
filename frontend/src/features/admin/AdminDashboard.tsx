import { useState, useEffect } from 'react'
import { UserManagement } from './UserManagement'
import { ManagerDashboard } from '../manager/ManagerDashboard'
import { getHealthStatus } from '../../lib/api'
import type { HealthStatus } from '../../types'

type AdminTab = 'users' | 'requests' | 'health'

export function AdminDashboard() {
  const [currentTab, setCurrentTab] = useState<AdminTab>('users')
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [loadingHealth, setLoadingHealth] = useState(false)

  useEffect(() => {
    if (currentTab === 'health') {
      setLoadingHealth(true)
      getHealthStatus()
        .then(setHealth)
        .catch(() => null)
        .finally(() => setLoadingHealth(false))
    }
  }, [currentTab])

  return (
    <div>
      <div className="page-header" style={{ marginBottom: '1.25rem' }}>
        <div>
          <h1 className="page-title">Dashboard Quản trị viên (Admin)</h1>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.95rem', margin: '0.25rem 0 0 0' }}>
            Toàn quyền quản trị tài khoản, kiểm soát quy trình mượn trả và giám sát tích hợp hệ thống.
          </p>
        </div>
      </div>

      {/* Admin Tab Navigation */}
      <div className="filter-tabs" role="tablist" style={{ marginBottom: '1.5rem' }}>
        <button
          role="tab"
          aria-selected={currentTab === 'users'}
          className={`filter-tab${currentTab === 'users' ? ' filter-tab--active' : ''}`}
          onClick={() => setCurrentTab('users')}
        >
          Quản lý người dùng & Phân quyền
        </button>
        <button
          role="tab"
          aria-selected={currentTab === 'requests'}
          className={`filter-tab${currentTab === 'requests' ? ' filter-tab--active' : ''}`}
          onClick={() => setCurrentTab('requests')}
        >
          Xử lý yêu cầu mượn (Manager View)
        </button>
        <button
          role="tab"
          aria-selected={currentTab === 'health'}
          className={`filter-tab${currentTab === 'health' ? ' filter-tab--active' : ''}`}
          onClick={() => setCurrentTab('health')}
        >
          Trạng thái hệ thống & Tích hợp
        </button>
      </div>

      {/* Tab Contents */}
      {currentTab === 'users' && <UserManagement />}
      {currentTab === 'requests' && <ManagerDashboard />}
      {currentTab === 'health' && (
        <div style={{ marginTop: '1rem' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>
            Thông tin Kết nối & Trạng thái dịch vụ
          </h2>

          {loadingHealth ? (
            <div className="loading">Đang tải trạng thái hệ thống...</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
              <div
                style={{
                  background: 'var(--color-surface, #fff)',
                  border: '1px solid var(--color-border, #e2e8f0)',
                  borderRadius: '8px',
                  padding: '1.25rem',
                }}
              >
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.75rem', color: '#0f172a' }}>
                  Cơ sở dữ liệu Excel
                </h3>
                <div style={{ fontSize: '0.95rem', lineHeight: '1.7' }}>
                  <div>
                    <strong>Trạng thái:</strong>{' '}
                    <span style={{ color: '#16a34a', fontWeight: 600 }}>
                      {health?.excel?.status === 'connected' ? 'Đã kết nối' : 'Đang hoạt động'}
                    </span>
                  </div>
                  <div>
                    <strong>Tệp dữ liệu:</strong>{' '}
                    <code style={{ fontSize: '0.85rem' }}>{health?.excel?.path || 'backend/data/equipment_agent.xlsx'}</code>
                  </div>
                  <div style={{ marginTop: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>
                    Chứa đầy đủ 3 bảng tính: <code>Equipment</code>, <code>Equipment_Requests</code>, <code>Users</code>.
                  </div>
                </div>
              </div>

              <div
                style={{
                  background: 'var(--color-surface, #fff)',
                  border: '1px solid var(--color-border, #e2e8f0)',
                  borderRadius: '8px',
                  padding: '1.25rem',
                }}
              >
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.75rem', color: '#0f172a' }}>
                  Trí tuệ nhân tạo Gemini AI
                </h3>
                <div style={{ fontSize: '0.95rem', lineHeight: '1.7' }}>
                  <div>
                    <strong>Trạng thái:</strong>{' '}
                    <span
                      style={{
                        color:
                          health?.gemini?.status === 'connected'
                            ? '#16a34a'
                            : health?.gemini?.status === 'error'
                            ? '#dc2626'
                            : '#d97706',
                        fontWeight: 600,
                      }}
                    >
                      {health?.gemini?.status === 'connected'
                        ? 'Đã kết nối'
                        : health?.gemini?.status === 'error'
                        ? 'Lỗi xác thực'
                        : 'Dùng chế độ dự phòng (Demo)'}
                    </span>
                  </div>
                  {health?.gemini?.model && (
                    <div>
                      <strong>Mô hình:</strong> <code>{health.gemini.model}</code>
                    </div>
                  )}
                  <div style={{ marginTop: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>
                    Tự động phân tích và đề xuất mức độ ưu tiên (Priority Recommendation) cho từng yêu cầu.
                  </div>
                </div>
              </div>

              <div
                style={{
                  background: 'var(--color-surface, #fff)',
                  border: '1px solid var(--color-border, #e2e8f0)',
                  borderRadius: '8px',
                  padding: '1.25rem',
                }}
              >
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.75rem', color: '#0f172a' }}>
                  Thông báo Email
                </h3>
                <div style={{ fontSize: '0.95rem', lineHeight: '1.7' }}>
                  <div>
                    <strong>Trạng thái:</strong>{' '}
                    <span style={{ color: health?.email?.status === 'configured' ? '#16a34a' : '#64748b', fontWeight: 600 }}>
                      {health?.email?.status === 'configured' ? 'Đã kích hoạt' : 'Ghi nhận Console log (Mặc định)'}
                    </span>
                  </div>
                  <div style={{ marginTop: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>
                    Tự động gửi thông báo khi yêu cầu được phê duyệt hoặc từ chối.
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
