<script>
  /**
   * DashboardStats — aggregate KPI bar across all agents.
   * Shows: total portfolio value, combined P&L, trade count, active agents, best performer.
   */
  import { agents, trades } from '../lib/ws.js'

  function fmt(n, d = 2) {
    return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
  }

  $: agentList = Object.values($agents)

  $: totalValue = agentList.reduce((s, a) => s + (a.portfolio?.total_value ?? 0), 0)
  $: totalAllowance = agentList.reduce((s, a) => s + (a.allowance ?? 0), 0)
  $: totalPnl = totalValue - totalAllowance
  $: totalPnlPct = totalAllowance > 0 ? (totalPnl / totalAllowance) * 100 : 0

  $: tradeCount = $trades.length

  $: buyCount = $trades.filter(t => t.side === 'buy').length
  $: sellCount = $trades.filter(t => t.side === 'sell').length

  // Best performing agent
  $: bestAgent = agentList.reduce((best, a) => {
    const pnl = (a.portfolio?.total_value ?? 0) - (a.allowance ?? 0)
    const bestPnl = (best?.portfolio?.total_value ?? 0) - (best?.allowance ?? 0)
    return pnl > bestPnl ? a : best
  }, agentList[0] ?? null)

  $: bestPnl = bestAgent ? (bestAgent.portfolio?.total_value ?? 0) - (bestAgent.allowance ?? 0) : 0
  $: bestPnlPct = bestAgent?.allowance > 0 ? (bestPnl / bestAgent.allowance) * 100 : 0
</script>

<div class="stats-bar">
  <div class="stat-block">
    <span class="stat-label">Portfolio Value</span>
    <span class="stat-value">${fmt(totalValue)}</span>
  </div>

  <div class="stat-divider"></div>

  <div class="stat-block">
    <span class="stat-label">Total P&L</span>
    <span class="stat-value" class:pos={totalPnl >= 0} class:neg={totalPnl < 0}>
      {totalPnl >= 0 ? '+' : ''}{fmt(totalPnl)}
      <span class="stat-sub">({totalPnlPct >= 0 ? '+' : ''}{fmt(totalPnlPct)}%)</span>
    </span>
  </div>

  <div class="stat-divider"></div>

  <div class="stat-block">
    <span class="stat-label">Trades</span>
    <span class="stat-value">
      {tradeCount}
      <span class="stat-sub trade-counts">
        <span class="buy-ct">▲{buyCount}</span>
        <span class="sell-ct">▼{sellCount}</span>
      </span>
    </span>
  </div>

  <div class="stat-divider"></div>

  <div class="stat-block">
    <span class="stat-label">Agents</span>
    <span class="stat-value">{agentList.length}</span>
  </div>

  {#if bestAgent && agentList.length > 1}
    <div class="stat-divider"></div>
    <div class="stat-block">
      <span class="stat-label">Best Agent</span>
      <span class="stat-value best-agent">
        {bestAgent.name}
        <span class="stat-sub" class:pos={bestPnl >= 0} class:neg={bestPnl < 0}>
          {bestPnlPct >= 0 ? '+' : ''}{fmt(bestPnlPct)}%
        </span>
      </span>
    </div>
  {/if}
</div>

<style>
  .stats-bar {
    display: flex;
    align-items: center;
    gap: 0;
    background: #0a0a18;
    border-bottom: 1px solid #1e1e3a;
    padding: 0.6rem 1.5rem;
    overflow-x: auto;
    flex-wrap: nowrap;
  }

  .stat-divider {
    width: 1px;
    height: 28px;
    background: #1e1e3a;
    flex-shrink: 0;
    margin: 0 1.25rem;
  }

  .stat-block {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    flex-shrink: 0;
  }

  .stat-label {
    font-size: 0.62rem;
    color: #444;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    white-space: nowrap;
  }

  .stat-value {
    font-size: 0.95rem;
    font-weight: 700;
    color: #e0e0ff;
    font-family: monospace;
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
    white-space: nowrap;
  }

  .stat-sub {
    font-size: 0.68rem;
    color: #666;
    font-weight: 400;
  }

  .pos { color: #00d4a0 !important; }
  .neg { color: #ff4d6d !important; }

  .trade-counts {
    display: flex;
    gap: 0.4rem;
    font-size: 0.68rem;
  }
  .buy-ct { color: #00d4a0; }
  .sell-ct { color: #ff4d6d; }

  .best-agent {
    color: #c0b8ff !important;
    font-size: 0.85rem;
  }
</style>
