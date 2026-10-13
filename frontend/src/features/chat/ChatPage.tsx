import React, { useState, useRef, useEffect, useCallback } from 'react'
import type { AgentMessage, AgentAction, EquipmentRequest, BorrowFormPrefill, RequestRead } from '../../types'
import { sendAgentMessage, extractErrorMessage } from '../../lib/api'
import { BorrowForm } from './BorrowForm'
import { ReturnForm } from './ReturnForm'
import type { ReturnFormPrefill } from './ReturnForm'
import { StatusBadge } from '../../components/StatusBadge'
import { MarkdownRenderer } from '../../components/MarkdownRenderer'
import { useAuth } from '../../app/AuthContext'

export interface ChatEntry {
  id: string
  role: 'user' | 'assistant'
  content: string
  action?: AgentAction
  submittedRequest?: EquipmentRequest
  formDismissed?: boolean
  returnDismissed?: boolean
  submittedReturn?: RequestRead
  timestamp: Date
}

export interface ChatSession {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  entries: ChatEntry[]
}

function formatDate(d: Date): string {
  return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
}

function formatSessionDate(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    const today = new Date()
    const isToday =
      d.getDate() === today.getDate() &&
      d.getMonth() === today.getMonth() &&
      d.getFullYear() === today.getFullYear()

    if (isToday) {
      return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })
  } catch {
    return ''
  }
}

function createWelcomeEntry(): ChatEntry {
  return {
    id: `entry-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    role: 'assistant',
    content:
      'Xin chào! Tôi là Trợ lý AI Quản lý Kho Thiết bị Kỹ thuật.\n\nTôi có thể hỗ trợ bạn:\n• Tra cứu số lượng, tình trạng và vị trí thiết bị trong kho\n• Lập yêu cầu mượn thiết bị cho dự án\n• Theo dõi tiến độ xét duyệt yêu cầu\n\nBạn có thể chọn gợi ý bên dưới hoặc nhập câu hỏi trực tiếp.',
    timestamp: new Date(),
  }
}

function createNewSession(customTitle?: string): ChatSession {
  const now = new Date().toISOString()
  return {
    id: `session-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    title: customTitle || 'Cuộc trò chuyện mới',
    createdAt: now,
    updatedAt: now,
    entries: [createWelcomeEntry()],
  }
}

const QUICK_SUGGESTIONS = [
  {
    icon: '🔍',
    title: 'Danh sách thiết bị',
    prompt: 'Danh sách thiết bị trong kho có những gì?',
  },
  {
    icon: '⚡',
    title: 'Mượn thiết bị',
    prompt: 'Mình muốn mượn CAN Interface cho dự án Alpha',
  },
  {
    icon: '📦',
    title: 'Yêu cầu của tôi',
    prompt: 'Xem trạng thái các yêu cầu mượn của tôi',
  },
  {
    icon: '💡',
    title: 'Quy trình mượn trả',
    prompt: 'Quy trình đăng ký và xét duyệt mượn thiết bị như thế nào?',
  },
]

