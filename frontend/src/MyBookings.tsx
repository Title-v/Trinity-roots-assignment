import { useEffect, useState } from 'react'

type Booking = {
  id: number
  room_name: string
  starts_at: string
  ends_at: string
  status: 'confirmed' | 'cancelled' | 'completed'
  can_cancel: boolean
}

const dateFormat = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'full', timeZone: 'Asia/Bangkok',
})
const timeFormat = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bangkok',
})

export function MyBookings() {
  const [bookings, setBookings] = useState<Booking[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [reload, setReload] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  const [cancelError, setCancelError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const response = await fetch('/api/bookings', { signal: controller.signal })
        if (!response.ok) throw new Error()
        setBookings(await response.json())
      } catch {
        if (!controller.signal.aborted) setLoadError(true)
      }
    }
    void load()
    return () => controller.abort()
  }, [reload])

  async function cancel(id: number) {
    if (pending) return
    setPending(true)
    setCancelError('')
    setMessage('')
    try {
      const response = await fetch(`/api/bookings/${id}/cancel`, { method: 'POST' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not cancel the booking.')
      }
      setBookings((current) => current?.map((booking) =>
        booking.id === id ? { ...booking, status: 'cancelled', can_cancel: false } : booking,
      ) ?? null)
      setSelected(null)
      setMessage('Booking cancelled.')
    } catch (error) {
      setCancelError(error instanceof Error ? error.message : 'Could not cancel the booking.')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="room-gallery booking-panel my-bookings" aria-labelledby="my-bookings-title">
      <h1 id="my-bookings-title">My bookings</h1>
      <p>All times are shown in Bangkok time.</p>
      {message && <p className="my-bookings-notice" role="status">{message}</p>}
      {loadError ? (
        <p role="alert">Could not load bookings.{' '}
          <button className="home-link" type="button" onClick={() => {
            setLoadError(false)
            setReload((value) => value + 1)
          }}>Try again</button>
        </p>
      ) : bookings === null ? <p role="status">Loading bookings…</p>
        : bookings.length === 0 ? (
          <div className="my-bookings-empty">
            <p>You haven’t booked a room yet.</p>
            <a className="home-primary" href={`${import.meta.env.BASE_URL}booking`}>Book a room</a>
          </div>
        ) : (
          <ul className="booking-room-list">
            {bookings.map((booking) => (
              <li key={booking.id} className="my-booking-card">
                <div>
                  <h2>{booking.room_name}</h2>
                  <p>{dateFormat.format(new Date(booking.starts_at))}</p>
                  <p>{timeFormat.format(new Date(booking.starts_at))}–{timeFormat.format(new Date(booking.ends_at))}</p>
                </div>
                <div className="my-booking-actions">
                  <span className={`booking-status booking-status-${booking.status}`}>{booking.status}</span>
                  {selected === booking.id ? (
                    <div className="booking-cancel-confirm">
                      <p>Cancel this time slot?</p>
                      <button className="home-link" type="button" disabled={pending} onClick={() => setSelected(null)}>Keep booking</button>
                      <button className="booking-cancel" type="button" disabled={pending} onClick={() => void cancel(booking.id)}>
                        {pending ? 'Cancelling…' : 'Confirm cancellation'}
                      </button>
                      {cancelError && <p role="alert">{cancelError}</p>}
                    </div>
                  ) : booking.can_cancel && (
                    <button className="booking-cancel" type="button" disabled={pending} onClick={() => {
                      setCancelError('')
                      setSelected(booking.id)
                    }}>Cancel booking</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
    </section>
  )
}
