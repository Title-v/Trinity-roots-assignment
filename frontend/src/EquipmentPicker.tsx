import { useEffect, useState } from 'react'

const equipmentTypes = ['Projector', 'Camera', 'Microphone'] as const
export type EquipmentType = typeof equipmentTypes[number]
export type EquipmentItem = { id: number; name: string; category: EquipmentType }
type Slot = { starts_at: string; ends_at: string }
type Availability = { name: EquipmentType; quantity: number }[]

type Props = {
  slots: Slot[]
  selected: EquipmentType[]
  onChange: (selected: EquipmentType[]) => void
  disabled: boolean
  bookingId?: number
}

export function EquipmentPicker({ slots, selected, onChange, disabled, bookingId }: Props) {
  const url = bookingId === undefined
    ? '/api/equipment/availability'
    : `/api/bookings/${bookingId}/equipment-availability`
  const body = JSON.stringify({ slots: slots.map(({ starts_at, ends_at }) => ({ starts_at, ends_at })) })
  const key = url + body
  const hasSlots = slots.length > 0
  const [result, setResult] = useState<{ key: string; items?: Availability; error?: string } | null>(null)

  useEffect(() => {
    if (!hasSlots) return
    const controller = new AbortController()
    let timer: number | undefined
    async function load() {
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body,
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]),
        })
        const data = await response.json()
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not check equipment.')
        if (!controller.signal.aborted) setResult({ key, items: data })
      } catch (error) {
        if (!controller.signal.aborted) setResult({
          key, error: error instanceof Error ? error.message : 'Could not check equipment.',
        })
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(load, 5000)
      }
    }
    void load()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [body, hasSlots, key, url])

  const availability = result?.key === key ? result.items : undefined
  const error = result?.key === key ? result.error : undefined

  return (
    <fieldset className="equipment-picker" disabled={disabled || !hasSlots}>
      <legend>Equipment (optional)</legend>
      <p>{hasSlots ? 'One item per type, booked for the same times as this room.' : 'Select room time slots to check equipment.'}</p>
      <div className="equipment-options">
        {equipmentTypes.map((category) => {
          const checked = selected.includes(category)
          const quantity = availability?.find((item) => item.name === category)?.quantity
          return (
            <label key={category} className="equipment-option">
              <input type="checkbox" checked={checked}
                disabled={!checked && (quantity === undefined || quantity === 0)}
                onChange={() => onChange(checked ? selected.filter((item) => item !== category) : [...selected, category])} />
              <span>
                <strong>{category}</strong>
                {hasSlots && <small>{quantity === undefined ? 'Checking…' : `${quantity} available`}</small>}
              </span>
            </label>
          )
        })}
      </div>
      {error && <p role="alert">{error}</p>}
    </fieldset>
  )
}
