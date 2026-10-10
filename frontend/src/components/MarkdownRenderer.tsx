import React from 'react'

interface MarkdownRendererProps {
  content: string
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  // Split into lines
  const lines = content.split('\n')
  const elements: React.ReactNode[] = []
  let currentList: string[] = []
  let currentTableLines: string[] = []

  const renderInline = (text: string): React.ReactNode[] => {
    // Parse **bold** and `code`
    const parts: React.ReactNode[] = []
    const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g
    let lastIndex = 0
    let match: RegExpExecArray | null

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index))
      }
      const token = match[0]
      if (token.startsWith('**') && token.endsWith('**')) {
        parts.push(
          <strong key={match.index} style={{ fontWeight: 600, color: 'var(--color-text, #0f172a)' }}>
            {token.slice(2, -2)}
          </strong>
        )
      } else if (token.startsWith('`') && token.endsWith('`')) {
        parts.push(
          <code
            key={match.index}
            style={{
              padding: '0.15rem 0.4rem',
              borderRadius: '4px',
              background: '#f1f5f9',
              fontSize: '0.9em',
              fontFamily: 'var(--font-mono)',
              color: '#0f172a',
            }}
          >
            {token.slice(1, -1)}
          </code>
        )
      }
      lastIndex = match.index + token.length
    }

    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex))
    }

    return parts.length > 0 ? parts : [text]
  }

  const flushList = (keyPrefix: number) => {
    if (currentList.length > 0) {
      elements.push(
        <ul
          key={`list-${keyPrefix}`}
          style={{
            margin: '0.65rem 0',
            paddingLeft: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.45rem',
            listStyleType: 'disc',
          }}
        >
          {currentList.map((item, idx) => (
            <li key={idx} style={{ lineHeight: 1.6 }}>
              {renderInline(item)}
            </li>
          ))}
        </ul>
      )
      currentList = []
    }
  }

  const flushTable = (keyPrefix: number) => {
    if (currentTableLines.length > 0) {
      const rawRows = currentTableLines.map((row) => {
        const trimmed = row.trim()
        const inner =
          trimmed.startsWith('|') && trimmed.endsWith('|')
            ? trimmed.slice(1, -1)
            : trimmed.replace(/^\|/, '').replace(/\|$/, '')
        return inner
          .split(/(?<!\\)\|/)
          .map((cell) => cell.replace(/\\\|/g, '|').trim())
      })

      if (rawRows.length > 0) {
        const headerRow = rawRows[0]
        let dataRows = rawRows.slice(1)
        if (
          dataRows.length > 0 &&
          dataRows[0].every((cell) => cell.replace(/-/g, '').replace(/:/g, '') === '')
        ) {
          dataRows = dataRows.slice(1)
        }

        elements.push(
          <div key={`table-wrapper-${keyPrefix}`} className="chat-table-wrapper">
            <table className="chat-table">
              <thead>
                <tr>
                  {headerRow.map((h, i) => (
                    <th key={i}>{renderInline(h)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataRows.map((row, rIdx) => (
                  <tr key={rIdx}>
                    {row.map((cell, cIdx) => (
                      <td key={cIdx}>{renderInline(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
      currentTableLines = []
    }
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim()
    // Check if it's a markdown table row
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushList(index)
      currentTableLines.push(trimmed)
    } else {
      flushTable(index)
      // Check if it's a bullet point
      if (trimmed.startsWith('• ') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        const itemContent = trimmed.slice(2).trim()
        currentList.push(itemContent)
      } else {
        flushList(index)
        if (trimmed === '') {
          // empty line - spacing
          elements.push(<div key={`empty-${index}`} style={{ height: '0.5rem' }} />)
        } else {
          elements.push(
            <p key={`p-${index}`} style={{ margin: '0.35rem 0', lineHeight: 1.65 }}>
              {renderInline(line)}
            </p>
          )
        }
      }
    }
  })

  flushList(lines.length)
  flushTable(lines.length)

  return <div className="markdown-content">{elements}</div>
}
