/**
 * PhantomEx WebSocket store.
 * Maintains a single persistent connection and dispatches typed events
 * to all registered listeners.
 */

import { writable, get } from 'svelte/store'

export const connected = writable(false)
export const prices = writable({})
export const agents = writable({})   // agent_id -> agent state
export const trades = writable([])   // recent trade log
export const pendingDecisions = writable({}) // agent_id -> decision

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

    case 'agent_state':
      agents.update(a => ({ ...a, [msg.data.id]: msg.data }))
      break

    case 'agent_removed':
      agents.update(a => {
        const next = { ...a }
        delete next[msg.agent_id]
        return next
      })
      break

    case 'trade':
      trades.update(t => [msg.data, ...t].slice(0, 200))
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

  socket.onopen = () => {
    connected.set(true)
    console.log('[ws] Connected to PhantomEx')
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

export { on, send, connect }

// Auto-connect on import
connect()
