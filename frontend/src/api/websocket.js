const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:"
const WS_URL = `${WS_PROTOCOL}//${window.location.host}/ws/chat`

class ViralMintWS {
  constructor() {
    this.ws = null
    this.listeners = {}
    this.reconnectDelay = 1000
    this.maxReconnectDelay = 30000
    this._shouldReconnect = true
    this._queue = [] // messages queued while disconnected
  }

  get connected() {
    return this.ws?.readyState === WebSocket.OPEN
  }

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return
    }

    this.ws = new WebSocket(WS_URL)

    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        const handlers = this.listeners[msg.type] || []
        handlers.forEach(h => h(msg))
      } catch (err) {
        console.error("WS parse error:", err)
      }
    }

    this.ws.onclose = () => {
      // Notify listeners of disconnection
      const handlers = this.listeners["_connection_state"] || []
      handlers.forEach(h => h({ connected: false }))

      if (this._shouldReconnect) {
        setTimeout(() => this.connect(), this.reconnectDelay)
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay)
      }
    }

    this.ws.onopen = () => {
      this.reconnectDelay = 1000

      // Flush queued messages
      const pending = this._queue.splice(0)
      for (const msg of pending) {
        this.ws.send(JSON.stringify(msg))
      }

      // Notify listeners of connection
      const handlers = this.listeners["_connection_state"] || []
      handlers.forEach(h => h({ connected: true }))
    }

    this.ws.onerror = (err) => {
      console.error("WS error:", err)
    }
  }

  on(type, callback) {
    if (!this.listeners[type]) this.listeners[type] = []
    this.listeners[type].push(callback)
    return () => {
      this.listeners[type] = this.listeners[type].filter(h => h !== callback)
    }
  }

  send(message) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      // Queue important messages (chat, wizard steps) for retry on reconnect
      const queueable = ["chat_message", "set_session", "wizard_step_complete", "wizard_cancel"]
      if (queueable.includes(message.type)) {
        this._queue.push(message)
      }
    }
  }

  disconnect() {
    this._shouldReconnect = false
    this.ws?.close()
  }

}

export const ws = new ViralMintWS()
