<script>
  import { approveTrade, rejectTrade, pendingDecisions, trades } from '../lib/ws.js'

  export let agent

  $: portfolio = agent.portfolio || {}
  $: holdings = portfolio.holdings || {}
  $: pnl = portfolio.unrealized_pnl || {}
  $: pending = $pendingDecisions[agent.id]
  $: thought = agent.last_thought
  $: agentTrades = $trades.filter(t => t.agent_id === agent.id).slice(0, 5)
  $: pnlDiff = (portfolio.total_value || 0) - (agent.allowance || 0)
  $: pnlPct = fmt((pnlDiff / (agent.allowance || 1)) * 100)
  $: inPositions = (agent.allowance || 0) - (portfolio.cash || 0)

  let trading = false
  let tradeFlash = false
  let walletOpen = false
  let depositAmount = ''
  let depositing = false
  let depositError = ''

  async function triggerTrade() {
    trading = true
    try {
      await fetch(`/api/agents/${agent.id}/trade`, { method: 'POST' })
      tradeFlash = true
      setTimeout(() => tradeFlash = false, 1200)
    } finally {
      trading = false
    }
  }

  async function deleteAgent() {
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

  function fmtTime(ts) {
    if (!ts) return ''
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  function fmt(n, d = 2) {
    return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
  }
</script>

<div class="agent-card" class:flash={tradeFlash}>
  <!-- Header -->
  <div class="agent-header">
    <div class="agent-name">{agent.name}</div>
    <div class="agent-meta">
      <span class="model-badge">{agent.model}</span>
      <button class="mode-btn" on:click={toggleMode}>{agent.mode}</button>
      <button class="delete-btn" on:click={deleteAgent}>✕</button>
    </div>
  </div>

  {#if agent.goal}
    <div class="goal-line">🎯 {agent.goal}</div>
  {/if}

  <!-- Portfolio summary -->
  <div class="portfolio-summary">
    <div class="stat">
      <span class="label">Cash</span>
      <span class="value">${fmt(portfolio.cash || 0)}</span>
    </div>
    <div class="stat">
      <span class="label">Total Value</span>
      <span class="value">${fmt(portfolio.total_value || 0)}</span>
    </div>
    <div class="stat">
      <span class="label">P&L</span>
      <span class="value" class:pos={pnlDiff >= 0} class:neg={pnlDiff < 0}>
        {pnlDiff >= 0 ? '+' : ''}{fmt(pnlDiff)} ({pnlPct}%)
      </span>
    </div>
  </div>

  <!-- Holdings -->
  {#if Object.keys(holdings).length > 0}
    <div class="section">
      <div class="section-label">Holdings</div>
      {#each Object.entries(holdings) as [symbol, h]}
        {@const p = pnl[symbol] || {}}
        <div class="holding-row">
          <span class="h-symbol">{symbol}</span>
          <span class="h-qty">{h.quantity.toFixed(6)}</span>
          <span class="h-pnl" class:pos={p.unrealized >= 0} class:neg={p.unrealized < 0}>
            {p.unrealized >= 0 ? '+' : ''}{fmt(p.unrealized || 0)} ({fmt(p.pct || 0)}%)
          </span>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Wallet section -->
  <div class="section">
    <button class="section-toggle" on:click={() => walletOpen = !walletOpen}>
      <span class="section-label">Wallet</span>
      <span class="toggle-arrow">{walletOpen ? '▲' : '▼'}</span>
    </button>

    {#if walletOpen}
      <div class="wallet-body">
        <div class="wallet-row">
          <span class="w-label">Starting Allowance</span>
          <span class="w-value">${fmt(agent.allowance || 0)}</span>
        </div>
        <div class="wallet-row">
          <span class="w-label">Cash Remaining</span>
          <span class="w-value">${fmt(portfolio.cash || 0)}</span>
        </div>
        <div class="wallet-row">
          <span class="w-label">In Positions</span>
          <span class="w-value">${fmt(inPositions > 0 ? inPositions : 0)}</span>
        </div>

        {#if Object.keys(holdings).length > 0}
          <div class="w-holdings-header">Holdings Detail</div>
          {#each Object.entries(holdings) as [symbol, h]}
            <div class="wallet-row">
              <span class="w-label">{symbol} × {h.quantity.toFixed(6)}</span>
              <span class="w-value w-subtle">avg ${fmt(h.avg_cost)}</span>
            </div>
          {/each}
        {/if}

        <div class="deposit-row">
          <input
            class="deposit-input"
            type="number"
            min="1"
            step="100"
            placeholder="Amount ($)"
            bind:value={depositAmount}
            on:keydown={e => e.key === 'Enter' && deposit()}
          />
          <button class="deposit-btn" on:click={deposit} disabled={depositing}>
            {depositing ? '...' : '+ Deposit'}
          </button>
        </div>
        {#if depositError}
          <div class="deposit-error">{depositError}</div>
        {/if}
      </div>
    {/if}
  </div>

  <!-- Make Trade button -->
  <button class="trade-btn" on:click={triggerTrade} disabled={trading}>
    {trading ? '⏳ Thinking...' : '⚡ Make Trade'}
  </button>

  <!-- Pending advisory decision -->
  {#if pending}
    <div class="pending-decision">
      <div class="pending-label">⚡ Pending Decision</div>
      <div class="decision-details">
        <span class="d-action" class:buy={pending.action==='buy'} class:sell={pending.action==='sell'}>
          {pending.action.toUpperCase()}
        </span>
        {#if pending.symbol}
          <span>{pending.quantity} {pending.symbol}</span>
        {/if}
      </div>
      <div class="reasoning-text">{pending.reasoning}</div>
      <div class="decision-actions">
        <button class="approve-btn" on:click={() => approveTrade(agent.id)}>Approve</button>
        <button class="reject-btn" on:click={() => rejectTrade(agent.id)}>Reject</button>
      </div>
    </div>
  {/if}

  <!-- AI Thoughts -->
  {#if thought}
    <div class="section">
      <div class="section-label">Latest Thought</div>
      <div class="thought-block">
        <div class="thought-action" class:buy={thought.action==='buy'} class:sell={thought.action==='sell'} class:hold={thought.action==='hold'}>
          {thought.action.toUpperCase()}
          {#if thought.symbol} {thought.quantity} {thought.symbol}{/if}
        </div>
        <div class="thought-reasoning">"{thought.reasoning}"</div>
        <div class="thought-time">{fmtTime(thought.timestamp)}</div>
      </div>
    </div>
  {/if}

  <!-- Recent trades -->
  {#if agentTrades.length > 0}
    <div class="section">
      <div class="section-label">Recent Trades</div>
      <div class="trade-list">
        {#each agentTrades as t}
          <div class="trade-item">
            <span class="t-side" class:buy={t.side==='buy'} class:sell={t.side==='sell'}>{t.side.toUpperCase()}</span>
            <span class="t-sym">{t.symbol}</span>
            <span class="t-qty">{fmt(t.quantity, 4)}</span>
            <span class="t-price">@ ${fmt(t.price)}</span>
            <span class="t-time">{fmtTime(t.timestamp)}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .agent-card {
    background: #0f0f20;
    border: 1px solid #1e1e3a;
    border-radius: 8px;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-width: 340px;
    max-width: 480px;
    width: 100%;
    transition: border-color 0.3s;
  }
  .agent-card.flash {
    border-color: #a080ff;
    box-shadow: 0 0 12px rgba(160, 128, 255, 0.3);
  }
  .agent-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .agent-name {
    font-weight: 700;
    color: #c0b8ff;
    font-size: 1rem;
  }
  .agent-meta { display: flex; gap: 0.4rem; align-items: center; }
  .model-badge {
    background: #1e1e3a;
    color: #888;
    font-size: 0.68rem;
    padding: 2px 6px;
    border-radius: 4px;
    max-width: 160px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mode-btn {
    background: #1e1e3a;
    color: #a080ff;
    border: 1px solid #3a2a6a;
    font-size: 0.68rem;
    padding: 2px 8px;
    border-radius: 4px;
    cursor: pointer;
    text-transform: capitalize;
  }
  .delete-btn { background: transparent; color: #555; border: none; cursor: pointer; font-size: 0.85rem; }
  .delete-btn:hover { color: #ff4d6d; }

  .goal-line {
    font-size: 0.75rem;
    color: #6a5a9a;
    font-style: italic;
    border-left: 2px solid #3a2a6a;
    padding-left: 0.5rem;
  }

  .portfolio-summary { display: flex; gap: 1rem; flex-wrap: wrap; }
  .stat { display: flex; flex-direction: column; }
  .label { font-size: 0.65rem; color: #555; text-transform: uppercase; }
  .value { font-size: 0.9rem; color: #e0e0ff; font-family: monospace; }
  .pos { color: #00d4a0 !important; }
  .neg { color: #ff4d6d !important; }

  .section { display: flex; flex-direction: column; gap: 0.3rem; }
  .section-label { font-size: 0.65rem; color: #444; text-transform: uppercase; letter-spacing: 0.05em; }

  .section-toggle {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: none;
    border: none;
    cursor: pointer;
    width: 100%;
    padding: 0;
    color: inherit;
  }
  .toggle-arrow { font-size: 0.55rem; color: #444; }

  /* Wallet */
  .wallet-body {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    background: #0d0d1a;
    border: 1px solid #1e1e3a;
    border-radius: 6px;
    padding: 0.6rem 0.75rem;
    margin-top: 0.1rem;
  }
  .wallet-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.78rem;
  }
  .w-label { color: #666; }
  .w-value { color: #c0c0d0; font-family: monospace; }
  .w-subtle { color: #555; }
  .w-holdings-header {
    font-size: 0.62rem;
    color: #444;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 0.3rem;
    border-top: 1px solid #1e1e3a;
    padding-top: 0.3rem;
  }
  .deposit-row {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.4rem;
    border-top: 1px solid #1e1e3a;
    padding-top: 0.4rem;
  }
  .deposit-input {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 4px 8px;
    border-radius: 5px;
    font-size: 0.78rem;
    flex: 1;
    outline: none;
    min-width: 0;
  }
  .deposit-input:focus { border-color: #7060d0; }
  .deposit-btn {
    background: #0d2a1a;
    color: #00d4a0;
    border: 1px solid #00d4a0;
    padding: 4px 10px;
    border-radius: 5px;
    font-size: 0.75rem;
    cursor: pointer;
    white-space: nowrap;
    font-weight: 600;
  }
  .deposit-btn:hover:not(:disabled) { background: #0a3a22; }
  .deposit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .deposit-error { font-size: 0.72rem; color: #ff4d6d; }

  .holding-row { display: flex; gap: 0.6rem; font-size: 0.8rem; align-items: center; }
  .h-symbol { color: #888; width: 45px; font-weight: 600; }
  .h-qty { color: #c0c0d0; font-family: monospace; flex: 1; }

  .trade-btn {
    background: #1e1040;
    color: #a080ff;
    border: 1px solid #4a2a9a;
    padding: 0.5rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 600;
    transition: background 0.2s;
  }
  .trade-btn:hover:not(:disabled) { background: #2e1a60; }
  .trade-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .pending-decision {
    background: #1a1030;
    border: 1px solid #5a3a9a;
    border-radius: 6px;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .pending-label { font-size: 0.7rem; color: #a080ff; font-weight: 600; }
  .decision-details { display: flex; gap: 0.5rem; font-size: 0.85rem; align-items: center; }
  .d-action { font-weight: 700; }
  .buy { color: #00d4a0; }
  .sell { color: #ff4d6d; }
  .hold { color: #888; }
  .reasoning-text { font-size: 0.75rem; color: #888; font-style: italic; }
  .decision-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
  .approve-btn, .reject-btn {
    padding: 4px 14px; border-radius: 4px; border: none; cursor: pointer;
    font-size: 0.8rem; font-weight: 600;
  }
  .approve-btn { background: #00d4a0; color: #000; }
  .reject-btn { background: #2a1a2a; color: #ff4d6d; border: 1px solid #ff4d6d; }

  .thought-block {
    background: #0d0d1a;
    border-left: 2px solid #3a2a6a;
    padding: 0.5rem 0.75rem;
    border-radius: 0 4px 4px 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .thought-action { font-size: 0.75rem; font-weight: 700; }
  .thought-reasoning { font-size: 0.78rem; color: #8888aa; font-style: italic; }
  .thought-time { font-size: 0.65rem; color: #444; }

  .trade-list { display: flex; flex-direction: column; gap: 0.2rem; }
  .trade-item {
    display: flex;
    gap: 0.5rem;
    font-size: 0.75rem;
    align-items: center;
  }
  .t-side { font-weight: 700; width: 32px; }
  .t-sym { color: #c0b8ff; width: 38px; font-weight: 600; }
  .t-qty { font-family: monospace; color: #c0c0d0; flex: 1; }
  .t-price { font-family: monospace; color: #888; }
  .t-time { color: #444; font-size: 0.68rem; }
</style>
