<script>
  import { approveTrade, rejectTrade, pendingDecisions } from '../lib/ws.js'

  export let agent

  $: portfolio = agent.portfolio || {}
  $: holdings = portfolio.holdings || {}
  $: pnl = portfolio.unrealized_pnl || {}
  $: pending = $pendingDecisions[agent.id]

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
</script>

<div class="agent-card">
  <div class="agent-header">
    <div class="agent-name">{agent.name}</div>
    <div class="agent-meta">
      <span class="model-badge">{agent.model}</span>
      <button class="mode-btn" on:click={toggleMode}>{agent.mode}</button>
      <button class="delete-btn" on:click={deleteAgent}>✕</button>
    </div>
  </div>

  <div class="portfolio-summary">
    <div class="stat">
      <span class="label">Cash</span>
      <span class="value">${(portfolio.cash || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
    </div>
    <div class="stat">
      <span class="label">Total Value</span>
      <span class="value">${(portfolio.total_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
    </div>
  </div>

  {#if Object.keys(holdings).length > 0}
    <div class="holdings">
      <div class="section-label">Holdings</div>
      {#each Object.entries(holdings) as [symbol, h]}
        {@const p = pnl[symbol] || {}}
        <div class="holding-row">
          <span class="h-symbol">{symbol}</span>
          <span class="h-qty">{h.quantity.toFixed(6)}</span>
          <span class="h-pnl" class:pos={p.unrealized >= 0} class:neg={p.unrealized < 0}>
            {p.unrealized >= 0 ? '+' : ''}{(p.unrealized || 0).toFixed(2)} ({(p.pct || 0).toFixed(2)}%)
          </span>
        </div>
      {/each}
    </div>
  {/if}

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
      <div class="reasoning">{pending.reasoning}</div>
      <div class="decision-actions">
        <button class="approve-btn" on:click={() => approveTrade(agent.id)}>Approve</button>
        <button class="reject-btn" on:click={() => rejectTrade(agent.id)}>Reject</button>
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
    min-width: 280px;
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
  .agent-meta {
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .model-badge {
    background: #1e1e3a;
    color: #888;
    font-size: 0.7rem;
    padding: 2px 6px;
    border-radius: 4px;
  }
  .mode-btn {
    background: #1e1e3a;
    color: #a080ff;
    border: 1px solid #3a2a6a;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 4px;
    cursor: pointer;
    text-transform: capitalize;
  }
  .delete-btn {
    background: transparent;
    color: #555;
    border: none;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .delete-btn:hover { color: #ff4d6d; }
  .portfolio-summary {
    display: flex;
    gap: 1.5rem;
  }
  .stat { display: flex; flex-direction: column; }
  .label { font-size: 0.68rem; color: #555; text-transform: uppercase; }
  .value { font-size: 0.95rem; color: #e0e0ff; font-family: monospace; }
  .section-label { font-size: 0.7rem; color: #555; text-transform: uppercase; margin-bottom: 0.25rem; }
  .holding-row {
    display: flex;
    gap: 0.75rem;
    font-size: 0.82rem;
    align-items: center;
  }
  .h-symbol { color: #888; width: 40px; font-weight: 600; }
  .h-qty { color: #e0e0ff; font-family: monospace; }
  .pos { color: #00d4a0; }
  .neg { color: #ff4d6d; }
  .pending-decision {
    background: #1a1030;
    border: 1px solid #5a3a9a;
    border-radius: 6px;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .pending-label { font-size: 0.72rem; color: #a080ff; font-weight: 600; }
  .decision-details { display: flex; gap: 0.5rem; font-size: 0.85rem; align-items: center; }
  .d-action { font-weight: 700; }
  .buy { color: #00d4a0; }
  .sell { color: #ff4d6d; }
  .reasoning { font-size: 0.75rem; color: #888; font-style: italic; }
  .decision-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
  .approve-btn, .reject-btn {
    padding: 4px 14px;
    border-radius: 4px;
    border: none;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
  }
  .approve-btn { background: #00d4a0; color: #000; }
  .reject-btn { background: #2a1a2a; color: #ff4d6d; border: 1px solid #ff4d6d; }
</style>
