// Sélecteur d'émetteur de l'en-tête : recherche par nom, mnemonic ou ISIN, résultats groupés par indice.
// L'émetteur choisi passe dans l'URL (?isin=…) via setIsin (src/issuer/context.ts).
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'

import type { Stock } from '../api/types.ts'
import { useIssuer } from '../issuer/context.ts'

const INDEXES = ['DAX', 'MDAX', 'SDAX'] as const

const fold = (text: string) =>
  text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function matches(stock: Stock, query: string) {
  if (!query) return true
  const q = fold(query.trim())
  return [stock.name, stock.ticker, stock.isin].some((field) => fold(field).includes(q))
}

export function IssuerPicker() {
  const { issuer, stocks, setIsin } = useIssuer()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()

  const groups = useMemo(() => {
    const found = stocks.filter((stock) => matches(stock, query))
    return INDEXES.map((index) => ({
      index,
      items: found
        .filter((stock) => stock.index === index)
        .sort((a, b) => Number(b.is_selected) - Number(a.is_selected) || a.name.localeCompare(b.name)),
    })).filter((group) => group.items.length > 0)
  }, [stocks, query])
  const flat = useMemo(() => groups.flatMap((group) => group.items), [groups])

  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
    const onDown = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const choose = (stock: Stock) => {
    if (stock.coverage && !stock.coverage.dashboard) return
    setIsin(stock.isin)
    setOpen(false)
    setQuery('')
  }

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') setOpen(false)
    else if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((value) => Math.min(value + 1, flat.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((value) => Math.max(value - 1, 0))
    } else if (event.key === 'Enter' && flat[active]) {
      event.preventDefault()
      choose(flat[active])
    }
  }

  if (stocks.length === 0) return null

  return (
    <div className="issuer-picker" ref={wrapRef}>
      <button
        className="issuer-picker-toggle"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Issuer: ${issuer.name}. Change issuer`}
        onClick={() => setOpen((value) => !value)}
      >
        <strong>{issuer.ticker}</strong>
        <span className="issuer-picker-name">{issuer.name}</span>
        <span aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="issuer-picker-popover">
          <input
            ref={inputRef}
            type="search"
            value={query}
            placeholder="Search name, mnemonic or ISIN"
            aria-label="Search issuers"
            aria-controls={listId}
            onChange={(event) => {
              setQuery(event.target.value)
              setActive(0)
            }}
            onKeyDown={onKey}
          />
          <div className="issuer-picker-list" id={listId} role="listbox" aria-label="Issuers">
            {groups.length === 0 && <p className="issuer-picker-empty">No issuer matches “{query}”.</p>}
            {groups.map((group) => (
              <div key={group.index} role="group" aria-label={group.index}>
                <span className="issuer-picker-group">
                  {group.index} · {group.items.length}
                </span>
                {group.items.map((stock) => {
                  const position = flat.indexOf(stock)
                  const noData = stock.coverage ? !stock.coverage.dashboard : false
                  return (
                    <button
                      key={stock.isin}
                      role="option"
                      aria-selected={stock.isin === issuer.isin}
                      aria-disabled={noData}
                      className={`issuer-option${position === active ? ' is-active' : ''}${noData ? ' is-disabled' : ''}`}
                      onMouseEnter={() => setActive(position)}
                      onClick={() => choose(stock)}
                    >
                      <span>
                        <strong>{stock.name}</strong>
                        <small>
                          {stock.ticker} · {stock.isin}
                          {stock.index_history && stock.index_history.length > 1 &&
                            ` · ${stock.index_history.map((period) => period.index).join(' → ')} in 2026`}
                        </small>
                      </span>
                      {noData ? (
                        <em>Not enough data</em>
                      ) : stock.isin === issuer.isin ? (
                        <em>Selected</em>
                      ) : null}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
