import type { PriorityLevel } from '../types'

const PRIORITY_LABELS: Record<PriorityLevel, string> = {
  Critical: 'Khẩn cấp',
  High: 'Cao',
  Medium: 'Trung bình',
  Low: 'Thấp',
  'Needs review': 'Cần xem xét',
}

interface PriorityBadgeProps {
  level: PriorityLevel
}

export function PriorityBadge({ level }: PriorityBadgeProps) {
  const cssClass = level === 'Needs review' ? 'priority-Needs-review' : `priority-${level}`
  return (
    <span className={`priority-badge ${cssClass}`}>
      <span className="priority-badge__dot" />
      <span>{PRIORITY_LABELS[level] ?? level}</span>
    </span>
  )
}
