<script>
  import { connected, agents, prices, deploymentLog } from './lib/ws.js'
  import PriceBar      from './components/PriceBar.svelte'
  import AgentCard     from './components/AgentCard.svelte'
  import TradeLog      from './components/TradeLog.svelte'
  import AddAgentModal from './components/AddAgentModal.svelte'
  import OllamaSetup   from './components/OllamaSetup.svelte'
  import DashboardStats from './components/DashboardStats.svelte'

  let showAddAgent = false

  $: agentList = Object.values($agents)

  function fmtTime(ts) {
    if (!ts) return ''
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }
</script>

<div class="app">

  <!-- ── Header ── -->
  <header>
    <div class="logo">
      <span class="phantom">Phantom</span><span class="ex">Ex</span>
      <span class="logo-tag">AI Paper Trading</span>
    </div>
    <div class="header-right">
      <span class="ws-status" class:connected={$connected}>
        <span class="ws-dot"></span>
        {$connected ? 'LIVE' : 'CONNECTING'}
      </span>
      <button class="add-agent-btn" on:click={() => showAddAgent = true}>
        ⚡ Deploy Agent
      </button>
    </div>
  </header>

  <!-- ── Price Ticker ── -->
  <PriceBar />

  <!-- ── Dashboard KPI Bar ── -->
  {#if agentList.length > 0}
    <DashboardStats />
  {/if}

  <!-- ── Ollama Setup Panel ── -->
  <div class="setup-panel">
    <OllamaSetup />
  </div>

  <!-- ── Main Content ── -->
  <main>

    <!-- Agents Grid -->
    <section class="agents-section">
      <div class="section-header">
        <h2>Active Agents</h2>
        {#if agentList.length > 0}
          <span class="count-badge">{agentList.length}</span>
        {/if}
      </div>

      {#if agentList.length === 0}
        <div class="empty-state">
          <div class="empty-icon">🤖</div>
          <div class="empty-title">No agents deployed</div>
          <div class="empty-sub">Deploy an AI agent to start paper trading. Each agent uses Ollama to make real-time decisions.</div>
          <button class="empty-cta" on:click={() => showAddAgent = true}>⚡ Deploy your first agent</button>
        </div>
      {:else}
        <div class="agents-grid">
          {#each agentList as agent (agent.id)}
            <AgentCard {agent} />
          {/each}
        </div>
      {/if}
    </section>

    <!-- Two-column bottom: Trade Log + Deployment Log -->
    <div class="bottom-row">

      <!-- Trade Log -->
      <section class="tradelog-section">
        <TradeLog />
      </section>

      <!-- Deployment Log -->
      <section class="deploy-log-section">
        <div class="deploy-log">
          <div class="deploy-log-header">
            <span>Deployment Log</span>
            <span class="log-count">{$deploymentLog.length}</span>
          </div>
          <div class="deploy-log-body">
            {#if $deploymentLog.length === 0}
              <div class="deploy-empty">No deployment events yet.</div>
            {:else}
              {#each $deploymentLog as evt}
                <div class="deploy-event" class:deployed={evt.action === 'deployed'} class:removed={evt.action === 'removed'}>
                  <span class="de-icon">{evt.action === 'deployed' ? '🟢' : '🔴'}</span>
                  <div class="de-info">
                    <span class="de-name">{evt.name}</span>
                    <span class="de-model">{evt.model.split(':')[0]}</span>
                  </div>
                  <div class="de-right">
                    <span class="de-action">{evt.action}</span>
                    <span class="de-time">{fmtTime(evt.ts)}</span>
                  </div>
                </div>
              {/each}
            {/if}
          </div>
        </div>
      </section>

    </div>
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
    background: #070710;
    color: #e0e0ff;
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
  }
  :global(::-webkit-scrollbar)       { width: 5px; height: 5px; }
  :global(::-webkit-scrollbar-track) { background: #0a0a18; }
  :global(::-webkit-scrollbar-thumb) { background: #2a2a4a; border-radius: 3px; }
  :global(::-webkit-scrollbar-thumb:hover) { background: #4a3a7a; }

  .app {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  /* Header */
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.7rem 1.5rem;
    background: #080814;
    border-bottom: 1px solid #18183a;
    gap: 1rem;
    position: sticky;
    top: 0;
    z-index: 50;
  }
  .logo {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    font-size: 1.25rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    flex-shrink: 0;
  }
  .phantom { color: #a080ff; }
  .ex      { color: #00d4a0; }
  .logo-tag {
    font-size: 0.6rem;
    color: #333;
    font-weight: 400;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 2px 6px;
    border: 1px solid #1e1e3a;
    border-radius: 3px;
  }

  .header-right { display: flex; align-items: center; gap: 0.75rem; }

  .ws-status {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.68rem;
    font-weight: 600;
    color: #555;
    letter-spacing: 0.06em;
  }
  .ws-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #ff4d6d;
    transition: background 0.3s;
  }
  .ws-status.connected { color: #00d4a0; }
  .ws-status.connected .ws-dot { background: #00d4a0; box-shadow: 0 0 6px rgba(0, 212, 160, 0.6); }

  .add-agent-btn {
    background: #2a1660;
    color: #c0b8ff;
    border: 1px solid #5a3aaa;
    padding: 0.4rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.82rem;
    font-weight: 600;
    transition: background 0.15s;
  }
  .add-agent-btn:hover { background: #4a2a9a; }

  /* Setup panel */
  .setup-panel {
    background: #080814;
    border-bottom: 1px solid #18183a;
    padding: 0.6rem 1.5rem;
  }

  /* Main */
  main {
    flex: 1;
    padding: 1.25rem 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    max-width: 1700px;
    margin: 0 auto;
    width: 100%;
  }

  /* Section headers */
  .section-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.85rem;
  }
  h2 {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #444;
    letter-spacing: 0.1em;
  }
  .count-badge {
    background: #1e1e3a;
    color: #777;
    font-size: 0.65rem;
    padding: 1px 7px;
    border-radius: 8px;
  }

  /* Empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    padding: 3.5rem 2rem;
    border: 1px dashed #1e1e3a;
    border-radius: 10px;
    text-align: center;
  }
  .empty-icon  { font-size: 2.5rem; filter: grayscale(0.5); }
  .empty-title { font-size: 0.95rem; font-weight: 600; color: #555; }
  .empty-sub   { font-size: 0.78rem; color: #333; max-width: 380px; line-height: 1.5; }
  .empty-cta {
    background: #2a1660; color: #c0b8ff; border: 1px solid #5a3aaa;
    padding: 0.5rem 1.25rem; border-radius: 6px; cursor: pointer;
    font-size: 0.82rem; font-weight: 600; margin-top: 0.25rem;
  }
  .empty-cta:hover { background: #4a2a9a; }

  /* Agents grid */
  .agents-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: flex-start;
  }

  /* Bottom row: trade log + deployment log */
  .bottom-row {
    display: grid;
    grid-template-columns: 1fr 280px;
    gap: 1rem;
    align-items: start;
  }
  @media (max-width: 900px) {
    .bottom-row { grid-template-columns: 1fr; }
  }

  .tradelog-section { min-width: 0; }

  /* Deployment log */
  .deploy-log {
    background: #0c0c1e;
    border: 1px solid #1e1e3a;
    border-radius: 8px;
    overflow: hidden;
  }
  .deploy-log-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 0.9rem;
    background: #0a0a1a;
    border-bottom: 1px solid #1a1a2e;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #555;
    letter-spacing: 0.06em;
  }
  .log-count {
    background: #1e1e3a; color: #777;
    font-size: 0.64rem; padding: 1px 6px; border-radius: 7px;
  }
  .deploy-log-body {
    max-height: 380px;
    overflow-y: auto;
  }
  .deploy-empty {
    padding: 1.5rem; color: #333;
    text-align: center; font-size: 0.78rem; font-style: italic;
  }
  .deploy-event {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.45rem 0.9rem;
    border-bottom: 1px solid #0a0a18;
    font-size: 0.72rem;
    transition: background 0.1s;
  }
  .deploy-event:hover { background: #0f0f22; }
  .deploy-event.deployed { border-left: 2px solid rgba(0, 212, 160, 0.3); }
  .deploy-event.removed  { border-left: 2px solid rgba(255, 77, 109, 0.3); }

  .de-icon { font-size: 0.65rem; flex-shrink: 0; }
  .de-info { display: flex; flex-direction: column; gap: 0.05rem; flex: 1; min-width: 0; }
  .de-name {
    color: #c0b8ff; font-weight: 600; font-size: 0.76rem;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .de-model { color: #555; font-size: 0.62rem; }
  .de-right { display: flex; flex-direction: column; align-items: flex-end; gap: 0.05rem; flex-shrink: 0; }
  .de-action { font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.05em; color: #666; }
  .deploy-event.deployed .de-action { color: #00a080; }
  .deploy-event.removed  .de-action { color: #cc3a55; }
  .de-time { font-size: 0.6rem; color: #444; }
</style>
