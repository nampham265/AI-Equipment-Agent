import { NavLink } from 'react-router-dom'
import { useAuth } from '../app/AuthContext'
import { logout } from '../lib/api'

export function Navbar() {
  const { user } = useAuth()

  // Generate 1-2 letter initial for avatar
  const getInitials = (name?: string) => {
    if (!name) return 'U'
    const parts = name.trim().split(/\s+/)
    if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
  }

  return (
    <header className="navbar" role="banner">
      {/* Brand logo & title */}
      <div className="navbar__brand-container">
        <div className="navbar__logo-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
        </div>
        <span className="navbar__brand">Quản lý Thiết bị</span>
      </div>

      {/* Navigation Links */}
      <nav className="navbar__nav" role="navigation" aria-label="Điều hướng chính">
        <NavLink
          to="/"
          className={({ isActive }) =>
            `navbar__link${isActive ? ' navbar__link--active' : ''}`
          }
          end
        >
          Trò chuyện
        </NavLink>
        <NavLink
          to="/my-requests"
          className={({ isActive }) =>
            `navbar__link${isActive ? ' navbar__link--active' : ''}`
          }
        >
          Yêu cầu của tôi
        </NavLink>
        {user?.is_manager && (
          <NavLink
            to="/manager"
            className={({ isActive }) =>
              `navbar__link${isActive ? ' navbar__link--active' : ''}`
            }
          >
            Quản lý
          </NavLink>
        )}
        {user?.is_admin && (
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              `navbar__link${isActive ? ' navbar__link--active' : ''}`
            }
          >
            Quản trị viên
          </NavLink>
        )}
      </nav>

      {/* User profile & Logout */}
      {user && (
        <div className="navbar__user">
          <div className="navbar__avatar">
            {getInitials(user.name)}
          </div>

          <div className="navbar__user-info">
            <span className="navbar__user-name">{user.name}</span>
            <span
              className={`navbar__user-role navbar__user-role--${user.role.toLowerCase()}`}
            >
              {user.role === 'ADMIN' ? 'Quản trị viên' : user.role === 'MANAGER' ? 'Quản lý' : 'Người dùng'}
            </span>
          </div>

          <button
            type="button"
            className="navbar__logout"
            title="Đăng xuất"
            onClick={async () => {
              try {
                await logout()
              } catch (_) {}
              window.location.href = '/'
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>Đăng xuất</span>
          </button>
        </div>
      )}
    </header>
  )
}
