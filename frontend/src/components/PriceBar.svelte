<script>
  import { prices } from '../lib/ws.js'
</script>

<div class="price-bar">
  {#each Object.entries($prices) as [symbol, data]}
    <span class="ticker">
      <span class="symbol">{symbol}</span>
      <span class="price">${data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
      <span class="change" class:up={data.change_24h >= 0} class:down={data.change_24h < 0}>
        {data.change_24h >= 0 ? '▲' : '▼'}{Math.abs(data.change_24h).toFixed(2)}%
      </span>
    </span>
  {/each}
</div>

<style>
  .price-bar {
    display: flex;
    gap: 1.5rem;
    overflow-x: auto;
    padding: 0.5rem 1rem;
    background: #0d0d1a;
    border-bottom: 1px solid #1e1e3a;
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .ticker {
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .symbol {
    color: #888;
    font-weight: 600;
  }
  .price {
    color: #e0e0ff;
    font-family: monospace;
  }
  .up { color: #00d4a0; }
  .down { color: #ff4d6d; }
</style>
