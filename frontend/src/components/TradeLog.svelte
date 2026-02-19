<script>
  import { trades, agents } from '../lib/ws.js'

  $: agentMap = $agents

  function agentName(id) {
    return agentMap[id]?.name || id.slice(0, 8)
  }

  function fmt(n, decimals = 2) {
    return Number(n).toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
  }

  function fmtTime(ts) {
    if (!ts) return ''
    return new Date(ts).toLocaleTimeString()
  }
</script>

<div class="trade-log">
  <div class="log-header">Trade Log</div>
  <div class="log-table">
    <div class="log-row header-row">
      <span>Time</span>
      <span>Agent</span>
      <span>Side</span>
      <span>Symbol</span>
      <span>Qty</span>
      <span>Price</span>
      <span>Total</span>
    </div>
    {#each $trades as trade (trade.timestamp + trade.agent_id)}
      <div class="log-row">
        <span class="time">{fmtTime(trade.timestamp)}</span>
        <span class="agent">{agentName(trade.agent_id)}</span>
        <span class="side" class:buy={trade.side === 'buy'} class:sell={trade.side === 'sell'}>
          {trade.side.toUpperCase()}
        </span>
        <span class="symbol">{trade.symbol}</span>
        <span class="mono">{fmt(trade.quantity, 6)}</span>
        <span class="mono">${fmt(trade.price)}</span>
        <span class="mono">${fmt(trade.total)}</span>
      </div>
    {:else}
      <div class="empty">No trades yet.</div>
    {/each}
  </div>
</div>

<style>
  .trade-log {
    background: #0f0f20;
    border: 1px solid #1e1e3a;
    border-radius: 8px;
    overflow: hidden;
  }
  .log-header {
    padding: 0.6rem 1rem;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    color: #555;
    border-bottom: 1px solid #1e1e3a;
  }
  .log-table { overflow-y: auto; max-height: 320px; }
  .log-row {
    display: grid;
    grid-template-columns: 70px 90px 50px 60px 110px 100px 100px;
    gap: 0.5rem;
    padding: 0.4rem 1rem;
    font-size: 0.78rem;
    align-items: center;
    border-bottom: 1px solid #0d0d1a;
  }
  .header-row {
    color: #444;
    font-size: 0.7rem;
    text-transform: uppercase;
    position: sticky;
    top: 0;
    background: #0f0f20;
  }
  .time { color: #555; }
  .agent { color: #888; }
  .buy { color: #00d4a0; font-weight: 700; }
  .sell { color: #ff4d6d; font-weight: 700; }
  .symbol { color: #c0b8ff; font-weight: 600; }
  .mono { font-family: monospace; color: #c0c0d0; }
  .empty { padding: 1.5rem; color: #333; text-align: center; font-size: 0.85rem; }
</style>
