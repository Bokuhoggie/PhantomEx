<script>
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

  // Auto-connect on mount
  import { onMount } from 'svelte'
  onMount(() => {
    if ($connectionStatus === 'idle') connect()
  })
</script>

<div class="ollama-setup">
  <div class="setup-left">
    <span class="label">Ollama</span>
    <input
      class="host-input"
      bind:value={hostInput}
      placeholder="http://localhost:11434"
      on:keydown={e => e.key === 'Enter' && connect()}
    />
    <button class="connect-btn" on:click={connect} disabled={$connectionStatus === 'connecting'}>
      {$connectionStatus === 'connecting' ? '...' : 'Connect'}
    </button>
    <span class="status-dot" class:connected={$connectionStatus === 'connected'} class:error={$connectionStatus === 'error'}>
      {#if $connectionStatus === 'connected'}● {$ollamaModels.length} models{/if}
      {#if $connectionStatus === 'error'}✕ Error{/if}
      {#if $connectionStatus === 'connecting'}○ Connecting{/if}
      {#if $connectionStatus === 'idle'}○ Not connected{/if}
    </span>
  </div>

  {#if $ollamaModels.length > 0}
    <div class="setup-right">
      <span class="label">Model</span>
      <select bind:value={$selectedModel} class="model-select">
        {#each $ollamaModels as m}
          <option value={m}>{m}</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if $connectionError}
    <span class="error-msg">{$connectionError}</span>
  {/if}
</div>

<style>
  .ollama-setup {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .setup-left, .setup-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .label {
    font-size: 0.72rem;
    color: #555;
    text-transform: uppercase;
    white-space: nowrap;
  }
  .host-input {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 4px 8px;
    border-radius: 5px;
    font-size: 0.78rem;
    width: 180px;
    outline: none;
  }
  .host-input:focus { border-color: #7060d0; }
  .connect-btn {
    background: #2a1a4a;
    color: #a080ff;
    border: 1px solid #4a2a8a;
    padding: 4px 12px;
    border-radius: 5px;
    font-size: 0.75rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .connect-btn:hover:not(:disabled) { background: #3a2a6a; }
  .connect-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .status-dot {
    font-size: 0.72rem;
    color: #444;
    white-space: nowrap;
  }
  .status-dot.connected { color: #00d4a0; }
  .status-dot.error { color: #ff4d6d; }
  .model-select {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 4px 8px;
    border-radius: 5px;
    font-size: 0.78rem;
    outline: none;
    max-width: 160px;
  }
  .error-msg {
    font-size: 0.72rem;
    color: #ff4d6d;
  }
</style>
