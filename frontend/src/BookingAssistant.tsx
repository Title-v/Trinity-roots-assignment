import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import type { EquipmentType } from './EquipmentPicker'
import { BookingManagement, type BookingManagementData } from './BookingManagement'
import './BookingAssistant.css'

const starterPrompts = [
  'หาห้องว่างพรุ่งนี้สำหรับ 4 คน',
  'จองห้องสำหรับ 8 คน พรุ่งนี้ 14:00–16:00',
  'ดูการจองของฉัน',
]

type Message = { role: 'user' | 'assistant'; content: string }
type Proposal = {
  resource_id: number
  room_name: string
  capacity?: number
  image_key?: string | null
  party_size: number
  slots: { starts_at: string; ends_at: string }[]
  equipment: EquipmentType[]
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
  const [contextStart, setContextStart] = useState(0)
  const [pending, setPending] = useState<'chat' | 'booking' | null>(null)
  const [error, setError] = useState('')
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(null)
  const [management, setManagement] = useState<BookingManagementData | null>(null)
  const proposal = proposals.find((item) => item.resource_id === selectedRoomId) ?? null
  const bookingDetails = proposal ?? proposals[0]
  const thread = useRef<HTMLDivElement>(null)
  const lastMessage = useRef<HTMLParagraphElement>(null)
  const messageInput = useRef<HTMLInputElement>(null)
  const roomGroup = useId()

  useEffect(() => {
    if (thread.current && lastMessage.current) {
      thread.current.scrollTop = proposals.length > 0 || management !== null
        ? lastMessage.current.offsetTop - 18
        : thread.current.scrollHeight
    }
  }, [messages, proposals, management])

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = draft.trim()
    if (!content || pending || !signedIn) return
    const next: Message[] = [...messages, { role: 'user', content }]
    setMessages(next)
    setDraft('')
    setError('')
    setProposals([])
    setManagement(null)
    setSelectedRoomId(null)
    setPending('chat')
    try {
      const response = await fetch('/api/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next.slice(contextStart).slice(-11) }),
        signal: AbortSignal.timeout(20000),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not send message.')
      setMessages([...next, { role: 'assistant', content: data.reply }])
      const choices: Proposal[] = data.proposals ?? (data.proposal ? [data.proposal] : [])
      setProposals(choices.map((item) => ({ ...item, equipment: item.equipment ?? [] })))
      setManagement(data.management ?? null)
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
      const { resource_id, party_size, slots, equipment } = proposal
      const response = await fetch('/api/bookings/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resource_id, party_size, slots, equipment }),
        signal: AbortSignal.timeout(20000),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        if (response.status === 409 || response.status === 422) {
          setProposals([])
          setSelectedRoomId(null)
        }
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not confirm the booking.')
      }
      setProposals([])
      setSelectedRoomId(null)
      setMessages((current) => [...current, {
        role: 'assistant',
        content: `Booking confirmed for ${proposal.room_name}. You can view it in My bookings.`,
      }])
      setContextStart(messages.length + 1)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not confirm the booking.')
    } finally {
      setPending(null)
    }
  }

  if (!signedIn) {
    return <div className="assistant-thread">
      <p>Sign in to find and book rooms, or manage your reservations.</p>
      <button className="assistant-example" type="button" onClick={onSignIn}>Sign in</button>
    </div>
  }

  return (
    <>
      <div ref={thread} className="assistant-thread" aria-live="polite">
        {messages.length === 0 && (
          <div className="assistant-welcome">
            <p className="assistant-bubble">
              สวัสดีครับ ผมช่วยหาห้องว่าง จองห้องพร้อมอุปกรณ์ และแก้ไขหรือยกเลิกการจองของคุณได้ครับ
              <br /><br />
              วันนี้ต้องการให้ช่วยเรื่องไหนครับ?
            </p>
            <p className="assistant-start-hint">เลือกตัวอย่าง แล้วปรับรายละเอียดก่อนส่งได้เลย</p>
            <div className="assistant-starters" aria-label="ข้อความตัวอย่าง">
              {starterPrompts.map((prompt) => (
                <button className="assistant-example" type="button" key={prompt}
                  onClick={() => { setDraft(prompt); messageInput.current?.focus() }}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message, index) => (
          <p ref={index === messages.length - 1 ? lastMessage : null}
            className={message.role === 'user' ? 'assistant-bubble assistant-user' : 'assistant-bubble'} key={index}>
            {message.content}
          </p>
        ))}
        {proposals.length > 0 && (
          <fieldset className="assistant-room-options" disabled={pending !== null}>
            <legend>Choose a room</legend>
            {proposals.map((room) => (
              <label className="assistant-room-option" key={room.resource_id}>
                <input type="radio" name={roomGroup} value={room.resource_id}
                  checked={room.resource_id === selectedRoomId}
                  onChange={() => { setSelectedRoomId(room.resource_id); setError('') }} />
                {room.image_key && /^rooms\/[a-z]+\.webp$/.test(room.image_key) && (
                  <img src={`${import.meta.env.BASE_URL}${room.image_key}`} alt="" width="72" height="54" loading="lazy" />
                )}
                <span>
                  <strong>{room.room_name}</strong>
                  {room.capacity !== undefined && <small>Up to {room.capacity} people</small>}
                </span>
              </label>
            ))}
          </fieldset>
        )}
        {pending === 'chat' && <p role="status">Checking…</p>}
        {management && (
          <BookingManagement data={management} pending={pending !== null}
            onPendingChange={(value) => setPending(value ? 'booking' : null)}
            onDiscard={() => { setManagement(null); setContextStart(messages.length) }}
            onComplete={(content) => {
              setManagement(null)
              setMessages((current) => [...current, { role: 'assistant', content }])
              setContextStart(messages.length + 1)
            }} />
        )}
      </div>
      {error && <p className="assistant-error" role="alert">{error}</p>}
      {bookingDetails && (
        <div className="assistant-proposal" aria-live="polite">
          {proposal ? <strong>{proposal.room_name}</strong> : <strong>Select a room to continue</strong>}
          <p>{bookingDate.format(new Date(bookingDetails.slots[0].starts_at))} · {bookingDetails.party_size} people</p>
          <p>
            {bookingTime.format(new Date(bookingDetails.slots[0].starts_at))}–
            {bookingTime.format(new Date(bookingDetails.slots[bookingDetails.slots.length - 1].ends_at))} Bangkok time
          </p>
          <p>Equipment · {bookingDetails.equipment.length > 0
            ? `${bookingDetails.equipment.join(', ')} (1 each)` : 'None'}</p>
          <div className="assistant-proposal-actions">
            <button className="booking-edit" type="button" disabled={pending !== null || proposal === null}
              onClick={() => void confirmBooking()}>
              {pending === 'booking' ? 'Confirming…' : 'Confirm booking'}
            </button>
            <button className="assistant-close" type="button" disabled={pending !== null}
              onClick={() => { setProposals([]); setSelectedRoomId(null); setContextStart(messages.length); setError('') }}>Discard</button>
          </div>
        </div>
      )}
      <form className="assistant-composer" onSubmit={send}>
        <label>
          <span>Message</span>
          <input ref={messageInput} value={draft} onChange={(event) => setDraft(event.target.value)}
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
