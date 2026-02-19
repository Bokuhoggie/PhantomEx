<script>
  import { createEventDispatcher } from 'svelte'
  import { ollamaModels, selectedModel, connectionStatus } from '../lib/ollama.js'

  const dispatch = createEventDispatcher()

  let name = ''
  let model = $selectedModel || ''
  let mode = 'autonomous'
  let allowance = 10000
  let goal = ''
  let loading = false
  let error = ''

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
        body: JSON.stringify({ name, model, mode, allowance, goal }),
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
    width: 400px;
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
