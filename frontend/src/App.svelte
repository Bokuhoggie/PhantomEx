<script>
  import { connected, agents, prices } from './lib/ws.js'
  import PriceBar from './components/PriceBar.svelte'
  import AgentCard from './components/AgentCard.svelte'
  import TradeLog from './components/TradeLog.svelte'
  import AddAgentModal from './components/AddAgentModal.svelte'

  let showAddAgent = false
</script>

<div class="app">
  <!-- Header -->
  <header>
    <div class="logo">
      <span class="phantom">Phantom</span><span class="ex">Ex</span>
    </div>
    <div class="header-right">
      <span class="ws-status" class:connected={$connected}>
        {$connected ? '● LIVE' : '○ CONNECTING'}
      </span>
      <button class="add-agent-btn" on:click={() => showAddAgent = true}>
        + Deploy Agent
      </button>
    </div>
  </header>

  <!-- Live price ticker -->
  <PriceBar />

  <!-- Main content -->
  <main>
    <!-- Agents section -->
    <section class="agents-section">
      <div class="section-header">
        <h2>Active Agents</h2>
        <span class="agent-count">{Object.keys($agents).length}</span>
      </div>

      {#if Object.keys($agents).length === 0}
        <div class="empty-agents">
          <p>No agents deployed yet.</p>
          <button on:click={() => showAddAgent = true}>Deploy your first agent →</button>
        </div>
      {:else}
        <div class="agents-grid">
          {#each Object.values($agents) as agent (agent.id)}
            <AgentCard {agent} />
          {/each}
        </div>
      {/if}
    </section>

    <!-- Trade log -->
    <section class="tradelog-section">
      <div class="section-header">
        <h2>Trade Log</h2>
      </div>
      <TradeLog />
    </section>
  </main>
</div>

{#if showAddAgent}
  <AddAgentModal on:close={() => showAddAgent = false} />
{/if}

<style>
  :global(*) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  :global(body) {
    background: #080810;
    color: #e0e0ff;
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
  }

  .app {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1.5rem;
    background: #0a0a18;
    border-bottom: 1px solid #1e1e3a;
  }

  .logo {
    font-size: 1.3rem;
    font-weight: 800;
    letter-spacing: -0.5px;
  }
  .phantom { color: #a080ff; }
  .ex { color: #00d4a0; }

  .header-right {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .ws-status {
    font-size: 0.72rem;
    font-weight: 600;
    color: #ff4d6d;
    letter-spacing: 0.05em;
  }
  .ws-status.connected { color: #00d4a0; }

  .add-agent-btn {
    background: #3a2070;
    color: #c0b8ff;
    border: 1px solid #5a3aaa;
    padding: 0.4rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.82rem;
    font-weight: 600;
  }
  .add-agent-btn:hover { background: #5a3aaa; }

  main {
    flex: 1;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 2rem;
    max-width: 1400px;
    margin: 0 auto;
    width: 100%;
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  h2 {
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    color: #555;
    letter-spacing: 0.08em;
  }
  .agent-count {
    background: #1e1e3a;
    color: #888;
    font-size: 0.72rem;
    padding: 1px 8px;
    border-radius: 10px;
  }

  .agents-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .empty-agents {
    color: #333;
    text-align: center;
    padding: 3rem;
    border: 1px dashed #1e1e3a;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    align-items: center;
  }
  .empty-agents button {
    background: none;
    border: none;
    color: #5a3aaa;
    cursor: pointer;
    font-size: 0.9rem;
  }
  .empty-agents button:hover { color: #a080ff; }
</style>
