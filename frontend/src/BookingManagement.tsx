import { useEffect, useRef, useState, type FormEvent } from 'react'
import { EquipmentPicker, type EquipmentType } from './EquipmentPicker'
import type { Booking } from './MyBookings'

export type BookingManagementData = {
  request: {
    action: 'view' | 'edit' | 'cancel'
    new_day: string | null
    start_hour: number | null
    end_hour: number | null
    equipment: EquipmentType[] | null
    add_equipment: EquipmentType[]
    remove_equipment: EquipmentType[]
  }
  bookings: Booking[]
}

type Selection = {
  booking: Booking
  action: 'edit' | 'cancel'
  day: string
  hours: number[]
  equipment: EquipmentType[]
}

type Props = {
  data: BookingManagementData
  pending: boolean
  onPendingChange: (pending: boolean) => void
  onComplete: (message: string) => void
  onDiscard: () => void
}

const dateFormat = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeZone: 'Asia/Bangkok' })
const inputDateFormat = new Intl.DateTimeFormat('sv-SE', {
  year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Bangkok',
})
const timeFormat = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bangkok',
})
const hoursOfDay = Array.from({ length: 10 }, (_, index) => index + 8)
const formatHour = (hour: number) => `${String(hour).padStart(2, '0')}:00`

function timeLabel(slots: Booking['slots']) {
  return slots.map((slot) =>
    `${timeFormat.format(new Date(slot.starts_at))}–${timeFormat.format(new Date(slot.ends_at))}`,
  ).join(' · ')
}

