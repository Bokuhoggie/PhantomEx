/**
 * PhantomEx WebSocket store.
 * Maintains a single persistent connection and dispatches typed events
 * to all registered listeners.
 */

import { writable, get } from 'svelte/store'

export const connected        = writable(false)
export const prices           = writable({})
export const agents           = writable({})          // agent_id -> agent state
export const trades           = writable([])          // recent trade log (newest first)
export const pendingDecisions = writable({})          // agent_id -> decision
export const deploymentLog    = writable([])          // [{id, name, model, action, ts}]

const WIPE_KEY = 'phantomex_wipe_before'

function getWipeBefore() {
  const v = localStorage.getItem(WIPE_KEY)
  return v ? Number(v) : 0
}

function afterWipe(trade) {
  const wb = getWipeBefore()
  if (!wb) return true
  const ts = trade.timestamp ? new Date(trade.timestamp).getTime() : 0
  return ts > wb
}

const WS_URL = `ws://${window.location.host}/ws`
const RECONNECT_MS = 3000

let socket = null
let listeners = {}

function on(type, fn) {
  if (!listeners[type]) listeners[type] = []
  listeners[type].push(fn)
  return () => {
    listeners[type] = listeners[type].filter(f => f !== fn)
  }
}

function dispatch(msg) {
  const t = msg.type
  if (listeners[t]) listeners[t].forEach(fn => fn(msg))

  switch (t) {
    case 'prices':
      prices.set(msg.data)
      break

    case 'agent_state': {
      const prev = get(agents)
      const isNew = !prev[msg.data.id]
      agents.update(a => ({ ...a, [msg.data.id]: msg.data }))
      // Log deployment events
      if (isNew) {
        deploymentLog.update(log => [{
          id: msg.data.id,
          name: msg.data.name,
          model: msg.data.model,
          action: 'deployed',
          ts: Date.now(),
        }, ...log].slice(0, 100))
      }
      break
    }

    case 'agent_removed':
      agents.update(a => {
        const removed = a[msg.agent_id]
        const next = { ...a }
        delete next[msg.agent_id]
        if (removed) {
          deploymentLog.update(log => [{
            id: msg.agent_id,
            name: removed.name || msg.agent_id.slice(0, 8),
            model: removed.model || '',
            action: 'removed',
            ts: Date.now(),
          }, ...log].slice(0, 100))
        }
        return next
      })
      break

    case 'trade':
      if (afterWipe(msg.data)) {
        trades.update(t => [msg.data, ...t].slice(0, 500))
      }
      break

    case 'portfolio':
      agents.update(a => {
        if (!a[msg.agent_id]) return a
        return {
          ...a,
          [msg.agent_id]: { ...a[msg.agent_id], portfolio: msg.data },
        }
      })
      break

    case 'pending_decision':
      pendingDecisions.update(d => ({ ...d, [msg.agent_id]: msg.data }))
      break
  }
}

function send(msg) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg))
  }
}

function connect() {
  socket = new WebSocket(WS_URL)

  socket.onopen = async () => {
    connected.set(true)
    console.log('[ws] Connected to PhantomEx')
    // Seed historical trade log from REST so log is never empty on page load
    try {
      const res = await fetch('/api/trades?limit=500')
      const data = await res.json()
      trades.set(data.filter(afterWipe))
    } catch (e) {
      console.warn('[ws] Could not seed trade history', e)
    }
  }

  socket.onmessage = (e) => {
    try {
      dispatch(JSON.parse(e.data))
    } catch (err) {
      console.error('[ws] Parse error', err)
    }
  }

  socket.onclose = () => {
    connected.set(false)
    console.log(`[ws] Disconnected. Reconnecting in ${RECONNECT_MS}ms...`)
    setTimeout(connect, RECONNECT_MS)
  }

  socket.onerror = (e) => {
    console.error('[ws] Error', e)
  }
}

export function approveTrade(agentId) {
  send({ type: 'approve_trade', agent_id: agentId })
  pendingDecisions.update(d => {
    const next = { ...d }
    delete next[agentId]
    return next
  })
}

export function rejectTrade(agentId) {
  send({ type: 'reject_trade', agent_id: agentId })
  pendingDecisions.update(d => {
    const next = { ...d }
    delete next[agentId]
    return next
  })
}

/** Wipe local trade log display (does not delete from server DB) */
export function wipeTradeLog() {
  localStorage.setItem(WIPE_KEY, String(Date.now()))
  trades.set([])
}

export { on, send, connect }

// Auto-connect on import
connect()