export function ChatPage() {
  const { user } = useAuth()
  const storageKey = `ai_equipment_sessions_${user?.email || 'guest'}`

  // Initialize sessions from localStorage or default
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) {
        const parsed: ChatSession[] = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) {
          // Revive Date objects in entries
          return parsed.map((s) => ({
            ...s,
            entries: s.entries.map((e) => ({
              ...e,
              timestamp: new Date(e.timestamp),
            })),
          }))
        }
      }
    } catch (err) {
      console.warn('Failed to parse saved sessions from localStorage:', err)
    }
    return [createNewSession()]
  })

  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    return sessions[0]?.id || 'default'
  })

  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('ai_equipment_sidebar_open')
      return saved !== null ? JSON.parse(saved) : true
    } catch {
      return true
    }
  })

  // Persist sidebar state
  useEffect(() => {
    try {
      localStorage.setItem('ai_equipment_sidebar_open', JSON.stringify(sidebarOpen))
    } catch (err) {
      console.warn('Failed to save sidebar state to localStorage:', err)
    }
  }, [sidebarOpen])

  // Support keyboard shortcut Ctrl+B / Cmd+B to toggle sidebar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        setSidebarOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Current active session
  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0]
  const entries = activeSession?.entries || []

  // Persist sessions to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(sessions))
    } catch (err) {
      console.warn('Failed to save chat sessions to localStorage:', err)
    }
  }, [sessions, storageKey])

  // Scroll to bottom on new message or loading change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [entries, loading])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`
    }
  }, [input])

  const conversationHistory = useCallback((): AgentMessage[] => {
    return entries
      .filter((e) => e.role === 'user' || (e.role === 'assistant' && !e.action))
      .map((e) => ({ role: e.role, content: e.content }))
  }, [entries])

  // Create a new session
  const handleNewChat = () => {
    const newSession = createNewSession()
    setSessions((prev) => [newSession, ...prev])
    setActiveSessionId(newSession.id)
    setInput('')
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  // Delete a session
  const handleDeleteSession = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    const confirmDelete = window.confirm('Bạn có chắc muốn xóa phiên trò chuyện này?')
    if (!confirmDelete) return

    setSessions((prev) => {
      const filtered = prev.filter((s) => s.id !== sessionId)
      if (filtered.length === 0) {
        const fresh = createNewSession()
        setActiveSessionId(fresh.id)
        return [fresh]
      }
      if (activeSessionId === sessionId) {
        setActiveSessionId(filtered[0].id)
      }
      return filtered
    })
  }

  // Send a message
  const handleSendPrompt = async (textToSend: string) => {
    const text = textToSend.trim()
    if (!text || loading) return

    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    const userEntry: ChatEntry = {
      id: `entry-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    }

    const currentEntries = [...entries, userEntry]
    const updatedTitle =
      activeSession.title === 'Cuộc trò chuyện mới'
        ? text.slice(0, 36) + (text.length > 36 ? '...' : '')
        : activeSession.title

    // Update session immediately with user message
    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSession.id
          ? {
              ...s,
              title: updatedTitle,
              updatedAt: new Date().toISOString(),
              entries: currentEntries,
            }
          : s
      )
    )

    setLoading(true)

    try {
      const response = await sendAgentMessage({
        message: text,
        conversation_history: conversationHistory(),
        conversation_id: activeSession.id,
      })

      const assistantEntry: ChatEntry = {
        id: `entry-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
        role: 'assistant',
        content: response.reply,
        action: response.action,
        timestamp: new Date(),
      }

      const updatedPreviousEntries = response.action
        ? currentEntries.map((e) => {
            if (response.action?.type === 'show_return_form' && e.action?.type === 'show_return_form') {
              return { ...e, returnDismissed: true }
            }
            if (response.action?.type === 'show_borrow_form' && e.action?.type === 'show_borrow_form') {
              return { ...e, formDismissed: true }
            }
            return e
          })
        : currentEntries

      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSession.id
            ? {
                ...s,
                updatedAt: new Date().toISOString(),
                entries: [...updatedPreviousEntries, assistantEntry],
              }
            : s
        )
      )
    } catch (err) {
      const errorEntry: ChatEntry = {
        id: `entry-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
        role: 'assistant',
        content: `Rất tiếc, đã có lỗi xảy ra: ${extractErrorMessage(err)}`,
        timestamp: new Date(),
      }

      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSession.id
            ? {
                ...s,
                updatedAt: new Date().toISOString(),
                entries: [...currentEntries, errorEntry],
              }
            : s
        )
      )
    } finally {
      setLoading(false)
      setTimeout(() => textareaRef.current?.focus(), 50)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendPrompt(input)
    }
  }

  const handleFormSubmitted = (entryId: string, request: EquipmentRequest) => {
    const confirmEntry: ChatEntry = {
      id: `entry-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      role: 'assistant',
      content: `🎉 Yêu cầu mượn thiết bị của bạn đã được ghi nhận thành công!\n\n• **Mã yêu cầu:** \`${request.display_id}\`\n• **Thiết bị:** **${request.equipment_name}**\n• **Trạng thái:** **Chờ duyệt**\n\nQuản lý phụ trách sẽ xem xét và phản hồi sớm cho bạn. Bạn có thể theo dõi tiến độ bất kỳ lúc nào tại mục **"Yêu cầu của tôi"**.`,
      timestamp: new Date(),
    }

    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSession.id
          ? {
              ...s,
              entries: [
                ...s.entries.map((e) =>
                  e.id === entryId ? { ...e, submittedRequest: request, formDismissed: true } : e
                ),
                confirmEntry,
              ],
            }
          : s
      )
    )
  }

  const handleFormCancelled = (entryId: string) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSession.id
          ? {
              ...s,
              entries: s.entries.map((e) =>
                e.id === entryId ? { ...e, formDismissed: true } : e
              ),
            }
          : s
      )
    )
  }

  const handleReturnFormSubmitted = (entryId: string, returned: RequestRead) => {
    const confirmEntry: ChatEntry = {
      id: `entry-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      role: 'assistant',
      content:
        `✅ Đã ghi nhận việc trả thiết bị thành công!\n\n` +
        `• **Mã phiếu:** \`${(returned as any).display_id || `REQ-${returned.id}`}\`\n` +
        `• **Thiết bị:** **${returned.equipment_name}**\n` +
        `• **Số lượng:** ${returned.quantity} cái\n` +
        `• **Tình trạng:** ${(returned as any).return_condition || ''}\n` +
        `• **Trạng thái mới:** **Đã trả**\n\n` +
        `Cảm ơn bạn đã trả thiết bị đúng hạn.`,
      timestamp: new Date(),
    }

    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSession.id
          ? {
              ...s,
              entries: [
                ...s.entries.map((e) =>
                  e.id === entryId ? { ...e, submittedReturn: returned, returnDismissed: true } : e
                ),
                confirmEntry,
              ],
            }
          : s
      )
    )
  }

  const handleReturnFormCancelled = (entryId: string) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSession.id
          ? {
              ...s,
              entries: s.entries.map((e) =>
                e.id === entryId ? { ...e, returnDismissed: true } : e
              ),
            }
          : s
      )
    )
  }


  // Get user initials
  const getUserInitials = (name?: string) => {
    if (!name) return 'U'
    const parts = name.trim().split(/\s+/)
    if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
  }

  const showHeroSuggestions = entries.length <= 1

  return (
    <div className="chat-page-wrapper">
      {/* ── Left Sidebar: Lịch sử hội thoại (ChatGPT / Gemini Style) ── */}
      <aside className={`chat-sidebar ${!sidebarOpen ? 'chat-sidebar--collapsed' : ''}`} aria-label="Lịch sử trò chuyện">
        <div className="chat-sidebar__header">
          <button
            type="button"
            className="chat-new-btn"
            onClick={handleNewChat}
            title="Bắt đầu đoạn chat mới"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Đoạn chat mới</span>
          </button>

          <button
            type="button"
            className="chat-collapse-btn"
            onClick={() => setSidebarOpen(false)}
            title="Đóng thanh lịch sử (Ctrl+B)"
            aria-label="Đóng thanh lịch sử"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <line x1="9" y1="3" x2="9" y2="21" />
              <polyline points="14 9 11 12 14 15" />
            </svg>
          </button>
        </div>

        <div className="chat-sidebar__content">
          <div className="chat-sidebar__section-title">Gần đây</div>

          {sessions.map((sess) => {
            const isActive = sess.id === activeSession.id
            return (
              <div
                key={sess.id}
                role="button"
                tabIndex={0}
                className={`chat-session-item ${isActive ? 'chat-session-item--active' : ''}`}
                onClick={() => setActiveSessionId(sess.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    setActiveSessionId(sess.id)
                  }
                }}
              >
                <div className="chat-session-item__icon">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </div>

                <div className="chat-session-item__text">
                  <span className="chat-session-item__title" title={sess.title}>
                    {sess.title}
                  </span>
                  <span className="chat-session-item__date">
                    {formatSessionDate(sess.updatedAt)}
                  </span>
                </div>

                <button
                  type="button"
                  className="chat-session-delete-btn"
                  title="Xóa đoạn chat này"
                  aria-label="Xóa đoạn chat"
                  onClick={(e) => handleDeleteSession(e, sess.id)}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            )
          })}
        </div>

        <div className="chat-sidebar__footer">
          <span>{sessions.length} cuộc trò chuyện</span>
          <span style={{ fontSize: '0.78rem', opacity: 0.8 }}>Tự động lưu</span>
        </div>
      </aside>

      {/* ── Main Chat Area ── */}
      <div className="chat-main-area">
        {/* Floating edge expand tab when sidebar is collapsed */}
        {!sidebarOpen && (
          <button
            type="button"
            className="chat-sidebar-edge-tab"
            onClick={() => setSidebarOpen(true)}
            title="Mở thanh lịch sử trò chuyện (Ctrl+B)"
            aria-label="Mở thanh lịch sử trò chuyện"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
            <span className="chat-sidebar-edge-tab__label">Lịch sử chat</span>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        )}

        {/* Top bar with Toggle & Active Title */}
        <div className="chat-topbar">
          <div className="chat-topbar__left">
            {!sidebarOpen && (
              <button
                type="button"
                className="chat-topbar-btn chat-topbar-btn--expand"
                onClick={() => setSidebarOpen(true)}
                title="Mở thanh lịch sử hội thoại (Ctrl+B)"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <line x1="9" y1="3" x2="9" y2="21" />
                  <polyline points="13 15 16 12 13 9" />
                </svg>
                <span>Mở lịch sử</span>
              </button>
            )}

            <span className="chat-topbar__title" title={activeSession?.title}>
              {activeSession?.title}
            </span>
          </div>

          <div className="chat-topbar__right">
            <button
              type="button"
              className="chat-topbar-btn"
              onClick={handleNewChat}
              title="Tạo phiên hội thoại mới"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span>Chat mới</span>
            </button>
          </div>
        </div>

        {/* Message Stream */}
        <div className="chat-layout">
          <div className="chat-messages" role="log" aria-live="polite" aria-label="Lịch sử hội thoại">
            {/* Gemini / Claude Inspired Hero Greeting */}
            {showHeroSuggestions && (
              <div className="chat-hero">
                <div className="chat-hero__sparkle">
                  <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M12 2L14.4 9.6L22 12L14.4 14.4L12 22L9.6 14.4L2 12L9.6 9.6L12 2Z"
                      fill="url(#sparkle-grad)"
                    />
                    <defs>
                      <linearGradient id="sparkle-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                        <stop stopColor="#2563eb" />
                        <stop offset="0.5" stopColor="#7c3aed" />
                        <stop offset="1" stopColor="#06b6d4" />
                      </linearGradient>
                    </defs>
                  </svg>
                </div>
                <h1 className="chat-hero__title">Trợ lý AI Kho Thiết bị Kỹ thuật</h1>
                <p className="chat-hero__subtitle">
                  Hỗ trợ tra cứu thiết bị, kiểm tra số lượng khả dụng và lập yêu cầu mượn trả
                </p>

                {/* Quick Suggestions Chips */}
                <div className="chat-hero__chips">
                  {QUICK_SUGGESTIONS.map((item, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="chat-suggestion-chip"
                      onClick={() => handleSendPrompt(item.prompt)}
                      disabled={loading}
                    >
                      <span className="chat-suggestion-chip__icon">{item.icon}</span>
                      <div className="chat-suggestion-chip__text">
                        <span className="chat-suggestion-chip__title">{item.title}</span>
                        <span className="chat-suggestion-chip__desc">{item.prompt}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Message Entries */}
            {entries.map((entry) => (
              <div
                key={entry.id}
                className={`chat-row chat-row--${entry.role}`}
              >
                {/* Avatar */}
                {entry.role === 'assistant' ? (
                  <div className="chat-avatar chat-avatar--assistant" title="Trợ lý AI">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                      <path
                        d="M12 2L14.4 9.6L22 12L14.4 14.4L12 22L9.6 14.4L2 12L9.6 9.6L12 2Z"
                        fill="currentColor"
                      />
                    </svg>
                  </div>
                ) : (
                  <div className="chat-avatar chat-avatar--user" title={user?.name || 'Bạn'}>
                    {getUserInitials(user?.name)}
                  </div>
                )}

                {/* Message Body */}
                <div className="chat-message-content">
                  <div className={`chat-bubble chat-bubble--${entry.role}`}>
                    {entry.role === 'assistant' ? (
                      <MarkdownRenderer content={entry.content} />
                    ) : (
                      <div>{entry.content}</div>
                    )}
                  </div>

                  {/* Inline Borrow Form */}
                  {entry.role === 'assistant' &&
                    entry.action?.type === 'show_borrow_form' &&
                    !entry.formDismissed &&
                    !entry.submittedRequest && (
                      <div className="mt-2" style={{ width: '100%' }}>
                        <BorrowForm
                          prefill={entry.action.prefill as BorrowFormPrefill}
                          onSubmitted={(req) => handleFormSubmitted(entry.id, req)}
                          onCancel={() => handleFormCancelled(entry.id)}
                        />
                      </div>
                    )}

                  {/* Inline Return Form */}
                  {entry.role === 'assistant' &&
                    entry.action?.type === 'show_return_form' &&
                    !entry.returnDismissed &&
                    !entry.submittedReturn && (
                      <div className="mt-2" style={{ width: '100%' }}>
                        <ReturnForm
                          prefill={entry.action.prefill as unknown as ReturnFormPrefill}
                          onSubmitted={(returned) => handleReturnFormSubmitted(entry.id, returned)}
                          onCancel={() => handleReturnFormCancelled(entry.id)}
                        />
                      </div>
                    )}

                  {/* Submitted Request Confirmation Card */}
                  {entry.submittedRequest && (
                    <div className="card mt-2" style={{ maxWidth: 480, padding: '1.25rem 1.5rem', borderRadius: 14 }}>
                      <div style={{ fontSize: '0.92rem', color: 'var(--color-text-secondary)' }}>
                        Phiếu mượn đã được khởi tạo:
                      </div>
                      <div style={{ fontWeight: 700, fontSize: '1.25rem', marginTop: '0.35rem', color: 'var(--color-primary)' }}>
                        {entry.submittedRequest.display_id}
                      </div>
                      <div style={{ marginTop: '0.65rem' }}>
                        <StatusBadge status={entry.submittedRequest.status} />
                      </div>
                    </div>
                  )}

                  {/* Submitted Return Confirmation Card */}
                  {entry.submittedReturn && (
                    <div className="card mt-2" style={{ maxWidth: 480, padding: '1.25rem 1.5rem', borderRadius: 14 }}>
                      <div style={{ fontSize: '0.92rem', color: 'var(--color-text-secondary)' }}>
                        Đã ghi nhận trả thiết bị:
                      </div>
                      <div style={{ fontWeight: 700, fontSize: '1.25rem', marginTop: '0.35rem', color: 'var(--color-primary)' }}>
                        {entry.submittedReturn.display_id || `REQ-${entry.submittedReturn.id}`}
                      </div>
                      <div style={{ marginTop: '0.65rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <StatusBadge status={entry.submittedReturn.status} />
                        {entry.submittedReturn.return_condition && (
                          <span className="badge badge--neutral" style={{ fontSize: '0.8rem' }}>
                            {entry.submittedReturn.return_condition}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  <span className="chat-meta">{formatDate(entry.timestamp)}</span>
                </div>
              </div>
            ))}

            {/* Loading / Thinking State */}
            {loading && (
              <div className="chat-row chat-row--assistant">
                <div className="chat-avatar chat-avatar--assistant">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M12 2L14.4 9.6L22 12L14.4 14.4L12 22L9.6 14.4L2 12L9.6 9.6L12 2Z"
                      fill="currentColor"
                    />
                  </svg>
                </div>
                <div className="chat-message-content">
                  <div className="chat-bubble chat-bubble--assistant chat-thinking">
                    <span className="chat-thinking__dot" />
                    <span className="chat-thinking__dot" />
                    <span className="chat-thinking__dot" />
                    <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.98rem' }}>
                      Trợ lý đang xử lý dữ liệu...
                    </span>
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Floating Prompt Capsule Bar (Claude / Gemini / ChatGPT style) */}
          <div className="chat-prompt-wrapper">
            <div className="chat-capsule">
              <textarea
                ref={textareaRef}
                className="chat-capsule__input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Hỏi trợ lý thiết bị hoặc gửi yêu cầu mượn... (Enter để gửi, Shift+Enter xuống dòng)"
                rows={1}
                disabled={loading}
                aria-label="Nhập câu hỏi"
              />

              <div className="chat-capsule__footer">
                <div className="chat-capsule__actions-left">
                  <button
                    type="button"
                    className="capsule-tool-btn"
                    title="Tạo nhanh yêu cầu mượn thiết bị"
                    onClick={() => handleSendPrompt('Tôi muốn mở form mượn thiết bị')}
                    disabled={loading}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                      <line x1="12" y1="5" x2="12" y2="19" />
                      <line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    <span>Mượn thiết bị</span>
                  </button>

                  <span className="model-chip" title="Mô hình AI hỗ trợ">
                    <span className="model-chip__dot" />
                    <span>Trợ lý Kỹ thuật</span>
                  </span>
                </div>

                <div className="chat-capsule__actions-right">
                  <button
                    type="button"
                    className={`chat-send-btn${input.trim() && !loading ? ' chat-send-btn--active' : ''}`}
                    onClick={() => handleSendPrompt(input)}
                    disabled={loading || !input.trim()}
                    title="Gửi câu hỏi (Enter)"
                    aria-label="Gửi câu hỏi"
                  >
                    {loading ? (
                      <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="19" x2="12" y2="5" />
                        <polyline points="5 12 12 5 19 12" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            </div>

            <div className="chat-disclaimer">
              Trợ lý AI hỗ trợ tra cứu và đề xuất ưu tiên. Quyết định phê duyệt thuộc về Quản lý hệ thống.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
