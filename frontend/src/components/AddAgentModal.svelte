<script>
  import { createEventDispatcher } from 'svelte'
  import { ollamaModels, selectedModel, connectionStatus } from '../lib/ollama.js'
  import { prices } from '../lib/ws.js'

  const dispatch = createEventDispatcher()

  let name = ''
  let model = $selectedModel || ''
  let mode = 'autonomous'
  let allowance = 10000
  let goal = ''
  let loading = false
  let error = ''

  // Risk profile
  let riskProfile = 'neutral'  // "aggressive" | "neutral" | "safe"

  // Trade frequency (slider in minutes, sent to backend as seconds)
  let tradeIntervalMin = 1

  // Session duration limit (seconds; null = no limit)
  let maxDurationSecs = null
  const DURATION_OPTIONS = [
    { label: 'No limit', value: null },
    { label: '30 min',  value: 30 * 60 },
    { label: '1 hour',  value: 60 * 60 },
    { label: '2 hours', value: 2 * 60 * 60 },
    { label: '4 hours', value: 4 * 60 * 60 },
    { label: '8 hours', value: 8 * 60 * 60 },
  ]

  // Coin search + initial holdings
  const SYMBOLS = ['BTC','ETH','SOL','BNB','XRP','ADA','DOGE','AVAX','DOT','MATIC']
  let coinSearch = ''
  let coinQty = {}
  let initialHoldings = {}

  $: filteredCoins = coinSearch.trim()
    ? SYMBOLS.filter(s => s.toLowerCase().includes(coinSearch.toLowerCase()))
    : SYMBOLS

  function addCoin(symbol) {
    const qty = parseFloat(coinQty[symbol])
    if (!qty || qty <= 0) return
    initialHoldings = { ...initialHoldings, [symbol]: qty }
    coinQty = { ...coinQty, [symbol]: '' }
  }

  function removeCoin(symbol) {
    const { [symbol]: _, ...rest } = initialHoldings
    initialHoldings = rest
  }

  // Sync model with selectedModel store
  $: if ($selectedModel && !model) model = $selectedModel

  async function submit() {
    if (!name.trim()) { error = 'Agent name is required.'; return }
    if (!model) { error = 'Select a model first — connect to Ollama above.'; return }
    loading = true
    error = ''
    try {
      const res = await fetch('/api/agents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          model,
          mode,
          allowance,
          goal,
          trade_interval: tradeIntervalMin * 60,
          risk_profile: riskProfile,
          max_duration: maxDurationSecs,
          initial_holdings: initialHoldings,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      dispatch('close')
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }
</script>

<div class="overlay" on:click|self={() => dispatch('close')} role="dialog" aria-modal="true">
  <div class="modal">
    <div class="modal-header">
      <span>Deploy Agent</span>
      <button class="close-btn" on:click={() => dispatch('close')}>✕</button>
    </div>

    <div class="form">
      <label>
        Agent Name
        <input bind:value={name} placeholder="e.g. Ghost-1" />
      </label>

      <label>
        Model
        {#if $ollamaModels.length > 0}
          <select bind:value={model}>
            {#each $ollamaModels as m}
              <option value={m}>{m}</option>
            {/each}
          </select>
        {:else}
          <div class="no-models">
            {$connectionStatus === 'connecting' ? 'Connecting to Ollama...' : 'No models found — connect Ollama first'}
          </div>
        {/if}
      </label>

      <label>
        Trading Goal
        <textarea
          bind:value={goal}
          placeholder="e.g. Maximize BTC holdings long-term. Avoid memecoins. Be patient."
          rows="3"
        />
      </label>

      <div class="row">
        <label>
          Mode
          <select bind:value={mode}>
            <option value="autonomous">Autonomous</option>
            <option value="advisory">Advisory</option>
          </select>
        </label>
        <label>
          Allowance ($)
          <input type="number" bind:value={allowance} min="100" step="100" />
        </label>
      </div>

      <!-- Risk Profile -->
      <div class="risk-section">
        <div class="risk-label">Risk Profile</div>
        <div class="risk-toggle">
          <button
            type="button"
            class="risk-btn aggressive"
            class:active={riskProfile === 'aggressive'}
            on:click={() => riskProfile = 'aggressive'}
          >🔴 Aggressive</button>
          <button
            type="button"
            class="risk-btn neutral"
            class:active={riskProfile === 'neutral'}
            on:click={() => riskProfile = 'neutral'}
          >⚪ Neutral</button>
          <button
            type="button"
            class="risk-btn safe"
            class:active={riskProfile === 'safe'}
            on:click={() => riskProfile = 'safe'}
          >🟢 Safe</button>
        </div>
      </div>

      <!-- Trade Frequency + Stop After (same row) -->
      <div class="row">
        <div class="freq-section">
          <label>
            Trade Frequency
            <div class="freq-row">
              <input
                type="range"
                min="1"
                max="60"
                step="1"
                bind:value={tradeIntervalMin}
                class="freq-slider"
              />
              <span class="freq-label">
                {tradeIntervalMin === 1 ? 'every 1m' : `every ${tradeIntervalMin}m`}
              </span>
            </div>
          </label>
        </div>
        <label>
          Stop After
          <select bind:value={maxDurationSecs}>
            {#each DURATION_OPTIONS as opt}
              <option value={opt.value}>{opt.label}</option>
            {/each}
          </select>
        </label>
      </div>

      <!-- Starting Holdings -->
      <div class="holdings-section">
        <div class="holdings-header">
          Starting Holdings <span class="optional">(optional)</span>
        </div>
        <input
          class="coin-search"
          placeholder="Search coins..."
          bind:value={coinSearch}
        />
        <div class="coin-list">
          {#each filteredCoins as symbol}
            {@const price = $prices[symbol]?.price}
            <div class="coin-row">
              <span class="coin-sym">{symbol}</span>
              <span class="coin-price">
                {#if price}${price.toLocaleString(undefined, {maximumFractionDigits: 2})}{:else}—{/if}
              </span>
              <input
                class="qty-input"
                type="number"
                min="0"
                step="any"
                placeholder="qty"
                bind:value={coinQty[symbol]}
                on:keydown={e => e.key === 'Enter' && addCoin(symbol)}
              />
              <button
                class="add-coin-btn"
                on:click={() => addCoin(symbol)}
                disabled={!coinQty[symbol] || parseFloat(coinQty[symbol]) <= 0}
              >+ Add</button>
            </div>
          {/each}
        </div>

        {#if Object.keys(initialHoldings).length > 0}
          <div class="holdings-chips">
            {#each Object.entries(initialHoldings) as [symbol, qty]}
              <span class="holding-chip">
                {symbol} × {qty}
                <button class="chip-remove" on:click={() => removeCoin(symbol)}>✕</button>
              </span>
            {/each}
          </div>
        {/if}
      </div>

      {#if error}
        <div class="error">{error}</div>
      {/if}

      <button class="submit-btn" on:click={submit} disabled={loading || $ollamaModels.length === 0}>
        {loading ? 'Deploying...' : '⚡ Deploy Agent'}
      </button>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.75);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }
  .modal {
    background: #0f0f20;
    border: 1px solid #2e2e5a;
    border-radius: 10px;
    padding: 1.5rem;
    width: 500px;
    max-height: 92vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 700;
    color: #c0b8ff;
    font-size: 1rem;
  }
  .close-btn {
    background: none;
    border: none;
    color: #555;
    cursor: pointer;
    font-size: 1rem;
  }
  .form {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: 0.78rem;
    color: #888;
    text-transform: uppercase;
  }
  .row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }
  input, select, textarea {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    font-size: 0.9rem;
    outline: none;
    font-family: inherit;
    resize: vertical;
  }
  input:focus, select:focus, textarea:focus { border-color: #7060d0; }
  .no-models {
    background: #1a1a30;
    border: 1px dashed #2e2e5a;
    color: #555;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    font-size: 0.82rem;
    text-transform: none;
  }

  /* Risk Profile */
  .risk-section { display: flex; flex-direction: column; gap: 0.4rem; }
  .risk-label {
    font-size: 0.78rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .risk-toggle {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 0.4rem;
  }
  .risk-btn {
    padding: 0.45rem 0.5rem;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid #2e2e5a;
    background: #1a1a30;
    color: #555;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
    text-align: center;
    white-space: nowrap;
  }
  .risk-btn:hover { border-color: #5a4a9a; color: #aaa; }
  .risk-btn.aggressive.active  { background: #2a1010; border-color: #ff6a4d; color: #ff6a4d; }
  .risk-btn.neutral.active     { background: #1e1e38; border-color: #7060d0; color: #a080ff; }
  .risk-btn.safe.active        { background: #0a2018; border-color: #00d4a0; color: #00d4a0; }

  /* Trade Frequency */
  .freq-section { display: flex; flex-direction: column; }
  .freq-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-top: 0.3rem;
  }
  .freq-slider {
    flex: 1;
    accent-color: #7060d0;
    cursor: pointer;
    padding: 0;
    border: none;
    background: transparent;
  }
  .freq-label {
    color: #a080ff;
    font-size: 0.8rem;
    white-space: nowrap;
    min-width: 100px;
    text-transform: none;
    font-weight: 500;
  }

  /* Starting Holdings */
  .holdings-section {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .holdings-header {
    font-size: 0.78rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .optional {
    font-size: 0.62rem;
    color: #444;
    font-weight: 400;
    text-transform: none;
  }
  .coin-search {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 0.4rem 0.65rem;
    border-radius: 6px;
    font-size: 0.85rem;
    outline: none;
    resize: none;
  }
  .coin-search:focus { border-color: #7060d0; }
  .coin-list {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    max-height: 160px;
    overflow-y: auto;
    border: 1px solid #2e2e5a;
    border-radius: 6px;
    padding: 0.35rem;
    background: #0d0d1a;
  }
  .coin-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.2rem 0.3rem;
    border-radius: 4px;
  }
  .coin-row:hover { background: #1a1a30; }
  .coin-sym {
    font-weight: 700;
    color: #c0b8ff;
    width: 44px;
    font-size: 0.82rem;
  }
  .coin-price {
    color: #555;
    font-family: monospace;
    font-size: 0.75rem;
    flex: 1;
  }
  .qty-input {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 3px 6px;
    border-radius: 4px;
    font-size: 0.78rem;
    width: 72px;
    outline: none;
    resize: none;
  }
  .qty-input:focus { border-color: #7060d0; }
  .add-coin-btn {
    background: #1a2a1a;
    color: #00d4a0;
    border: 1px solid #00d4a0;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .add-coin-btn:disabled { opacity: 0.3; cursor: not-allowed; }
  .add-coin-btn:hover:not(:disabled) { background: #0a2a1a; }

  .holdings-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .holding-chip {
    background: #1e1e3a;
    border: 1px solid #3a2a6a;
    color: #a080ff;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .chip-remove {
    background: none;
    border: none;
    color: #555;
    cursor: pointer;
    font-size: 0.7rem;
    padding: 0;
    line-height: 1;
  }
  .chip-remove:hover { color: #ff4d6d; }

  .error { color: #ff4d6d; font-size: 0.8rem; }
  .submit-btn {
    background: #5a3aaa;
    color: #fff;
    border: none;
    padding: 0.65rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    margin-top: 0.25rem;
  }
  .submit-btn:hover:not(:disabled) { background: #7050c0; }
  .submit-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
