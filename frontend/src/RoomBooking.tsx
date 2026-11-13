import { useEffect, useState, type FormEvent } from 'react'

type Room = { id: number; name: string; capacity: number | null; image_key: string | null }
type Slot = { starts_at: string; ends_at: string; status: 'available' | 'booked' | 'past' }
type Search = { day: string; people: number }
type Props = { signedIn: boolean; onSignIn: () => void }

const bangkokDate = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit',
})
const bangkokTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit',
})

export function RoomBooking({ signedIn, onSignIn }: Props) {
  const [rooms, setRooms] = useState<Room[] | null>(null)
  const [catalogError, setCatalogError] = useState(false)
  const [search, setSearch] = useState<Search | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const response = await fetch('/api/rooms', { signal: controller.signal })
        if (!response.ok) throw new Error()
        setRooms(await response.json())
      } catch {
        if (!controller.signal.aborted) setCatalogError(true)
      }
    }
    void load()
    return () => controller.abort()
  }, [])

  function findRooms(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    setSearch({ day: String(values.get('day')), people: Number(values.get('people')) })
  }

  const matches = search && rooms?.filter((room) => (room.capacity ?? 0) >= search.people)
  return (
    <section className="room-gallery booking-panel" aria-labelledby="booking-title">
      <div className="booking-overview">
        <div className="booking-intro">
          <h1 id="booking-title">Book a meeting room</h1>
          <p>Daily, 08:00–18:00 Bangkok time. Book in one-hour slots.</p>
          <form className="booking-search" onSubmit={findRooms}>
            <label className="booking-field">
              Date (Bangkok time)
              <input type="date" name="day" min={bangkokDate.format(new Date())} defaultValue={bangkokDate.format(new Date())} required />
            </label>
            <label className="booking-field">
              Number of people
              <input type="number" name="people" min="1" step="1" defaultValue="1" required />
            </label>
            <button className="home-primary" type="submit" disabled={!rooms}>Find rooms</button>
          </form>
          {catalogError && <p role="alert">Could not load rooms. Refresh to try again.</p>}
        </div>
        <img className="booking-photo" src={`${import.meta.env.BASE_URL}meeting-room.webp`} alt="" width="1200" height="900" />
      </div>
      {matches && search && (
        matches.length === 0 ? <p>No rooms fit this group size.</p> : (
          <RoomResults key={JSON.stringify(search)} rooms={matches} search={search}
            signedIn={signedIn} onSignIn={onSignIn} />
        )
      )}
    </section>
  )
}

function RoomResults({ rooms, search, signedIn, onSignIn }: Props & { rooms: Room[]; search: Search }) {
  const [availability, setAvailability] = useState<Record<number, Slot[]> | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const { day, people } = search

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined
    async function load() {
      try {
        const response = await fetch(`/api/rooms/slots?day=${encodeURIComponent(day)}&people=${people}`, {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]),
        })
        if (!response.ok) throw new Error()
        setAvailability(await response.json())
        setLoadError(false)
      } catch {
        if (!controller.signal.aborted) {
          setAvailability(null)
          setLoadError(true)
        }
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(load, 5000)
      }
    }
    void load()
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [day, people, refresh])

  return (
    <section className="booking-results" aria-labelledby="booking-results-title">
      <h2 id="booking-results-title">Rooms and availability</h2>
      <p>{day} · Bangkok time</p>
      {availability === null && (
        <p role="status">{loadError ? 'Could not check availability. Retrying…' : 'Checking availability…'}</p>
      )}
      <ul className="booking-room-list">
        {rooms.map((room) => (
          <li className="booking-room-card" key={room.id}>
            <div className="booking-room-summary">
              {room.image_key && /^rooms\/[a-z]+\.webp$/.test(room.image_key) && (
                <img src={`${import.meta.env.BASE_URL}${room.image_key}`} alt="" width="600" height="400" loading="lazy" />
              )}
              <div className="booking-room-card-details">
                <h3>{room.name}</h3>
                <span>Up to {room.capacity} {room.capacity === 1 ? 'person' : 'people'}</span>
              </div>
            </div>
            <RoomSlots room={room} search={search} signedIn={signedIn} onSignIn={onSignIn}
              slots={availability?.[room.id] ?? null}
              onRefresh={() => { setAvailability(null); setRefresh((value) => value + 1) }} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function RoomSlots({ room, search, signedIn, onSignIn, slots, onRefresh }: Props & {
  room: Room; search: Search; slots: Slot[] | null; onRefresh: () => void
}) {
  const [selected, setSelected] = useState<string[]>([])
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  const chosen = slots?.filter((item) => selected.includes(item.starts_at) && item.status === 'available') ?? []
  const canConfirm = chosen.length > 0 && chosen.length === selected.length
  const { day, people } = search

  async function confirm() {
    if (!canConfirm || pending) return
    setPending(true)
    setMessage('')
    try {
      const response = await fetch('/api/bookings/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          resource_id: room.id,
          party_size: people,
          slots: chosen.map(({ starts_at, ends_at }) => ({ starts_at, ends_at })),
        }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not book this room.')
      }
      setMessage(`Booking confirmed for ${room.name} on ${day}: ${chosen.length} hour(s).`)
      setSelected([])
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not book this room.')
    } finally {
      setPending(false)
      onRefresh()
    }
  }

  return (
    <div className="booking-slots">
      {slots && (
        <div className="slot-grid" aria-label={`One-hour time slots for ${room.name}`}>
          {slots.map((item) => (
            <button type="button" key={item.starts_at} disabled={pending || (item.status !== 'available' && !selected.includes(item.starts_at))}
              aria-pressed={selected.includes(item.starts_at)}
              onClick={() => {
                setSelected((current) => current.includes(item.starts_at)
                  ? current.filter((start) => start !== item.starts_at)
                  : [...current, item.starts_at])
                setMessage('')
              }}>
              {bangkokTime.format(new Date(item.starts_at))}–{bangkokTime.format(new Date(item.ends_at))}
              <small>{item.status === 'available' ? 'Available' : item.status === 'booked' ? 'Booked' : 'Past'}</small>
            </button>
          ))}
        </div>
      )}
      {selected.length > 0 && slots && !canConfirm && (
        <p role="status">Deselect any booked or past slots before confirming.</p>
      )}
      {canConfirm && (
        <button className="home-primary" type="button" disabled={pending} onClick={signedIn ? confirm : onSignIn}>
          {pending ? 'Booking…' : signedIn ? `Confirm booking · ${selected.length} hr` : 'Sign in to confirm'}
        </button>
      )}
      {message && <p role="status">{message}</p>}
    </div>
  )
}
