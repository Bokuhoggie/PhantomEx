<script>
  /**
   * SessionsPanel — browse and inspect saved session snapshots.
   * Fetches from GET /api/sessions on mount, supports expand/detail view and delete.
   * Auto-refreshes when sessionRefreshToken increments (e.g. after AgentCard saves).
   */
  import { onMount } from 'svelte'
  import { sessionRefreshToken } from '../lib/ws.js'

  let sessions = []
  let loading  = true
  let error    = null
  let expanded = null   // session id currently expanded
  let detail   = null   // full session detail (trades + equity)
  let loadingDetail = false
  let deletingId = null
  let recapturingId = null

  onMount(async () => {
    await refresh()
  })

  // Auto-refresh whenever a session is saved from an AgentCard
  let _prevToken = 0
  $: if ($sessionRefreshToken !== _prevToken) {
    _prevToken = $sessionRefreshToken
    refresh()
  }

  async function refresh() {
    loading = true
    error = null
    try {
      const res = await fetch('/api/sessions')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      sessions = await res.json()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  async function toggleExpand(session) {
    if (expanded === session.id) {
      expanded = null
      detail = null
      return
    }
    expanded = session.id
    detail = null
    loadingDetail = true
    try {
      const res = await fetch(`/api/sessions/${session.id}`)
      if (res.ok) detail = await res.json()
    } finally {
      loadingDetail = false
    }
  }

  async function deleteSession(id, e) {
    e.stopPropagation()
    if (!confirm('Delete this saved session?')) return
    deletingId = id
    try {
      await fetch(`/api/sessions/${id}`, { method: 'DELETE' })
      sessions = sessions.filter(s => s.id !== id)
      if (expanded === id) { expanded = null; detail = null }
    } finally {
      deletingId = null
    }
  }

  async function recaptureSession(id, e) {
    e.stopPropagation()
    recapturingId = id
    try {
      const res = await fetch(`/api/sessions/${id}/recapture`, { method: 'POST' })
      if (res.ok) {
        // Refresh the list and re-expand with updated detail
        await refresh()
        if (expanded === id) {
          detail = null
          loadingDetail = true
          try {
            const r = await fetch(`/api/sessions/${id}`)
            if (r.ok) detail = await r.json()
          } finally { loadingDetail = false }
        }
      }
    } finally {
      recapturingId = null
    }
  }

  function fmt(n, d = 2) {
    return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
  }
  function fmtCompact(n) {
    if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + 'k'
    return fmt(n)
  }
  function fmtDuration(secs) {
    if (!secs) return '—'
    const h = Math.floor(secs / 3600)
    const m = Math.floor((secs % 3600) / 60)
    if (h > 0) return `${h}h ${m}m`
    if (m > 0) return `${m}m`
    return `${Math.floor(secs)}s`
  }
  function fmtDate(ts) {
    if (!ts) return '—'
    return new Date(ts).toLocaleString([], {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  }
  function fmtTime(ts) {
    if (!ts) return ''
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }
</script>

<div class="sessions-panel">
  <div class="panel-header">
    <div class="panel-title">
      <span>Saved Sessions</span>
      {#if sessions.length > 0}
        <span class="count-badge">{sessions.length}</span>
      {/if}
    </div>
    <button class="refresh-btn" on:click={refresh} title="Refresh">↻</button>
  </div>

  <div class="panel-body">
    {#if loading}
      <div class="empty">Loading…</div>
    {:else if error}
      <div class="empty error">Error: {error}</div>
    {:else if sessions.length === 0}
      <div class="empty">No saved sessions yet.<br>Hit 💾 Save on an agent card to snapshot a session.</div>
    {:else}
      {#each sessions as s (s.id)}
        <!-- Session row -->
        <div
          class="session-row"
          class:expanded={expanded === s.id}
          on:click={() => toggleExpand(s)}
          role="button"
          tabindex="0"
          on:keydown={e => e.key === 'Enter' && toggleExpand(s)}
        >
          <div class="sr-left">
            <div class="sr-name">{s.agent_name}</div>
            <div class="sr-meta">
              <span class="sr-model">{s.model.split(':')[0]}</span>
              <span class="sr-risk risk-{s.risk_profile}">{s.risk_profile}</span>
              <span class="sr-dur">⏱ {fmtDuration(s.duration_secs)}</span>
              <span class="sr-date">{fmtDate(s.saved_at)}</span>
            </div>
          </div>

          <div class="sr-right">
            <div class="sr-pnl" class:pos={s.pnl >= 0} class:neg={s.pnl < 0}>
              {s.pnl >= 0 ? '+' : ''}{fmtCompact(s.pnl)}
              <span class="sr-pct">({s.pnl_pct >= 0 ? '+' : ''}{fmt(s.pnl_pct)}%)</span>
            </div>
            <div class="sr-counts">
              <span class="buy-ct">▲{s.buy_count}</span>
              <span class="sell-ct">▼{s.sell_count}</span>
              <span class="hold-ct">◼{s.hold_count}</span>
            </div>
          </div>

          <div class="sr-actions">
            <span class="sr-expand">{expanded === s.id ? '▲' : '▼'}</span>
            <button
              class="recap-btn"
              on:click={e => recaptureSession(s.id, e)}
              disabled={recapturingId === s.id}
              title="Rebuild session from full agent history"
            >{recapturingId === s.id ? '…' : '⟳'}</button>
            <button
              class="del-btn"
              on:click={e => deleteSession(s.id, e)}
              disabled={deletingId === s.id}
              title="Delete session"
            >✕</button>
          </div>
        </div>

        <!-- Expanded detail -->
        {#if expanded === s.id}
          <div class="session-detail">
            {#if loadingDetail && !detail}
              <div class="detail-loading">Loading detail…</div>
            {:else if detail}
              <!-- Summary stats row -->
              <div class="detail-stats">
                <div class="ds-item">
                  <span class="ds-label">Allowance</span>
                  <span class="ds-val">${fmt(detail.allowance)}</span>
                </div>
                <div class="ds-item">
                  <span class="ds-label">Final Value</span>
                  <span class="ds-val">${fmt(detail.final_value)}</span>
                </div>
                <div class="ds-item">
                  <span class="ds-label">Net P&L</span>
                  <span class="ds-val" class:pos={detail.pnl >= 0} class:neg={detail.pnl < 0}>
                    {detail.pnl >= 0 ? '+' : ''}{fmt(detail.pnl)}
                  </span>
                </div>
                <div class="ds-item">
                  <span class="ds-label">Duration</span>
                  <span class="ds-val">{fmtDuration(detail.duration_secs)}</span>
                </div>
                <div class="ds-item">
                  <span class="ds-label">Trades</span>
                  <span class="ds-val">
                    <span class="buy-ct">▲{detail.buy_count}</span>
                    <span class="sell-ct">▼{detail.sell_count}</span>
                  </span>
                </div>
              </div>

              <!-- Goal -->
              {#if detail.goal}
                <div class="detail-goal">🎯 {detail.goal}</div>
              {/if}

              <!-- AI Summary -->
              {#if detail.summary}
                <div class="detail-summary">
                  <span class="summary-label">AI Analysis</span>
                  {detail.summary}
                </div>
              {/if}

              <!-- Notes -->
              {#if detail.notes}
                <div class="detail-notes">📝 {detail.notes}</div>
              {/if}

              <!-- Trade list (buys + sells only, holds collapsed) -->
              {#if detail.trades && detail.trades.length > 0}
                <div class="detail-trades-header">Trade History</div>
                <div class="detail-trades">
                  {#each detail.trades.filter(t => t.side !== 'hold').sort((a,b) => new Date(b.timestamp) - new Date(a.timestamp)) as t}
                    <div class="dt-row">
                      <span class="dt-side {t.side}">{t.side.toUpperCase()}</span>
                      <span class="dt-sym">{t.symbol}</span>
                      <span class="dt-qty">{fmt(t.quantity, 4)}</span>
                      <span class="dt-price">@ ${fmtCompact(t.price)}</span>
                      <span class="dt-total">${fmtCompact(t.total)}</span>
                      <span class="dt-time">{fmtTime(t.timestamp)}</span>
                    </div>
                    {#if t.reasoning}
                      <div class="dt-reasoning">"{t.reasoning}"</div>
                    {/if}
                  {/each}
                </div>
              {:else}
                <div class="detail-empty">No trades recorded.</div>
              {/if}
            {/if}
          </div>
        {/if}
      {/each}
    {/if}
  </div>
</div>

<style>
  .sessions-panel {
    background: #0c0c1e;
    border: 1px solid #1e1e3a;
    border-radius: 8px;
    overflow: hidden;
  }

  /* Header */
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0.9rem;
    background: #0a0a1a;
    border-bottom: 1px solid #1a1a2e;
  }
  .panel-title {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #555;
    letter-spacing: 0.06em;
  }
  .count-badge {
    background: #1e1e3a;
    color: #777;
    font-size: 0.64rem;
    padding: 1px 6px;
    border-radius: 7px;
  }
  .refresh-btn {
    background: none;
    border: none;
    color: #444;
    cursor: pointer;
    font-size: 0.95rem;
    padding: 2px 4px;
    border-radius: 3px;
    line-height: 1;
  }
  .refresh-btn:hover { color: #a080ff; }

  /* Body */
  .panel-body {
    max-height: 520px;
    overflow-y: auto;
  }

  .empty {
    padding: 1.5rem;
    color: #333;
    text-align: center;
    font-size: 0.78rem;
    font-style: italic;
    line-height: 1.6;
  }
  .empty.error { color: #ff4d6d; font-style: normal; }

  /* Session row */
  .session-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.5rem 0.9rem;
    border-bottom: 1px solid #0d0d1e;
    cursor: pointer;
    transition: background 0.1s;
    user-select: none;
  }
  .session-row:hover        { background: #0f0f22; }
  .session-row.expanded     { background: #10102a; border-left: 2px solid #5a3aaa; }

  .sr-left { flex: 1; min-width: 0; }
  .sr-name {
    font-size: 0.8rem;
    font-weight: 700;
    color: #c0b8ff;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sr-meta {
    display: flex;
    gap: 0.4rem;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 0.15rem;
  }
  .sr-model { font-size: 0.62rem; color: #555; }
  .sr-risk  { font-size: 0.6rem; font-weight: 600; text-transform: capitalize; padding: 1px 5px; border-radius: 3px; }
  .risk-aggressive { background: #2a1010; color: #ff6a4d; border: 1px solid #ff6a4d44; }
  .risk-neutral    { background: #1a1a30; color: #9080c0; border: 1px solid #4a3a7a44; }
  .risk-safe       { background: #0a1a10; color: #00d4a0; border: 1px solid #00d4a044; }
  .sr-dur  { font-size: 0.6rem; color: #556; }
  .sr-date { font-size: 0.6rem; color: #444; }

  .sr-right { display: flex; flex-direction: column; align-items: flex-end; gap: 0.1rem; flex-shrink: 0; }
  .sr-pnl {
    font-size: 0.8rem;
    font-weight: 700;
    font-family: monospace;
    display: flex;
    align-items: baseline;
    gap: 0.25rem;
  }
  .sr-pct  { font-size: 0.62rem; font-weight: 400; color: #666; }
  .sr-counts {
    display: flex;
    gap: 0.35rem;
    font-size: 0.62rem;
  }
  .buy-ct  { color: #00d4a0; }
  .sell-ct { color: #ff4d6d; }
  .hold-ct { color: #444; }

  .pos { color: #00d4a0 !important; }
  .neg { color: #ff4d6d !important; }

  .sr-actions {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    flex-shrink: 0;
  }
  .sr-expand { font-size: 0.65rem; color: #444; }
  .recap-btn {
    background: none;
    border: none;
    color: #334;
    cursor: pointer;
    font-size: 0.78rem;
    padding: 2px 4px;
    border-radius: 3px;
    transition: color 0.15s;
  }
  .recap-btn:hover:not(:disabled) { color: #6090e0; }
  .recap-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .del-btn {
    background: none;
    border: none;
    color: #333;
    cursor: pointer;
    font-size: 0.7rem;
    padding: 2px 4px;
    border-radius: 3px;
    transition: color 0.15s;
  }
  .del-btn:hover:not(:disabled) { color: #ff4d6d; }
  .del-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* Expanded detail */
  .session-detail {
    background: #080816;
    border-bottom: 1px solid #1a1a2e;
    padding: 0.65rem 0.9rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }
  .detail-loading { font-size: 0.7rem; color: #444; font-style: italic; }

  /* Detail summary stats */
  .detail-stats {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    background: #0a0a1e;
    border-radius: 5px;
    padding: 0.4rem 0.6rem;
    border: 1px solid #14143a;
  }
  .ds-item { display: flex; flex-direction: column; gap: 0.05rem; }
  .ds-label {
    font-size: 0.55rem;
    color: #444;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .ds-val {
    font-size: 0.78rem;
    font-weight: 700;
    font-family: monospace;
    color: #c0c0d8;
    display: flex;
    gap: 0.3rem;
    align-items: baseline;
  }

  /* Goal */
  .detail-goal {
    font-size: 0.7rem;
    color: #5a4a8a;
    font-style: italic;
    padding: 0.25rem 0.5rem;
    border-left: 2px solid #2e2060;
    line-height: 1.4;
  }

  /* AI Summary */
  .detail-summary {
    background: #06080e;
    border: 1px solid #1a2a3a;
    border-left: 3px solid #2a4a7a;
    border-radius: 4px;
    padding: 0.4rem 0.6rem;
    font-size: 0.7rem;
    color: #7a9abb;
    line-height: 1.5;
    font-style: italic;
  }
  .summary-label {
    display: block;
    font-size: 0.55rem;
    font-style: normal;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #2a4a7a;
    margin-bottom: 0.2rem;
  }

  /* Notes */
  .detail-notes {
    font-size: 0.7rem;
    color: #6a6a8a;
    font-style: italic;
    padding: 0.3rem 0.5rem;
    border-left: 2px solid #2e2060;
    line-height: 1.4;
  }

  /* Trade history */
  .detail-trades-header {
    font-size: 0.6rem;
    color: #444;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.1rem;
  }
  .detail-trades {
    display: flex;
    flex-direction: column;
    gap: 0.05rem;
    max-height: 200px;
    overflow-y: auto;
  }
  .dt-row {
    display: flex;
    gap: 0.4rem;
    align-items: center;
    font-size: 0.67rem;
    padding: 0.08rem 0;
  }
  .dt-side { font-weight: 700; width: 30px; }
  .dt-side.buy  { color: #00d4a0; }
  .dt-side.sell { color: #ff4d6d; }
  .dt-sym   { color: #a090d0; font-weight: 600; width: 36px; }
  .dt-qty   { font-family: monospace; color: #c0c0d0; flex: 1; }
  .dt-price { font-family: monospace; color: #888; }
  .dt-total { font-family: monospace; color: #6a5aaa; font-size: 0.62rem; }
  .dt-time  { color: #444; font-size: 0.58rem; margin-left: auto; }
  .dt-reasoning {
    font-size: 0.62rem;
    color: #4a4a6a;
    font-style: italic;
    padding: 0 0 0.15rem 0.5rem;
    border-left: 1px solid #28284a;
    margin: 0 0 0.05rem 2px;
    line-height: 1.3;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .detail-empty {
    font-size: 0.7rem;
    color: #333;
    font-style: italic;
  }
</style>
