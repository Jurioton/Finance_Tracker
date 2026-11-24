import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowUp, RotateCcw, Sparkles, Square, TriangleAlert, X } from 'lucide-react'
import api, { errorMessage } from '../api'
import { springs, useMediaQuery } from '../motion'

const SUGGESTIONS = [
  'How much did I spend this month?',
  'Where does most of my money go?',
  'Am I over any budget?',
  'How do I import a bank statement?',
]

// Floating "Ask AI" button and chat panel, available on every page.
// Answers come from a local model (Ollama) via the backend, which streams them as newline-delimited JSON.
export default function Assistant() {
  const [open, setOpen] = useState(false)
  const reduce = useReducedMotion()
  const isPhone = useMediaQuery('(max-width: 640px)')

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const hidden = reduce ? { opacity: 0 } : isPhone ? { y: '100%' } : { opacity: 0, scale: 0.6, y: 40, filter: 'blur(8px)' }
  const shown = reduce ? { opacity: 1 } : isPhone ? { y: 0 } : { opacity: 1, scale: 1, y: 0, filter: 'blur(0px)' }

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button key="fab" className="assistant-fab" onClick={() => setOpen(true)} aria-label="Ask AI"
            initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }}
            transition={reduce ? springs.fade : springs.sheet}>
            <Sparkles size={18} strokeWidth={2.3} /><span>Ask AI</span>
          </motion.button>
        )}
      </AnimatePresence>
      {/* Kept mounted while closed so the conversation survives closing and reopening the panel */}
      <motion.section className={`assistant-panel${open ? '' : ' closed'}`} role="dialog" aria-label="AI assistant"
        inert={!open} initial={false} animate={open ? shown : hidden}
        transition={reduce ? springs.fade : springs.sheet}>
        <Chat open={open} onClose={() => setOpen(false)} />
      </motion.section>
    </>
  )
}

