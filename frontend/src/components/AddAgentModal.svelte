<script>
  import { createEventDispatcher, onMount } from 'svelte'

  const dispatch = createEventDispatcher()

  let name = ''
  let model = ''
  let mode = 'autonomous'
  let allowance = 10000
  let models = []
  let loading = false
  let error = ''

  onMount(async () => {
    try {
      const res = await fetch('/api/ollama/models')
      if (res.ok) models = await res.json()
      if (models.length > 0) model = models[0]
    } catch {
      models = []
    }
  })

  async function submit() {
    if (!name.trim() || !model) {
      error = 'Name and model are required.'
      return
    }
    loading = true
    error = ''
    try {
      const res = await fetch('/api/agents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, model, mode, allowance }),
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

<div class="overlay" on:click|self={() => dispatch('close')}>
  <div class="modal">
    <div class="modal-header">
      <span>New Agent</span>
      <button class="close-btn" on:click={() => dispatch('close')}>✕</button>
    </div>

    <div class="form">
      <label>
        Agent Name
        <input bind:value={name} placeholder="e.g. Ghost-1" />
      </label>

      <label>
        Ollama Model
        {#if models.length > 0}
          <select bind:value={model}>
            {#each models as m}
              <option value={m}>{m}</option>
            {/each}
          </select>
        {:else}
          <input bind:value={model} placeholder="e.g. llama3" />
        {/if}
      </label>

      <label>
        Mode
        <select bind:value={mode}>
          <option value="autonomous">Autonomous</option>
          <option value="advisory">Advisory</option>
        </select>
      </label>

      <label>
        Starting Allowance ($)
        <input type="number" bind:value={allowance} min="100" step="100" />
      </label>

      {#if error}
        <div class="error">{error}</div>
      {/if}

      <button class="submit-btn" on:click={submit} disabled={loading}>
        {loading ? 'Creating...' : 'Deploy Agent'}
      </button>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
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
    width: 360px;
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
  input, select {
    background: #1a1a30;
    border: 1px solid #2e2e5a;
    color: #e0e0ff;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    font-size: 0.9rem;
    outline: none;
  }
  input:focus, select:focus { border-color: #7060d0; }
  .error { color: #ff4d6d; font-size: 0.8rem; }
  .submit-btn {
    background: #5a3aaa;
    color: #fff;
    border: none;
    padding: 0.6rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    margin-top: 0.25rem;
  }
  .submit-btn:hover { background: #7050c0; }
  .submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
