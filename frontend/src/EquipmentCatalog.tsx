import { useEffect, useState } from 'react'

type Equipment = { name: string; quantity: number }

export function EquipmentCatalog() {
  const [equipment, setEquipment] = useState<Equipment[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    async function loadEquipment() {
      try {
        const response = await fetch('/api/equipment', { signal: controller.signal })
        if (!response.ok) throw new Error()
        setEquipment(await response.json())
      } catch {
        if (!controller.signal.aborted) setFailed(true)
      }
    }
    void loadEquipment()
    return () => controller.abort()
  }, [])

  return (
    <section className="room-gallery" id="equipment" aria-labelledby="equipment-title">
      <h2 id="equipment-title">Equipment</h2>
      {failed ? (
        <p role="status">Could not load equipment. Refresh to try again.</p>
      ) : equipment === null ? (
        <p role="status">Loading equipment…</p>
      ) : (
        <ul className="room-grid equipment-grid">
          {equipment.map(({ name, quantity }) => (
            <li key={name}>
              <h3>{name}</h3>
              <p className="room-capacity">{quantity} {quantity === 1 ? 'unit' : 'units'}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
