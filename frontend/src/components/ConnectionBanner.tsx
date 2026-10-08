import { useEffect, useState } from 'react'
import type { HealthStatus } from '../types'
import { getHealthStatus } from '../lib/api'

const LABEL: Record<string, string> = {
  connected: 'Đã kết nối',
  not_configured: 'Chưa cấu hình',
  error: 'Lỗi kết nối',
  configured: 'Đã cấu hình',
}

function Dot({ status }: { status: string }) {
  const cls = status === 'connected' || status === 'configured' ? 'ok' : status === 'error' ? 'err' : 'off'
  return <span className={`conn-dot conn-dot--${cls}`} aria-hidden />
}

export function ConnectionBanner() {
  const [health, setHealth] = useState<HealthStatus | null>(null)

  useEffect(() => {
    getHealthStatus().then(setHealth).catch(() => null)
  }, [])

  if (!health) return null

  return (
    <div className="connection-banner" role="status" aria-label="Trạng thái kết nối">
      {health.excel && (
        <div className="connection-banner__item">
          <Dot status={health.excel.status} />
          <span>Dữ liệu Excel: {LABEL[health.excel.status] ?? health.excel.status}</span>
        </div>
      )}
      <div className="connection-banner__item">
        <Dot status={health.gemini.status} />
        <span>Gemini AI: {LABEL[health.gemini.status] ?? health.gemini.status}
          {health.gemini.model ? ` (${health.gemini.model})` : ''}
        </span>
      </div>
      {health.microsoft_graph && health.microsoft_graph.status !== 'not_configured' && (
        <div className="connection-banner__item">
          <Dot status={health.microsoft_graph.status} />
          <span>Microsoft Lists: {LABEL[health.microsoft_graph.status] ?? health.microsoft_graph.status}</span>
        </div>
      )}
      <div className="connection-banner__item">
        <Dot status={health.email.status} />
        <span>Email: {LABEL[health.email.status] ?? health.email.status}</span>
      </div>
    </div>
  )
}
