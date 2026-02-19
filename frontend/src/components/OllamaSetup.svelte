<script>
  import { onMount } from 'svelte'
  import {
    ollamaHost,
    ollamaModels,
    selectedModel,
    connectionStatus,
    connectionError,
    fetchModels,
  } from '../lib/ollama.js'

  let hostInput = $ollamaHost

  async function connect() {
    ollamaHost.set(hostInput)
    await fetchModels(hostInput)
  }

  onMount(() => {
    if ($connectionStatus === 'idle') connect()
  })
</script>

<div class="ollama-setup">
  <span class="label">Ollama</span>

  <div class="setup-row">
    <input
      class="host-input"
      bind:value={hostInput}
      placeholder="http://localhost:11434"
      on:keydown={e => e.key === 'Enter' && connect()}
    />
    <button class="connect-btn" on:click={connect} disabled={$connectionStatus === 'connecting'}>
      {$connectionStatus === 'connecting' ? 'Connecting...' : 'Connect'}
    </button>

    <span class="status-dot" class:connected={$connectionStatus === 'connected'} class:error={$connectionStatus === 'error'}>
      {#if $connectionStatus === 'connected'}● {$ollamaModels.length} model{$ollamaModels.length !== 1 ? 's' : ''} available{/if}
      {#if $connectionStatus === 'error'}✕ {$connectionError}{/if}
      {#if $connectionStatus === 'connecting'}○ Connecting...{/if}
      {#if $connectionStatus === 'idle'}○ Not connected{/if}
    </span>

    {#if $ollamaModels.length > 0}
      <div class="model-section">
        <span class="label">Default Model</span>
        <select bind:value={$selectedModel} class="model-select">
          {#each $ollamaModels as m}
            <option value={m}>{m}</option>
          {/each}
        </select>
      </div>
    {/if}
  </div>
</div>

<style>
  .ollama-setup {
    display: flex;
    align-items: center;
    gap: 1rem;
    width: 100%;
  }
  .label {
    font-size: 0.72rem;
    color: #555;
    text-transform: uppercase;
    white-space: nowrap;
    letter-spacing: 0.05em;
    flex-shrink: 0;
  }
  .setup-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex: 1;
    flex-wrap: wrap;
  }
  .host-input {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 5px 10px;
    border-radius: 5px;
    font-size: 0.82rem;
    width: 280px;
    outline: none;
  }
  .host-input:focus { border-color: #7060d0; }
  .connect-btn {
    background: #2a1a4a;
    color: #a080ff;
    border: 1px solid #4a2a8a;
    padding: 5px 16px;
    border-radius: 5px;
    font-size: 0.82rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .connect-btn:hover:not(:disabled) { background: #3a2a6a; }
  .connect-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .status-dot {
    font-size: 0.78rem;
    color: #444;
    white-space: nowrap;
  }
  .status-dot.connected { color: #00d4a0; }
  .status-dot.error { color: #ff4d6d; }

  .model-section {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-left: auto;
  }
  .model-select {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 5px 10px;
    border-radius: 5px;
    font-size: 0.82rem;
    outline: none;
    min-width: 200px;
  }
</style>
