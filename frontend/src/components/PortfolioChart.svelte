<script>
  /**
   * PortfolioChart — live SVG equity curve for a single agent.
   * Tracks total_value snapshots over time and renders a sparkline + area fill.
   * No external deps — pure SVG.
   */
  import { onMount, onDestroy } from 'svelte'
  import { trades } from '../lib/ws.js'

  export let agent          // full agent object (with portfolio.total_value)
  export let height = 80    // px
  export let width = '100%' // CSS width

  const MAX_POINTS = 500    // rolling window of snapshots

  // History array: { t: timestamp_ms, v: total_value }
  let history = []
  let prevValue = null
  let seeded = false

  // Seed history from REST on mount so chart survives page refresh
  onMount(async () => {
    try {
      const res = await fetch(`/api/agents/${agent.id}/equity?limit=500`)
      if (res.ok) {
        const rows = await res.json()
        if (rows.length > 0) {
          history = rows.map(r => ({ t: new Date(r.timestamp).getTime(), v: r.total_value }))
          prevValue = history[history.length - 1].v
        }
      }
    } catch (e) {
      // silently ignore — chart will build from live data
    }
    seeded = true
  })

  // Snapshot whenever agent.portfolio.total_value changes (after seed)
  $: if (seeded && agent?.portfolio?.total_value != null) {
    const v = agent.portfolio.total_value
    if (v !== prevValue) {
      prevValue = v
      history = [...history, { t: Date.now(), v }].slice(-MAX_POINTS)
    }
  }

  // Also snapshot on every incoming trade for this agent (forces instant update)
  $: $trades, (() => {})()

  // ── SVG path computation ────────────────────────────────────────────────────

  const W = 400  // internal SVG viewBox width
  const H = height

  $: pts = history.length < 2 ? [] : (() => {
    const values = history.map(p => p.v)
    const minV = Math.min(...values)
    const maxV = Math.max(...values)
    const range = maxV - minV || 1

    return history.map((p, i) => ({
      x: (i / (history.length - 1)) * W,
      y: H - ((p.v - minV) / range) * (H * 0.85) - H * 0.07,
    }))
  })()

  $: linePath = pts.length < 2 ? '' : (() => {
    return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  })()

  $: areaPath = pts.length < 2 ? '' : (() => {
    const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
    return `${line} L${W},${H} L0,${H} Z`
  })()

  // Current value vs starting value — determines colour
  $: startValue = history.length > 0 ? history[0].v : (agent?.allowance ?? 0)
  $: currentValue = agent?.portfolio?.total_value ?? startValue
  $: pnlPct = startValue > 0 ? ((currentValue - startValue) / startValue) * 100 : 0
  $: isUp = pnlPct >= 0

  $: strokeColor = isUp ? '#00d4a0' : '#ff4d6d'
  $: fillId = `fill-${agent?.id?.slice(0, 8) ?? 'x'}`
</script>

<div class="chart-wrap" style="height:{height}px">
  {#if pts.length < 2}
    <div class="chart-empty">Waiting for data…</div>
  {:else}
    <svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" class="chart-svg">
      <defs>
        <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color={strokeColor} stop-opacity="0.25" />
          <stop offset="100%" stop-color={strokeColor} stop-opacity="0.02" />
        </linearGradient>
      </defs>
      <!-- Area fill -->
      <path d={areaPath} fill="url(#{fillId})" />
      <!-- Line -->
      <path d={linePath} fill="none" stroke={strokeColor} stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" />
      <!-- Latest dot -->
      {#if pts.length > 0}
        <circle cx={pts[pts.length-1].x} cy={pts[pts.length-1].y} r="2.5" fill={strokeColor} />
      {/if}
    </svg>
  {/if}
</div>

<style>
  .chart-wrap {
    width: 100%;
    position: relative;
    overflow: hidden;
    border-radius: 4px;
  }
  .chart-svg {
    width: 100%;
    height: 100%;
    display: block;
  }
  .chart-empty {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.68rem;
    color: #333;
    font-style: italic;
  }
</style>
