/**
 * Ollama connection store for PhantomEx.
 * Manages host configuration and available model list.
 */

import { writable, derived } from 'svelte/store'

const STORAGE_KEY = 'phantomex_ollama_host'

function loadHost() {
  try {
    return localStorage.getItem(STORAGE_KEY) || 'http://localhost:8081'
  } catch {
    return 'http://localhost:8081'
  }
}

export const ollamaHost = writable(loadHost())
export const ollamaModels = writable([])
export const selectedModel = writable('')
export const connectionStatus = writable('idle') // idle | connecting | connected | error
export const connectionError = writable('')

// Persist host changes to localStorage
ollamaHost.subscribe(host => {
  try { localStorage.setItem(STORAGE_KEY, host) } catch {}
})

export async function fetchModels(host) {
  connectionStatus.set('connecting')
  connectionError.set('')
  try {
    const params = host ? `?host=${encodeURIComponent(host)}` : ''
    const res = await fetch(`/api/ollama/models${params}`)
    if (!res.ok) {
      const err = await res.text()
      throw new Error(err)
    }
    const models = await res.json()
    ollamaModels.set(models)
    if (models.length > 0) {
      selectedModel.update(cur => cur || models[0])
    }
    connectionStatus.set('connected')
    return models
  } catch (e) {
    connectionStatus.set('error')
    connectionError.set(e.message || 'Could not connect to Ollama')
    ollamaModels.set([])
    return []
  }
}
