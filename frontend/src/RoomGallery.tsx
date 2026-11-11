import { useEffect, useState } from 'react'

type Room = { id: number; name: string; image_key: string | null; capacity: number | null }

export function RoomGallery() {
  const [rooms, setRooms] = useState<Room[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    async function loadRooms() {
      try {
        const response = await fetch('/api/rooms', { signal: controller.signal })
        if (!response.ok) throw new Error('Could not load rooms.')
        setRooms(await response.json())
      } catch {
        if (!controller.signal.aborted) setFailed(true)
      }
    }
    void loadRooms()
    return () => controller.abort()
  }, [])

  return (
    <section className="room-gallery" id="rooms" aria-labelledby="rooms-title">
      <h2 id="rooms-title">Meeting rooms</h2>
      {failed ? (
        <p role="status">Could not load rooms. Refresh to try again.</p>
      ) : rooms === null ? (
        <p role="status">Loading rooms…</p>
      ) : rooms.length === 0 ? (
        <p>No rooms are listed yet.</p>
      ) : (
        <ul className="room-grid">
          {rooms.map((room) => (
            <li key={room.id}>
              {room.image_key && /^rooms\/[a-z]+\.webp$/.test(room.image_key) && (
                <img src={`${import.meta.env.BASE_URL}${room.image_key}`} alt={`${room.name} interior`} width="600" height="400" loading="lazy" />
              )}
              <h3>{room.name}</h3>
              {room.capacity !== null && (
                <p className="room-capacity">Up to {room.capacity} {room.capacity === 1 ? 'person' : 'people'}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
