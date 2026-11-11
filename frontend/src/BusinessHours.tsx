import { useEffect, useState, type FormEvent } from 'react'

type Hours = { opens_at: string; closes_at: string }

export function BusinessHours() {
  const [hours, setHours] = useState<Hours | null>(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    async function loadHours() {
      try {
        const response = await fetch('/api/business-hours', { signal: controller.signal })
        if (!response.ok) throw new Error()
        setHours(await response.json())
      } catch {
        if (!controller.signal.aborted) setMessage('Could not load opening hours.')
      }
    }
    void loadHours()
    return () => controller.abort()
  }, [])

  async function checkHours(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const date = fields.get('date')
    // The form always uses Bangkok time, regardless of the browser timezone.
    const bangkokTime = (field: string) => `${date}T${fields.get(field)}:00+07:00`
    setLoading(true)
    setMessage('')
    try {
      const response = await fetch('/api/business-hours/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ starts_at: bangkokTime('start'), ends_at: bangkokTime('end') }),
        signal: AbortSignal.timeout(10000),
      })
      if (!response.ok) throw new Error()
      const result = await response.json()
      setMessage(result.within_business_hours
        ? 'This slot is within opening hours.'
        : 'Choose an end time after the start, within opening hours.')
    } catch {
      setMessage('Could not check the time. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="booking-hours" aria-labelledby="booking-hours-title">
      <h2 id="booking-hours-title">Opening hours</h2>
      {hours && (
        <>
          <p>Daily, {hours.opens_at}–{hours.closes_at} (Bangkok time)</p>
          <form className="auth-form" onSubmit={checkHours} onChange={() => setMessage('')}>
            <label htmlFor="booking-date">Date</label>
            <input id="booking-date" name="date" type="date" required disabled={loading} />
            <label htmlFor="booking-start">Start time</label>
            <input id="booking-start" name="start" type="time" required disabled={loading} />
            <label htmlFor="booking-end">End time</label>
            <input id="booking-end" name="end" type="time" required disabled={loading} />
            <button className="auth-primary" type="submit" disabled={loading}>
              {loading ? 'Checking…' : 'Check opening hours'}
            </button>
          </form>
        </>
      )}
      <p className="auth-feedback" role="status">{message}</p>
    </section>
  )
}