function Chat({ open, onClose }) {
  const [messages, setMessages] = useState([]) // { role, content, error?, code? }
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [activity, setActivity] = useState('')
  const [status, setStatus] = useState(null) // backend's /assistant/status
  const [checking, setChecking] = useState(false)
  const abortRef = useRef(null)
  const listRef = useRef(null)
  const inputRef = useRef(null)

  const checkStatus = () => {
    setChecking(true)
    api.get('/assistant/status')
      .then((r) => setStatus(r.data))
      .catch((e) => setStatus({ available: false, model_installed: false, message: errorMessage(e) }))
      .finally(() => setChecking(false))
  }

  // Check Ollama each time the panel opens, and focus the input
  useEffect(() => {
    if (!open) return
    checkStatus()
    const t = setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 250)
    return () => clearTimeout(t)
  }, [open])

  // Stay scrolled to the newest message while the answer streams in
  useLayoutEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, activity])

  useEffect(() => () => abortRef.current?.abort(), [])

  const ready = status?.available && status?.model_installed

  const send = async (text) => {
    const question = text.trim()
    if (!question || busy) return
    const history = messages.filter((m) => !m.error && m.content).map(({ role, content }) => ({ role, content }))
    const next = [...history, { role: 'user', content: question }]
    setMessages([...messages, { role: 'user', content: question }, { role: 'assistant', content: '' }])
    setInput('')
    setBusy(true)
    setActivity('Thinking…')

    const update = (fn) => setMessages((all) => {
      const copy = [...all]
      copy[copy.length - 1] = fn(copy[copy.length - 1])
      return copy
    })

    const controller = new AbortController()
    abortRef.current = controller
    try {
      const res = await fetch(`${api.defaults.baseURL}/assistant/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
        body: JSON.stringify({ messages: next.slice(-20) }),
        signal: controller.signal,
      })
      if (res.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        window.location.href = '/login'
        return
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(typeof body.detail === 'string' ? body.detail : `Something went wrong (error ${res.status}).`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.trim()) continue
          const event = JSON.parse(line)
          if (event.type === 'token') {
            setActivity('')
            update((m) => ({ ...m, content: m.content + event.text }))
          } else if (event.type === 'status') {
            setActivity(event.text)
          } else if (event.type === 'error') {
            update((m) => ({ ...m, content: event.text, error: true, code: event.code }))
            if (event.code === 'unavailable' || event.code === 'model_missing') checkStatus()
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        update((m) => (m.content ? m : { ...m, content: 'Stopped.', error: true }))
      } else {
        const text = err instanceof TypeError
          ? `Can't reach the server at ${api.defaults.baseURL}. Check that the backend is running.`
          : err.message
        update((m) => ({ ...m, content: text, error: true }))
      }
    } finally {
      abortRef.current = null
      setBusy(false)
      setActivity('')
      inputRef.current?.focus({ preventScroll: true })
    }
  }

  const reset = () => {
    abortRef.current?.abort()
    setMessages([])
  }

  return (
    <>
      <header className="assistant-header">
        <span className="assistant-avatar"><Sparkles size={15} strokeWidth={2.4} /></span>
        <div className="assistant-title">
          <h3>Assistant</h3>
          <span className={`assistant-model ${ready ? 'ok' : status ? 'off' : ''}`}>
            {status ? (ready ? `${status.model} · on this device` : 'Local AI offline') : 'Checking…'}
          </span>
        </div>
        {messages.length > 0 && (
          <button className="icon-btn" onClick={reset} aria-label="New chat" title="New chat"><RotateCcw size={14} /></button>
        )}
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} strokeWidth={2.5} /></button>
      </header>

      <div className="assistant-messages" ref={listRef} aria-live="polite">
        {status && !ready && <Setup status={status} checking={checking} onRetry={checkStatus} />}

        {messages.length === 0 && (
          <div className="assistant-empty">
            <p>Ask about your spending, budgets and goals, or how to use any part of the app. Your data stays on this computer.</p>
            <div className="assistant-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="assistant-chip" onClick={() => send(s)} disabled={busy}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}${m.error ? ' error' : ''}`}>
            {m.error && <TriangleAlert size={14} />}
            {m.role === 'user' ? m.content : m.error ? <span>{inline(m.content)}</span> : <RichText text={m.content} />}
            {busy && i === messages.length - 1 && !m.content && (
              <span className="assistant-activity"><span className="typing" aria-hidden="true"><i /><i /><i /></span>{activity}</span>
            )}
          </div>
        ))}
        {busy && activity && messages.at(-1)?.content && (
          <span className="assistant-activity">{activity}</span>
        )}
      </div>

      <form className="assistant-input" onSubmit={(e) => { e.preventDefault(); send(input) }}>
        <textarea ref={inputRef} rows={1} value={input} maxLength={2000} placeholder="Ask anything about your money…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(input) }
          }} />
        {busy ? (
          <button type="button" className="assistant-send" onClick={() => abortRef.current?.abort()} aria-label="Stop">
            <Square size={12} fill="currentColor" />
          </button>
        ) : (
          <button className="assistant-send" disabled={!input.trim()} aria-label="Send"><ArrowUp size={17} strokeWidth={2.6} /></button>
        )}
      </form>
    </>
  )
}

// Shown when Ollama isn't running or the model isn't downloaded yet
function Setup({ status, checking, onRetry }) {
  const model = status.model || 'llama3.2'
  return (
    <div className="assistant-setup">
      <strong><TriangleAlert size={15} />{status.available ? 'Download the AI model' : 'Start the local AI'}</strong>
      <p>{inline(status.message || '')}</p>
      <ol>
        {!status.available && <li>Install Ollama from <a href="https://ollama.com/download" target="_blank" rel="noreferrer">ollama.com</a> and open it.</li>}
        <li>In a terminal run <code>ollama pull {model}</code></li>
        <li>Keep Ollama running, then press Try again.</li>
      </ol>
      <button className="btn small" onClick={onRetry} disabled={checking}>{checking ? 'Checking…' : 'Try again'}</button>
    </div>
  )
}

// A tiny, safe Markdown subset for answers: **bold**, `code`, and "-" / "1." lists. No HTML is injected.
function RichText({ text }) {
  const blocks = []
  let list = null
  for (const raw of text.split('\n')) {
    const line = raw.trimEnd()
    const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/)
    if (item) {
      const ordered = /^\s*\d/.test(line)
      if (!list || list.ordered !== ordered) blocks.push(list = { ordered, items: [] })
      list.items.push(item[1])
    } else {
      list = null
      if (line.trim()) blocks.push(line)
    }
  }
  return blocks.map((b, i) => {
    if (typeof b === 'string') return <p key={i}>{inline(b)}</p>
    const List = b.ordered ? 'ol' : 'ul'
    return <List key={i}>{b.items.map((t, j) => <li key={j}>{inline(t)}</li>)}</List>
  })
}

function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) return <code key={i}>{part.slice(1, -1)}</code>
    return <Fragment key={i}>{part}</Fragment>
  })
}
