import React, { useState } from 'react'
import { devLogin, extractErrorMessage } from '../../lib/api'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleLoginWithEmail = async (targetEmail: string) => {
    const cleanEmail = targetEmail.trim()
    if (!cleanEmail) {
      setError('Vui lòng nhập địa chỉ email của bạn.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await devLogin(cleanEmail)
      window.location.reload()
    } catch (err) {
      setError(extractErrorMessage(err))
      setLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    handleLoginWithEmail(email)
  }

  const handleSsoClick = (provider: 'Google' | 'Microsoft') => {
    if (email.trim()) {
      handleLoginWithEmail(email)
    } else {
      setError(`Vui lòng nhập địa chỉ email của bạn để đăng nhập với ${provider}.`)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card" style={{ maxWidth: '440px' }}>
        {/* App Emblem / Logo */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '52px',
            height: '52px',
            borderRadius: '12px',
            backgroundColor: 'rgba(29, 108, 230, 0.08)',
            color: 'var(--color-primary, #1d6ce6)',
            marginBottom: '1.25rem',
          }}
        >
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
        </div>

        <h1 className="login-card__title">Đăng Nhập Hệ Thống</h1>
        <p className="login-card__subtitle">
          Cổng tra cứu thiết bị kỹ thuật & điều hành mượn trả
        </p>

        {error && (
          <div className="alert alert--error" role="alert" style={{ marginBottom: '1.25rem', textAlign: 'left', fontSize: '0.9rem' }}>
            {error}
          </div>
        )}

        {/* Standard Email Login Form */}
        <form onSubmit={handleSubmit} style={{ textAlign: 'left' }}>
          <div style={{ marginBottom: '1.35rem' }}>
            <label
              htmlFor="email-input"
              style={{
                display: 'block',
                fontSize: '1.02rem',
                fontWeight: 600,
                marginBottom: '0.5rem',
                color: 'var(--color-text)',
              }}
            >
              Địa chỉ Email
            </label>
            <input
              id="email-input"
              type="email"
              className="form-control"
              placeholder="vd: phamngochainam25@gmail.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              required
              autoFocus
              style={{
                width: '100%',
                padding: '0.8rem 1rem',
                fontSize: '1.05rem',
              }}
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary btn--lg"
            disabled={loading}
            style={{
              width: '100%',
              justifyContent: 'center',
              padding: '0.85rem',
              fontSize: '1.1rem',
              fontWeight: 600,
            }}
          >
            {loading ? 'Đang đăng nhập...' : 'Đăng nhập'}
          </button>
        </form>

        {/* Divider */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            margin: '1.75rem 0',
            color: 'var(--color-text-muted)',
            fontSize: '0.95rem',
          }}
        >
          <div style={{ flex: 1, height: '1px', background: 'var(--color-border-light, #e2e8f0)' }} />
          <span style={{ padding: '0 0.85rem', textTransform: 'lowercase' }}>hoặc đăng nhập với</span>
          <div style={{ flex: 1, height: '1px', background: 'var(--color-border-light, #e2e8f0)' }} />
        </div>

        {/* SSO Buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <button
            type="button"
            className="btn btn--outline"
            disabled={loading}
            onClick={() => handleSsoClick('Google')}
            style={{
              width: '100%',
              justifyContent: 'center',
              padding: '0.75rem',
              fontWeight: 500,
              gap: '0.75rem',
              fontSize: '1.02rem',
            }}
          >
            {/* Google Icon SVG */}
            <svg width="20" height="20" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
              />
            </svg>
            Google Workspace
          </button>

          <button
            type="button"
            className="btn btn--outline"
            disabled={loading}
            onClick={() => handleSsoClick('Microsoft')}
            style={{
              width: '100%',
              justifyContent: 'center',
              padding: '0.75rem',
              fontWeight: 500,
              gap: '0.75rem',
              fontSize: '1.02rem',
            }}
          >
            {/* Microsoft Icon SVG */}
            <svg width="20" height="20" viewBox="0 0 21 21">
              <rect x="1" y="1" width="9" height="9" fill="#f25022" />
              <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
              <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
              <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            Microsoft 365
          </button>
        </div>

        {/* Footer info */}
        <p
          className="login-card__info"
          style={{ marginTop: '2rem', fontSize: '0.95rem', color: 'var(--color-text-muted)' }}
        >
          Chưa có tài khoản hoặc cần phân quyền? Vui lòng liên hệ Quản trị viên hệ thống để được cấp quyền sử dụng.
        </p>
      </div>
    </div>
  )
}