export function BookingManagement({ data, pending, onPendingChange, onComplete, onDiscard }: Props) {
  const [selection, setSelection] = useState<Selection | null>(null)
  const [error, setError] = useState('')
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    panel.current?.scrollIntoView({ block: 'start' })
  }, [selection?.booking.id, selection?.action])

  function selectBooking(booking: Booking, action: Selection['action']) {
    const currentHours = booking.slots.map((slot) => Number(timeFormat.format(new Date(slot.starts_at)).split(':')[0]))
    const draft = data.request.action === 'edit' ? data.request : null
    let hours = currentHours
    if (draft?.end_hour != null) {
      const start = draft.start_hour ?? currentHours[0]
      hours = Array.from({ length: Math.max(0, draft.end_hour - start) }, (_, index) => start + index)
    } else if (draft?.start_hour != null) {
      const offset = draft.start_hour - currentHours[0]
      hours = currentHours.map((hour) => hour + offset)
    }
    const validHours = hours.length > 0 && hours.every((hour) => hour >= 8 && hour <= 17)
    const existingEquipment = booking.equipment.map((item) => item.category)
    const equipment = [...new Set([
      ...(draft?.equipment ?? existingEquipment),
      ...(draft?.add_equipment ?? []),
    ])].filter((item) => !draft?.remove_equipment.includes(item))
    setSelection({
      booking, action,
      day: draft?.new_day ?? inputDateFormat.format(new Date(booking.starts_at)),
      hours: validHours ? hours : [], equipment,
    })
    setError(validHours ? '' : 'Choose time slots within 08:00–18:00 Bangkok time.')
  }

  const slots = selection ? [...selection.hours].sort((a, b) => a - b).map((hour) => ({
    starts_at: `${selection.day}T${formatHour(hour)}:00+07:00`,
    ends_at: `${selection.day}T${formatHour(hour + 1)}:00+07:00`,
  })) : []

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selection || pending || (selection.action === 'edit' && slots.length === 0)) return
    const { booking, action, equipment } = selection
    onPendingChange(true)
    setError('')
    try {
      const response = await fetch(`/api/bookings/${booking.id}${action === 'cancel' ? '/cancel' : ''}`, {
        method: action === 'cancel' ? 'POST' : 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: action === 'edit' ? JSON.stringify({ slots, equipment }) : undefined,
        signal: AbortSignal.timeout(20000),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not update the booking.')
      }
      onComplete(action === 'cancel'
        ? `Booking #${booking.id} for ${booking.room_name} was cancelled, including its equipment.`
        : `Booking #${booking.id} for ${booking.room_name} was updated to ${dateFormat.format(new Date(slots[0].starts_at))}, ${timeLabel(slots)} (Bangkok time). Equipment · ${equipment.join(', ') || 'None'}.`)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not update the booking.')
    } finally {
      onPendingChange(false)
    }
  }

  return (
    <div className="assistant-management" ref={panel}>
      {selection ? (
        <>
          <button className="assistant-close" type="button" disabled={pending}
            onClick={() => { setSelection(null); setError('') }}>Choose another booking</button>
          <div className="assistant-booking-card">
            <strong>{selection.booking.room_name} · #{selection.booking.id}</strong>
            <p>{dateFormat.format(new Date(selection.booking.starts_at))}</p>
            <p>{timeLabel(selection.booking.slots)} Bangkok time</p>
            {selection.booking.equipment.length > 0 && (
              <p>Equipment · {selection.booking.equipment.map((item) => item.name).join(', ')}</p>
            )}
          </div>
          <form className="assistant-booking-edit" onSubmit={(event) => void confirm(event)}>
            {selection.action === 'edit' ? (
              <>
                <label className="assistant-edit-date">
                  New date
                  <input type="date" required min={inputDateFormat.format(new Date())}
                    value={selection.day} disabled={pending}
                    onChange={(event) => { setSelection({ ...selection, day: event.target.value }); setError('') }} />
                </label>
                <fieldset className="booking-edit-times" disabled={pending}>
                  <legend>New time slots (Bangkok)</legend>
                  <div className="slot-grid">
                    {hoursOfDay.map((hour) => (
                      <button type="button" key={hour} aria-pressed={selection.hours.includes(hour)}
                        onClick={() => {
                          setSelection({ ...selection, hours: selection.hours.includes(hour)
                            ? selection.hours.filter((item) => item !== hour)
                            : [...selection.hours, hour] })
                          setError('')
                        }}>
                        {formatHour(hour)}–{formatHour(hour + 1)}
                      </button>
                    ))}
                  </div>
                </fieldset>
                <EquipmentPicker slots={slots} selected={selection.equipment} bookingId={selection.booking.id}
                  disabled={pending} onChange={(equipment) => { setSelection({ ...selection, equipment }); setError('') }} />
              </>
            ) : <p>Cancel this room booking and release all its time slots and equipment?</p>}
            {error && <p className="assistant-management-error" role="alert">{error}</p>}
            <div className="assistant-proposal-actions">
              <button className={selection.action === 'cancel' ? 'booking-cancel' : 'booking-edit'} type="submit"
                disabled={pending || (selection.action === 'edit' && slots.length === 0)}>
                {pending ? 'Saving…' : selection.action === 'cancel' ? 'Confirm cancellation' : 'Confirm changes'}
              </button>
              <button className="assistant-close" type="button" disabled={pending} onClick={onDiscard}>Discard</button>
            </div>
          </form>
        </>
      ) : (
        <>
          <ul className="assistant-booking-list">
            {data.bookings.map((booking) => (
              <li className="assistant-booking-card" key={booking.id}>
                <div className="assistant-booking-heading">
                  {booking.image_key && /^rooms\/[a-z]+\.webp$/.test(booking.image_key) && (
                    <img src={`${import.meta.env.BASE_URL}${booking.image_key}`} alt="" width="60" height="48" loading="lazy" />
                  )}
                  <strong>{booking.room_name} · #{booking.id}</strong>
                </div>
                <p>{dateFormat.format(new Date(booking.starts_at))}</p>
                <p>{timeLabel(booking.slots)} Bangkok time</p>
                {booking.equipment.length > 0 && <p>Equipment · {booking.equipment.map((item) => item.name).join(', ')}</p>}
                <span className={`booking-status booking-status-${booking.status}`}>{booking.status}</span>
                {booking.can_cancel && (
                  <div className="assistant-proposal-actions">
                    {data.request.action === 'view' ? (
                      <>
                        <button className="booking-edit" type="button" disabled={pending}
                          aria-label={`Edit booking ${booking.id}`} onClick={() => selectBooking(booking, 'edit')}>Edit</button>
                        <button className="booking-cancel" type="button" disabled={pending}
                          aria-label={`Cancel booking ${booking.id}`} onClick={() => selectBooking(booking, 'cancel')}>Cancel</button>
                      </>
                    ) : (
                      <button className="booking-edit" type="button" disabled={pending}
                        aria-label={`Select booking ${booking.id}`}
                        onClick={() => selectBooking(booking, data.request.action === 'cancel' ? 'cancel' : 'edit')}>Select booking</button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
          <button className="assistant-close" type="button" disabled={pending} onClick={onDiscard}>Close bookings</button>
        </>
      )}
    </div>
  )
}
