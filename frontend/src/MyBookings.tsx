import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { EquipmentPicker, type EquipmentItem, type EquipmentType } from './EquipmentPicker'

export type Booking = {
  id: number
  room_name: string
  image_key?: string | null
  starts_at: string
  ends_at: string
  slots: { starts_at: string; ends_at: string }[]
  equipment: EquipmentItem[]
  status: 'confirmed' | 'cancelled' | 'completed'
  can_cancel: boolean
}

const dateFormat = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'full', timeZone: 'Asia/Bangkok',
})
const timeFormat = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bangkok',
})
const inputDateFormat = new Intl.DateTimeFormat('sv-SE', {
  year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Bangkok',
})
const bookingHours = Array.from({ length: 10 }, (_, index) => index + 8)
const formatHour = (hour: number) => `${String(hour).padStart(2, '0')}:00`

export function MyBookings() {
  const [bookings, setBookings] = useState<Booking[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [reload, setReload] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  const [cancelError, setCancelError] = useState('')
  const [edit, setEdit] = useState<{
    id: number; day: string; hours: number[]; equipment: EquipmentType[]
  } | null>(null)
  const [editError, setEditError] = useState('')
  const editSlots = edit ? [...edit.hours].sort((a, b) => a - b).map((hour) => ({
    starts_at: `${edit.day}T${formatHour(hour)}:00+07:00`,
    ends_at: `${edit.day}T${formatHour(hour + 1)}:00+07:00`,
  })) : []

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

  async function reschedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!edit || pending || edit.hours.length === 0) return
    const { id, equipment } = edit
    setPending(true)
    setEditError('')
    setMessage('')
    try {
      const response = await fetch(`/api/bookings/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slots: editSlots, equipment }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not save changes.')
      }
      setBookings(null)
      setLoadError(false)
      setReload((value) => value + 1)
      setEdit(null)
      setMessage('Booking updated.')
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'Could not save changes.')
    } finally {
      setPending(false)
    }
  }

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
            {bookings.map((booking) => {
              const slots = booking.slots ?? [{ starts_at: booking.starts_at, ends_at: booking.ends_at }]
              return (
                <li key={booking.id} className="my-booking-card">
                  <div>
                    <h2>{booking.room_name}</h2>
                    <p>{dateFormat.format(new Date(booking.starts_at))}</p>
                    <p>{slots.map((slot) =>
                      `${timeFormat.format(new Date(slot.starts_at))}–${timeFormat.format(new Date(slot.ends_at))}`,
                    ).join(' · ')}</p>
                    {(booking.equipment?.length ?? 0) > 0 && (
                      <p className="my-booking-equipment">Equipment · {booking.equipment.map((item) => item.name).join(', ')}</p>
                    )}
                  </div>
                  <div className="my-booking-actions">
                    <span className={`booking-status booking-status-${booking.status}`}>{booking.status}</span>
                    {selected === booking.id ? (
                      <div className="booking-cancel-confirm">
                        <p>Cancel this room booking and all its equipment?</p>
                        <button className="home-link" type="button" disabled={pending} onClick={() => setSelected(null)}>Keep booking</button>
                        <button className="booking-cancel" type="button" disabled={pending} onClick={() => void cancel(booking.id)}>
                          {pending ? 'Cancelling…' : 'Confirm cancellation'}
                        </button>
                        {cancelError && <p role="alert">{cancelError}</p>}
                      </div>
                    ) : booking.can_cancel && edit?.id !== booking.id && (
                      <>
                        <button className="booking-edit" type="button" disabled={pending} onClick={() => {
                          const start = new Date(booking.starts_at)
                          setSelected(null)
                          setEditError('')
                          setMessage('')
                          setEdit({
                            id: booking.id,
                            day: inputDateFormat.format(start),
                            hours: slots.map((slot) =>
                              Number(timeFormat.format(new Date(slot.starts_at)).split(':')[0]),
                            ),
                            equipment: (booking.equipment ?? []).map((item) => item.category),
                          })
                        }}>Edit booking</button>
                        <button className="booking-cancel" type="button" disabled={pending} onClick={() => {
                          setEdit(null)
                          setCancelError('')
                          setSelected(booking.id)
                        }}>Cancel booking</button>
                      </>
                    )}
                  </div>
                  {edit?.id === booking.id && (
                    <form className="booking-edit-form" onSubmit={(event) => void reschedule(event)}>
                      <label>
                        New date
                        <input type="date" required min={inputDateFormat.format(new Date())}
                          value={edit.day} disabled={pending}
                          onChange={(event) => setEdit({ ...edit, day: event.target.value })} />
                      </label>
                      <fieldset className="booking-edit-times" disabled={pending}>
                        <legend>Time slots (Bangkok) · {edit.hours.length} selected</legend>
                        <div className="slot-grid">
                          {bookingHours.map((hour) => (
                            <button key={hour} type="button" aria-pressed={edit.hours.includes(hour)}
                              onClick={() => {
                                setEdit({ ...edit, hours: edit.hours.includes(hour)
                                  ? edit.hours.filter((selectedHour) => selectedHour !== hour)
                                  : [...edit.hours, hour] })
                                setEditError('')
                              }}>
                              {formatHour(hour)}–{formatHour(hour + 1)}
                            </button>
                          ))}
                        </div>
                      </fieldset>
                      <EquipmentPicker slots={editSlots} selected={edit.equipment}
                        onChange={(equipment) => setEdit({ ...edit, equipment })}
                        disabled={pending} bookingId={booking.id} />
                      <div className="my-booking-actions">
                        <button className="booking-edit" type="submit" disabled={pending || edit.hours.length === 0}>
                          {pending ? 'Saving…' : 'Save changes'}
                        </button>
                        <button className="home-link" type="button" disabled={pending}
                          onClick={() => setEdit(null)}>Discard changes</button>
                      </div>
                      {editError && <p className="booking-edit-error" role="alert">{editError}</p>}
                    </form>
                  )}
                </li>
              )
            })}
          </ul>
        )}
    </section>
  )
}
