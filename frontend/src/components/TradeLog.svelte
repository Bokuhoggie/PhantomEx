<script>
  import { trades, agents, wipeTradeLog } from '../lib/ws.js'

  $: agentMap = $agents
  $: agentList = Object.values($agents)

  let filterAgent = 'all'
  let filterSide  = 'all'
  let showReasoning = false

  $: filtered = $trades
    .filter(t => {
      if (filterAgent !== 'all' && t.agent_id !== filterAgent) return false
      if (filterSide  !== 'all' && t.side    !== filterSide)   return false
      return true
    })
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))

  $: buyCount  = filtered.filter(t => t.side === 'buy').length
  $: sellCount = filtered.filter(t => t.side === 'sell').length
  $: totalVolume = filtered.reduce((s, t) => s + (t.total || 0), 0)

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
    const d = new Date(ts)
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
      + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  function confirmWipe() {
    if (confirm('Clear the trade log display? Trades before this point will be hidden even after page refresh. (Trades remain in the database.)')) {
      wipeTradeLog()
    }
  }
</script>

<div class="trade-log">

  <!-- Header + Controls -->
  <div class="log-header">
    <div class="log-title">
      <span>Trade Log</span>
      <span class="log-count">{filtered.length}</span>
      {#if filtered.length > 0}
        <span class="log-stats">
          <span class="buy-ct">▲{buyCount}</span>
          <span class="sell-ct">▼{sellCount}</span>
          <span class="vol">vol ${(totalVolume / 1000).toFixed(1)}k</span>
        </span>
      {/if}
    </div>

    <div class="log-controls">
      <!-- Agent filter -->
      <select bind:value={filterAgent} class="ctrl-select">
        <option value="all">All agents</option>
        {#each agentList as a}
          <option value={a.id}>{a.name}</option>
        {/each}
      </select>

      <!-- Side filter -->
      <select bind:value={filterSide} class="ctrl-select">
        <option value="all">All sides</option>
        <option value="buy">Buys</option>
        <option value="sell">Sells</option>
        <option value="hold">Holds</option>
      </select>

      <!-- Toggle reasoning -->
      <button class="ctrl-btn" class:active={showReasoning} on:click={() => showReasoning = !showReasoning}
        title="Show AI reasoning">
        💬
      </button>

      <!-- Wipe -->
      <button class="ctrl-btn wipe" on:click={confirmWipe} title="Clear display">
        🗑 Wipe
      </button>
    </div>
  </div>

  <!-- Table -->
  <div class="log-table">
    <div class="log-row header-row">
      <span>Time</span>
      <span>Agent</span>
      <span>Side</span>
      <span>Symbol</span>
      <span>Qty</span>
      <span>Price</span>
      <span>Total</span>
      {#if showReasoning}<span class="reason-col">Reasoning</span>{/if}
    </div>

    {#each filtered as trade (trade.timestamp + trade.agent_id + trade.symbol)}
      <div class="log-row"
        class:buy-row={trade.side === 'buy'}
        class:sell-row={trade.side === 'sell'}
        class:hold-row={trade.side === 'hold'}
      >
        <span class="col-time">{fmtTime(trade.timestamp)}</span>
        <span class="col-agent">{agentName(trade.agent_id)}</span>
        <span class="col-side"
          class:buy={trade.side === 'buy'}
          class:sell={trade.side === 'sell'}
          class:hold={trade.side === 'hold'}
        >
          {trade.side.toUpperCase()}
        </span>
        <span class="col-symbol">{trade.side !== 'hold' ? trade.symbol : '—'}</span>
        <span class="col-mono">{trade.side !== 'hold' ? fmt(trade.quantity, 6) : '—'}</span>
        <span class="col-mono">{trade.side !== 'hold' ? '$' + fmt(trade.price) : '—'}</span>
        <span class="col-mono">{trade.side !== 'hold' ? '$' + fmt(trade.total) : '—'}</span>
        {#if showReasoning}
          <span class="reason-col col-reason">{trade.reasoning || '—'}</span>
        {/if}
      </div>
    {:else}
      <div class="empty">
        {$trades.length === 0 ? 'No trades yet.' : 'No trades match the current filter.'}
      </div>
    {/each}
  </div>

</div>

<style>
  .trade-log {
    background: #0c0c1e;
    border: 1px solid #1e1e3a;
    border-radius: 8px;
    overflow: hidden;
  }

  /* Header */
  .log-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid #1a1a2e;
    flex-wrap: wrap;
    gap: 0.5rem;
    background: #0a0a1a;
  }
  .log-title {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #555;
    letter-spacing: 0.06em;
  }
  .log-count {
    background: #1e1e3a;
    color: #888;
    font-size: 0.68rem;
    padding: 1px 7px;
    border-radius: 8px;
  }
  .log-stats {
    display: flex;
    gap: 0.5rem;
    font-size: 0.68rem;
    font-weight: 400;
    text-transform: none;
  }
  .buy-ct  { color: #00d4a0; }
  .sell-ct { color: #ff4d6d; }
  .vol     { color: #555; }

  .log-controls {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
  }
  .ctrl-select {
    background: #12122a;
    border: 1px solid #2a2a4a;
    color: #888;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    outline: none;
    cursor: pointer;
  }
  .ctrl-select:focus { border-color: #5a4a9a; }
  .ctrl-btn {
    background: #12122a;
    border: 1px solid #2a2a4a;
    color: #666;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 0.72rem;
    cursor: pointer;
    white-space: nowrap;
    transition: border-color 0.15s, color 0.15s;
  }
  .ctrl-btn:hover  { border-color: #5a4a9a; color: #a080ff; }
  .ctrl-btn.active { border-color: #5a4a9a; color: #a080ff; background: #1e1a3a; }
  .ctrl-btn.wipe:hover { border-color: #ff4d6d; color: #ff4d6d; }

  /* Table */
  .log-table { overflow-y: auto; max-height: 380px; }
  .log-row {
    display: grid;
    grid-template-columns: 120px 80px 42px 52px 100px 90px 90px;
    gap: 0.4rem;
    padding: 0.35rem 1rem;
    font-size: 0.75rem;
    align-items: center;
    border-bottom: 1px solid #0a0a18;
    transition: background 0.1s;
  }
  .log-row:hover { background: #0f0f22; }
  .log-row.buy-row  { border-left: 2px solid rgba(0, 212, 160, 0.2); }
  .log-row.sell-row { border-left: 2px solid rgba(255, 77, 109, 0.2); }
  .log-row.hold-row { border-left: 2px solid rgba(80, 80, 100, 0.15); opacity: 0.5; }

  .header-row {
    color: #3a3a5a;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    position: sticky;
    top: 0;
    background: #0a0a18;
    padding: 0.3rem 1rem;
    border-bottom: 1px solid #1a1a2e;
    cursor: default;
  }
  .header-row:hover { background: #0a0a18; }

  /* Columns */
  .col-time   { color: #444; font-size: 0.7rem; }
  .col-agent  { color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .col-side   { font-weight: 700; }
  .buy        { color: #00d4a0; }
  .sell       { color: #ff4d6d; }
  .hold       { color: #444; font-style: italic; }
  .col-symbol { color: #a090d0; font-weight: 600; }
  .col-mono   { font-family: monospace; color: #c0c0d0; }
  .col-reason { font-size: 0.68rem; color: #555; font-style: italic; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* Reasoning column (wide) */
  :global(.log-row.header-row),
  :global(.log-row) {
    grid-template-columns: 120px 80px 42px 52px 100px 90px 90px;
  }
  .reason-col { /* expanded inline when reasoning is on */ }

  .empty {
    padding: 2rem;
    color: #333;
    text-align: center;
    font-size: 0.82rem;
    font-style: italic;
  }
</style>
