import { useRef, useState, type FormEvent } from 'react'
import './BookingAssistant.css'

const example = 'จองห้องสำหรับ 8 คน พรุ่งนี้ 10:00–12:00'

type Message = { role: 'user' | 'assistant'; content: string }
type Proposal = {
  resource_id: number
  room_name: string
  party_size: number
  slots: { starts_at: string; ends_at: string }[]
}

const bookingDate = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium', timeZone: 'Asia/Bangkok',
})
const bookingTime = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bangkok',
})

function AssistantContent({ signedIn, onSignIn }: Props) {
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState<'chat' | 'booking' | null>(null)
  const [error, setError] = useState('')
  const [proposal, setProposal] = useState<Proposal | null>(null)

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = draft.trim()
    if (!content || pending || !signedIn) return
    const next: Message[] = [...messages, { role: 'user', content }]
    setMessages(next)
    setDraft('')
    setError('')
    setProposal(null)
    setPending('chat')
    try {
      const response = await fetch('/api/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next.slice(-11) }),
        signal: AbortSignal.timeout(20000),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not send message.')
      setMessages([...next, { role: 'assistant', content: data.reply }])
      setProposal(data.proposal ?? null)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not send message.')
      setMessages(messages)
      setDraft(content)
    } finally {
      setPending(null)
    }
  }

  async function confirmBooking() {
    if (!proposal || pending || !signedIn) return
    setError('')
    setPending('booking')
    try {
      const { resource_id, party_size, slots } = proposal
      const response = await fetch('/api/bookings/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resource_id, party_size, slots }),
        signal: AbortSignal.timeout(20000),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        if (response.status === 409 || response.status === 422) setProposal(null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not confirm the booking.')
      }
      setProposal(null)
      setMessages((current) => [...current, {
        role: 'assistant',
        content: `Booking confirmed for ${proposal.room_name}. You can view it in My bookings.`,
      }])
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not confirm the booking.')
    } finally {
      setPending(null)
    }
  }

  if (!signedIn) {
    return <div className="assistant-thread">
      <p>Sign in to find or book a meeting room.</p>
      <button className="assistant-example" type="button" onClick={onSignIn}>Sign in</button>
    </div>
  }

  return (
    <>
      <div className="assistant-thread" aria-live="polite">
        {messages.length === 0 && (
          <button className="assistant-example" type="button" onClick={() => setDraft(example)}>
            {example}
          </button>
        )}
        {messages.map((message, index) => (
          <p className={message.role === 'user' ? 'assistant-bubble assistant-user' : 'assistant-bubble'} key={index}>
            {message.content}
          </p>
        ))}
        {proposal && (
          <div className="assistant-proposal">
            <strong>{proposal.room_name}</strong>
            <p>{bookingDate.format(new Date(proposal.slots[0].starts_at))} · {proposal.party_size} people</p>
            <p>
              {bookingTime.format(new Date(proposal.slots[0].starts_at))}–
              {bookingTime.format(new Date(proposal.slots[proposal.slots.length - 1].ends_at))} Bangkok time
            </p>
            <div className="assistant-proposal-actions">
              <button className="booking-edit" type="button" disabled={pending !== null}
                onClick={() => void confirmBooking()}>
                {pending === 'booking' ? 'Confirming…' : 'Confirm booking'}
              </button>
              <button className="assistant-close" type="button" disabled={pending !== null}
                onClick={() => { setProposal(null); setError('') }}>Discard</button>
            </div>
          </div>
        )}
        {pending === 'chat' && <p role="status">Checking…</p>}
        {error && <p role="alert">{error}</p>}
      </div>
      <form className="assistant-composer" onSubmit={send}>
        <label>
          <span>Message</span>
          <input value={draft} onChange={(event) => setDraft(event.target.value)}
            placeholder="Find or book a room…" maxLength={500} disabled={pending !== null} />
        </label>
        <button type="submit" disabled={pending !== null || !draft.trim()}>Send</button>
      </form>
    </>
  )
}

type Props = { signedIn: boolean; onSignIn: () => void }

export function BookingAssistant({ signedIn, onSignIn }: Props) {
  function signIn() {
    dialog.current?.close()
    onSignIn()
  }

  const dialog = useRef<HTMLDialogElement>(null)

  return (
    <div className="booking-assistant">
      <aside className="assistant-panel assistant-desktop" aria-labelledby="assistant-heading">
        <header className="assistant-header">
          <h2 id="assistant-heading">AI Booking Assistant</h2>
        </header>
        <AssistantContent signedIn={signedIn} onSignIn={signIn} />
      </aside>

      <button className="assistant-launch home-primary" type="button" aria-haspopup="dialog"
        onClick={() => dialog.current?.showModal()}>Ask AI</button>
      <dialog ref={dialog} className="assistant-mobile" aria-labelledby="assistant-mobile-heading">
        <div className="assistant-panel">
          <header className="assistant-header">
            <div>
              <h2 id="assistant-mobile-heading">AI Booking Assistant</h2>
                </div>
            <button className="assistant-close" type="button" onClick={() => dialog.current?.close()}>Close</button>
          </header>
          <AssistantContent signedIn={signedIn} onSignIn={signIn} />
        </div>
      </dialog>
    </div>
  )
}
