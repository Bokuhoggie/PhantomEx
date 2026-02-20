<script>
  import { approveTrade, rejectTrade, pendingDecisions, trades, prices } from '../lib/ws.js'
  import PortfolioChart from './PortfolioChart.svelte'

  export let agent

  $: portfolio    = agent.portfolio || {}
  $: holdings     = portfolio.holdings || {}
  $: pnl          = portfolio.unrealized_pnl || {}
  $: pending      = $pendingDecisions[agent.id]
  $: thought      = agent.last_thought
  $: agentTrades  = $trades.filter(t => t.agent_id === agent.id && t.side !== 'hold')
  $: pnlDiff      = (portfolio.total_value || 0) - (agent.allowance || 0)
  $: pnlPct       = (agent.allowance || 1) > 0 ? (pnlDiff / agent.allowance) * 100 : 0
  $: holdingCount = Object.keys(holdings).length

  $: intervalLabel = agent.trade_interval
    ? agent.trade_interval >= 60
      ? Math.round(agent.trade_interval / 60) + 'm'
      : agent.trade_interval + 's'
    : null

  $: statusLabel = (() => {
    if (!agent.running && agent.started_at) return 'Stopped'
    if (!thought) return 'Idle'
    if (thought.action === 'buy')  return `Bought ${thought.symbol}`
    if (thought.action === 'sell') return `Sold ${thought.symbol}`
    return 'Holding'
  })()
  $: statusClass = !agent.running && agent.started_at ? 'stopped'
    : thought?.action === 'buy' ? 'buy'
    : thought?.action === 'sell' ? 'sell'
    : 'hold'

  // ── In-browser thought history ───────────────────────────────────────────────
  const MAX_THOUGHTS = 50
  let thoughtHistory = []
  let prevThoughtTs = null
  $: if (thought?.timestamp && thought.timestamp !== prevThoughtTs) {
    prevThoughtTs = thought.timestamp
    thoughtHistory = [thought, ...thoughtHistory].slice(0, MAX_THOUGHTS)
  }

  // ── Session timer ────────────────────────────────────────────────────────────
  let elapsed = 0
  let timerInterval = null

  $: {
    if (agent.started_at && agent.running !== false) {
      if (!timerInterval) {
        timerInterval = setInterval(() => {
          elapsed = Date.now() / 1000 - agent.started_at
        }, 1000)
      }
    } else {
      if (timerInterval) { clearInterval(timerInterval); timerInterval = null }
      elapsed = agent.started_at ? (Date.now() / 1000 - agent.started_at) : 0
    }
  }

  function fmtDuration(secs) {
    const h = Math.floor(secs / 3600)
    const m = Math.floor((secs % 3600) / 60)
    const s = Math.floor(secs % 60)
    if (h > 0) return `${h}h ${m}m`
    if (m > 0) return `${m}m ${s}s`
    return `${s}s`
  }

  $: durationProgress = agent.max_duration && elapsed ? elapsed / agent.max_duration : null
  $: durationLabel = agent.max_duration
    ? `${fmtDuration(elapsed)} / ${fmtDuration(agent.max_duration)}`
    : elapsed > 0 ? fmtDuration(elapsed) : null

  // ── Panel state ──────────────────────────────────────────────────────────────
  let walletOpen  = false
  let logOpen     = false
  let aiLogOpen   = false
  let trading     = false
  let tradeFlash  = false
  let depositAmount = ''
  let depositing    = false
  let depositError  = ''

  // ── Risk profile live toggle ─────────────────────────────────────────────────
  const RISK_CYCLE = ['aggressive', 'neutral', 'safe']
  async function cycleRisk() {
    const idx  = RISK_CYCLE.indexOf(agent.risk_profile)
    const next = RISK_CYCLE[(idx + 1) % RISK_CYCLE.length]
    await fetch(`/api/agents/${agent.id}/risk`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ risk_profile: next }),
    })
  }

  async function triggerTrade() {
    trading = true
    try {
      await fetch(`/api/agents/${agent.id}/trade`, { method: 'POST' })
      tradeFlash = true
      setTimeout(() => tradeFlash = false, 1400)
    } finally {
      trading = false
    }
  }

  async function deleteAgent() {
    if (!confirm(`Remove agent "${agent.name}"?`)) return
    await fetch(`/api/agents/${agent.id}`, { method: 'DELETE' })
  }

  async function toggleMode() {
    const next = agent.mode === 'autonomous' ? 'advisory' : 'autonomous'
    await fetch(`/api/agents/${agent.id}/mode`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: next }),
    })
  }

  async function deposit() {
    const amount = parseFloat(depositAmount)
    if (!amount || amount <= 0) { depositError = 'Enter a positive amount'; return }
    depositing = true
    depositError = ''
    try {
      const res = await fetch(`/api/agents/${agent.id}/deposit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount }),
      })
      if (!res.ok) throw new Error(await res.text())
      depositAmount = ''
    } catch(e) {
      depositError = e.message
    } finally {
      depositing = false
    }
  }

  function fmt(n, d = 2) {
    return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
  }
  function fmtTime(ts) {
    if (!ts) return ''
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }
  function fmtCompact(n) {
    if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + 'k'
    return fmt(n)
  }

  function riskEmoji(r) {
    if (r === 'aggressive') return '🔴'
    if (r === 'safe')       return '🟢'
    return '⚪'
  }
</script>

<div class="agent-card" class:flash={tradeFlash} class:advisory={agent.mode === 'advisory'} class:stopped={!agent.running && agent.started_at}>

  <!-- ── Header ── -->
  <div class="card-header">
    <div class="header-left">
      <div class="agent-name">{agent.name}</div>
      <div class="meta-pills">
        <span class="pill model">{agent.model.split(':')[0]}</span>
        {#if intervalLabel}
          <span class="pill interval">every {intervalLabel}</span>
        {/if}
        <button class="pill mode" on:click={toggleMode}>{agent.mode}</button>
        <!-- Live risk toggle pill -->
        {#if agent.risk_profile}
          <button
            class="pill risk {agent.risk_profile}"
            on:click={cycleRisk}
            title="Click to cycle risk profile"
          >{riskEmoji(agent.risk_profile)} {agent.risk_profile}</button>
        {/if}
        <!-- Session timer pill -->
        {#if durationLabel}
          <span class="pill timer" class:timer-warn={durationProgress && durationProgress > 0.75} class:timer-done={!agent.running && agent.started_at}>
            ⏱ {durationLabel}
          </span>
        {/if}
      </div>
    </div>
    <div class="header-right">
      <span class="status-dot {statusClass}">{statusLabel}</span>
      <button class="icon-btn delete" on:click={deleteAgent} title="Remove agent">✕</button>
    </div>
  </div>

  {#if agent.goal}
    <div class="goal-line">🎯 {agent.goal}</div>
  {/if}

  <!-- ── Equity Chart ── -->
  <div class="chart-section">
    <PortfolioChart {agent} height={70} />
  </div>

  <!-- ── KPI Row ── -->
  <div class="kpi-row">
    <div class="kpi">
      <span class="kpi-label">Portfolio</span>
      <span class="kpi-val">${fmtCompact(portfolio.total_value || 0)}</span>
    </div>
    <div class="kpi">
      <span class="kpi-label">Cash</span>
      <span class="kpi-val">${fmtCompact(portfolio.cash || 0)}</span>
    </div>
    <div class="kpi">
      <span class="kpi-label">P&L</span>
      <span class="kpi-val" class:pos={pnlDiff >= 0} class:neg={pnlDiff < 0}>
        {pnlDiff >= 0 ? '+' : ''}{fmtCompact(pnlDiff)}
        <span class="kpi-pct">({pnlPct >= 0 ? '+' : ''}{fmt(pnlPct)}%)</span>
      </span>
    </div>
    <div class="kpi">
      <span class="kpi-label">Trades</span>
      <span class="kpi-val">{agentTrades.length}</span>
    </div>
  </div>

  <!-- ── Holdings ── -->
  {#if holdingCount > 0}
    <div class="card-section">
      <div class="section-title">Holdings ({holdingCount})</div>
      <div class="holdings-list">
        {#each Object.entries(holdings) as [symbol, h]}
          {@const p = pnl[symbol] || {}}
          {@const currentPrice = $prices[symbol]?.price ?? h.avg_cost}
          {@const positionValue = h.quantity * currentPrice}
          <div class="holding-row">
            <span class="h-sym">{symbol}</span>
            <span class="h-qty">{fmt(h.quantity, 4)}</span>
            <span class="h-val">≈ ${fmtCompact(positionValue)}</span>
            <span class="h-pnl" class:pos={p.unrealized >= 0} class:neg={p.unrealized < 0}>
              {p.unrealized >= 0 ? '+' : ''}{fmtCompact(p.unrealized || 0)}
              <span class="h-pnl-pct">({fmt(p.pct || 0)}%)</span>
            </span>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- ── Advisory Pending Decision ── -->
  {#if pending}
    <div class="pending-block">
      <div class="pending-header">⚡ Awaiting Approval</div>
      <div class="pending-detail">
        <span class="pending-action {pending.action}">{pending.action.toUpperCase()}</span>
        {#if pending.symbol}
          <span class="pending-sym">{pending.quantity} {pending.symbol}</span>
        {/if}
      </div>
      <div class="pending-reasoning">"{pending.reasoning}"</div>
      <div class="pending-btns">
        <button class="btn-approve" on:click={() => approveTrade(agent.id)}>✓ Approve</button>
        <button class="btn-reject"  on:click={() => rejectTrade(agent.id)}>✕ Reject</button>
      </div>
    </div>
  {/if}

  <!-- ── Action Row ── -->
  <div class="action-row">
    <button class="trade-btn" on:click={triggerTrade} disabled={trading}>
      {trading ? '⏳ Thinking…' : '⚡ Trigger'}
    </button>
    <button class="toggle-btn wallet-toggle" on:click={() => walletOpen = !walletOpen}>
      💰 Wallet {walletOpen ? '▲' : '▼'}
    </button>
    <button class="toggle-btn log-toggle" on:click={() => logOpen = !logOpen}>
      📋 Log ({agentTrades.length}) {logOpen ? '▲' : '▼'}
    </button>
    <button class="toggle-btn ai-log-toggle" on:click={() => aiLogOpen = !aiLogOpen}>
      🧠 AI ({thoughtHistory.length}) {aiLogOpen ? '▲' : '▼'}
    </button>
  </div>

  <!-- ── Wallet Panel ── -->
  {#if walletOpen}
    <div class="expandable">
      <div class="wallet-rows">
        <div class="w-row"><span>Allowance</span><span>${fmt(agent.allowance || 0)}</span></div>
        <div class="w-row"><span>Cash</span><span>${fmt(portfolio.cash || 0)}</span></div>
        {#if holdingCount > 0}
          <div class="w-divider"></div>
          {#each Object.entries(holdings) as [symbol, h]}
            {@const cp = $prices[symbol]?.price ?? h.avg_cost}
            {@const posVal = h.quantity * cp}
            <div class="w-row">
              <span>{symbol} × {fmt(h.quantity, 4)}</span>
              <span>≈ ${fmtCompact(posVal)}</span>
            </div>
          {/each}
        {/if}
      </div>
      <div class="deposit-row">
        <input type="number" min="1" step="100" placeholder="Deposit amount ($)"
          bind:value={depositAmount} on:keydown={e => e.key === 'Enter' && deposit()}
          class="deposit-input" />
        <button class="deposit-btn" on:click={deposit} disabled={depositing}>
          {depositing ? '…' : '+ Deposit'}
        </button>
      </div>
      {#if depositError}<div class="deposit-err">{depositError}</div>{/if}
    </div>
  {/if}

  <!-- ── Trade Log Panel ── -->
  {#if logOpen}
    <div class="expandable log-body">
      {#if agentTrades.length === 0}
        <div class="log-empty">No trades yet.</div>
      {:else}
        {#each agentTrades.sort((a,b) => new Date(b.timestamp) - new Date(a.timestamp)) as t}
          <div class="log-trade">
            <span class="lt-side {t.side}">{t.side.toUpperCase()}</span>
            <span class="lt-sym">{t.symbol}</span>
            <span class="lt-qty">{fmt(t.quantity, 4)}</span>
            <span class="lt-price">@ ${fmtCompact(t.price)}</span>
            <span class="lt-total">${fmtCompact(t.total)}</span>
            <span class="lt-time">{fmtTime(t.timestamp)}</span>
          </div>
          {#if t.reasoning}
            <div class="lt-reasoning">"{t.reasoning}"</div>
          {/if}
        {/each}
      {/if}
    </div>
  {/if}

  <!-- ── AI Thought Log Panel ── -->
  {#if aiLogOpen}
    <div class="expandable ai-log-body">
      {#if thoughtHistory.length === 0}
        <div class="log-empty">No think cycles recorded yet.</div>
      {:else}
        {#each thoughtHistory as th}
          <div class="ai-entry">
            <div class="ai-entry-header">
              <span class="ai-action {th.action}">
                {th.action.toUpperCase()}
                {#if th.symbol && th.action !== 'hold'}
                  <span class="ai-detail">{th.quantity} {th.symbol}</span>
                {/if}
              </span>
              <span class="ai-time">{fmtTime(th.timestamp)}</span>
            </div>
            <div class="ai-reasoning">"{th.reasoning}"</div>
          </div>
        {/each}
      {/if}
    </div>
  {/if}

</div>

<style>
  .agent-card {
    background: #0c0c1e;
    border: 1px solid #1e1e3a;
    border-radius: 10px;
    padding: 0.9rem;
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
    min-width: 340px;
    max-width: 480px;
    width: 100%;
    transition: border-color 0.3s, box-shadow 0.3s;
  }
  .agent-card.flash {
    border-color: #7060d0;
    box-shadow: 0 0 18px rgba(112, 96, 208, 0.3);
  }
  .agent-card.advisory { border-color: #3a2a6a; }
  .agent-card.stopped  { opacity: 0.7; border-color: #2a2a3a; }

  /* Header */
  .card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; }
  .header-left { display: flex; flex-direction: column; gap: 0.3rem; }
  .header-right { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }

  .agent-name { font-size: 1rem; font-weight: 700; color: #d0c8ff; line-height: 1; }

  .meta-pills { display: flex; gap: 0.3rem; flex-wrap: wrap; align-items: center; }
  .pill {
    font-size: 0.65rem; padding: 2px 7px; border-radius: 4px;
    border: none; white-space: nowrap; line-height: 1.4;
  }
  .pill.model    { background: #1a1a30; color: #666; border: 1px solid #2e2e4a; }
  .pill.interval { background: #1a1430; color: #6050b0; border: 1px solid #2e2060; }
  .pill.mode     { background: #1e1a3a; color: #9070d0; border: 1px solid #3a2a6a; cursor: pointer; text-transform: capitalize; }
  .pill.mode:hover { background: #2e2a4a; }

  /* Timer pill */
  .pill.timer       { background: #1a1a30; color: #6060a0; border: 1px solid #2e2e4a; font-variant-numeric: tabular-nums; }
  .pill.timer-warn  { background: #2a1a0a; color: #e08020; border-color: #a05010; }
  .pill.timer-done  { background: #1a1a2a; color: #444; border-color: #2a2a3a; }

  /* Risk pill */
  .pill.risk {
    cursor: pointer;
    font-weight: 600;
    text-transform: capitalize;
    transition: background 0.2s, border-color 0.2s, color 0.2s;
  }
  .pill.risk.aggressive { background: #2a1010; border: 1px solid #ff6a4d; color: #ff6a4d; }
  .pill.risk.neutral    { background: #1e1e38; border: 1px solid #5a4a9a; color: #9080c0; }
  .pill.risk.safe       { background: #0a2018; border: 1px solid #00d4a0; color: #00d4a0; }
  .pill.risk:hover      { filter: brightness(1.2); }

  .status-dot {
    font-size: 0.63rem; font-weight: 600; padding: 2px 8px;
    border-radius: 10px; white-space: nowrap;
  }
  .status-dot.buy     { background: rgba(0,212,160,0.1);  color: #00d4a0; border: 1px solid rgba(0,212,160,0.3); }
  .status-dot.sell    { background: rgba(255,77,109,0.1); color: #ff4d6d; border: 1px solid rgba(255,77,109,0.3); }
  .status-dot.hold    { background: rgba(80,80,100,0.1);  color: #555;    border: 1px solid #2e2e4a; }
  .status-dot.stopped { background: rgba(60,60,80,0.1);   color: #444;    border: 1px solid #2e2e3a; }

  .icon-btn { background: none; border: none; cursor: pointer; color: #444; font-size: 0.82rem; padding: 2px 4px; border-radius: 3px; }
  .icon-btn.delete:hover { color: #ff4d6d; }

  .goal-line {
    font-size: 0.72rem; color: #5a4a8a; font-style: italic;
    border-left: 2px solid #2e2060; padding-left: 0.5rem; line-height: 1.3;
  }

  /* Chart */
  .chart-section { background: #06060f; border-radius: 6px; overflow: hidden; border: 1px solid #12122a; }

  /* KPI Row */
  .kpi-row {
    display: grid; grid-template-columns: repeat(4, 1fr);
    background: #080812; border-radius: 6px;
    padding: 0.5rem 0.6rem; border: 1px solid #12122a; gap: 0.4rem;
  }
  .kpi { display: flex; flex-direction: column; gap: 0.1rem; }
  .kpi-label { font-size: 0.56rem; color: #444; text-transform: uppercase; letter-spacing: 0.05em; }
  .kpi-val {
    font-size: 0.8rem; font-weight: 700; font-family: monospace; color: #c0c0d8;
    display: flex; align-items: baseline; gap: 0.2rem; flex-wrap: wrap;
  }
  .kpi-pct { font-size: 0.6rem; font-weight: 400; color: #555; }
  .pos { color: #00d4a0 !important; }
  .neg { color: #ff4d6d !important; }

  /* Holdings */
  .card-section { display: flex; flex-direction: column; gap: 0.25rem; }
  .section-title { font-size: 0.6rem; color: #444; text-transform: uppercase; letter-spacing: 0.06em; }
  .holdings-list { display: flex; flex-direction: column; gap: 0.15rem; }
  .holding-row { display: flex; gap: 0.5rem; align-items: center; font-size: 0.74rem; padding: 0.12rem 0; }
  .h-sym  { color: #a090d0; font-weight: 700; width: 40px; }
  .h-qty  { font-family: monospace; color: #888; font-size: 0.68rem; width: 64px; }
  .h-val  { font-family: monospace; color: #c0c0d0; font-size: 0.72rem; flex: 1; }
  .h-pnl  { font-family: monospace; font-size: 0.7rem; }
  .h-pnl-pct { font-size: 0.6rem; color: #666; }

  /* Pending */
  .pending-block {
    background: #100820; border: 1px solid #5a3a9a;
    border-radius: 6px; padding: 0.55rem 0.7rem;
    display: flex; flex-direction: column; gap: 0.3rem;
  }
  .pending-header { font-size: 0.68rem; font-weight: 700; color: #a080ff; }
  .pending-detail { display: flex; gap: 0.5rem; align-items: center; }
  .pending-action { font-size: 0.85rem; font-weight: 700; }
  .pending-action.buy  { color: #00d4a0; }
  .pending-action.sell { color: #ff4d6d; }
  .pending-sym { color: #c0c0d0; font-size: 0.85rem; }
  .pending-reasoning { font-size: 0.7rem; color: #7a6a9a; font-style: italic; }
  .pending-btns { display: flex; gap: 0.5rem; }
  .btn-approve {
    background: #00d4a0; color: #000; border: none;
    padding: 4px 16px; border-radius: 4px; font-size: 0.78rem; font-weight: 700; cursor: pointer;
  }
  .btn-approve:hover { background: #00f0b8; }
  .btn-reject {
    background: #1a0a1a; color: #ff4d6d; border: 1px solid #ff4d6d;
    padding: 4px 14px; border-radius: 4px; font-size: 0.78rem; cursor: pointer;
  }
  .btn-reject:hover { background: #2a1020; }

  /* Action Row */
  .action-row { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .trade-btn {
    background: #160c32; color: #a080ff; border: 1px solid #4a2a9a;
    padding: 0.42rem 0.75rem; border-radius: 6px; cursor: pointer;
    font-size: 0.76rem; font-weight: 600; flex: 1; transition: background 0.2s;
  }
  .trade-btn:hover:not(:disabled) { background: #2a1a58; }
  .trade-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .toggle-btn {
    background: #0c0c1e; color: #555; border: 1px solid #1e1e3a;
    padding: 0.42rem 0.55rem; border-radius: 6px; cursor: pointer;
    font-size: 0.7rem; white-space: nowrap; transition: border-color 0.15s, color 0.15s;
  }
  .wallet-toggle:hover  { border-color: #3a2a6a; color: #a080ff; }
  .log-toggle:hover     { border-color: #1a3a2a; color: #00d4a0; }
  .ai-log-toggle:hover  { border-color: #2a3a5a; color: #60a0e0; }

  /* Expandable panels */
  .expandable {
    background: #070710; border: 1px solid #18182e;
    border-radius: 6px; padding: 0.6rem 0.7rem;
    display: flex; flex-direction: column; gap: 0.25rem;
  }
  .wallet-rows { display: flex; flex-direction: column; gap: 0.2rem; }
  .w-row { display: flex; justify-content: space-between; font-size: 0.75rem; color: #888; }
  .w-row span:last-child { color: #c0c0d0; font-family: monospace; }
  .w-divider { height: 1px; background: #18182e; margin: 0.2rem 0; }
  .deposit-row {
    display: flex; gap: 0.4rem; margin-top: 0.3rem;
    padding-top: 0.4rem; border-top: 1px solid #18182e;
  }
  .deposit-input {
    background: #10102a; border: 1px solid #282848; color: #e0e0ff;
    padding: 4px 8px; border-radius: 4px; font-size: 0.75rem;
    flex: 1; outline: none; min-width: 0;
  }
  .deposit-input:focus { border-color: #5a4a9a; }
  .deposit-btn {
    background: #0a2018; color: #00d4a0; border: 1px solid #00d4a0;
    padding: 4px 10px; border-radius: 4px; font-size: 0.7rem;
    cursor: pointer; white-space: nowrap; font-weight: 600;
  }
  .deposit-btn:hover:not(:disabled) { background: #0a3020; }
  .deposit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .deposit-err { font-size: 0.68rem; color: #ff4d6d; }

  /* Trade Log Panel */
  .log-body { max-height: 280px; overflow-y: auto; gap: 0.1rem !important; }
  .log-empty { font-size: 0.7rem; color: #444; font-style: italic; }
  .log-trade {
    display: flex; gap: 0.4rem; font-size: 0.68rem;
    align-items: center; padding: 0.1rem 0;
  }
  .lt-side { font-weight: 700; width: 28px; }
  .lt-side.buy  { color: #00d4a0; }
  .lt-side.sell { color: #ff4d6d; }
  .lt-sym   { color: #a090d0; width: 34px; font-weight: 600; }
  .lt-qty   { font-family: monospace; color: #c0c0d0; flex: 1; }
  .lt-price { font-family: monospace; color: #888; }
  .lt-total { font-family: monospace; color: #6a5aaa; font-size: 0.64rem; }
  .lt-time  { color: #444; font-size: 0.6rem; margin-left: auto; }
  .lt-reasoning {
    font-size: 0.64rem; color: #4a4a6a; font-style: italic;
    padding: 0 0 0.2rem 0.5rem; border-left: 1px solid #28284a;
    margin: 0 0 0.1rem 2px; line-height: 1.3;
    white-space: pre-wrap; word-break: break-word;
  }

  /* AI Thought Log Panel */
  .ai-log-body { max-height: 320px; overflow-y: auto; gap: 0.35rem !important; }
  .ai-entry {
    border-left: 2px solid #1e2a3a; padding-left: 0.6rem;
    display: flex; flex-direction: column; gap: 0.2rem;
    padding-bottom: 0.3rem; border-bottom: 1px solid #10101e;
  }
  .ai-entry:last-child { border-bottom: none; }
  .ai-entry-header { display: flex; align-items: center; gap: 0.5rem; }
  .ai-action { font-size: 0.7rem; font-weight: 700; display: flex; align-items: center; gap: 0.4rem; }
  .ai-action.buy  { color: #00d4a0; }
  .ai-action.sell { color: #ff4d6d; }
  .ai-action.hold { color: #445; font-style: normal; }
  .ai-detail { font-weight: 400; color: #888; font-size: 0.65rem; }
  .ai-time   { margin-left: auto; font-size: 0.58rem; color: #444; }
  .ai-reasoning {
    font-size: 0.68rem; color: #6a6a8a; font-style: italic;
    line-height: 1.4; white-space: pre-wrap; word-break: break-word;
  }
</style>
