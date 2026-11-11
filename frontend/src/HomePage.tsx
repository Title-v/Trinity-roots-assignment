import { useEffect, useState } from 'react'
import { EquipmentCatalog } from './EquipmentCatalog'
import { RoomGallery } from './RoomGallery'
import './HomePage.css'

type HomePageProps = {
  onSignIn: () => void
  onRegister: () => void
}

type Hours = { opens_at: string; closes_at: string }

export function HomePage({ onSignIn, onRegister }: HomePageProps) {
  const [hours, setHours] = useState<Hours | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/business-hours', { signal: controller.signal })
      .then(async (response) => {
        if (response.ok) setHours(await response.json())
      })
      .catch(() => {
        // The account links remain usable if opening hours cannot be loaded.
      })
    return () => controller.abort()
  }, [])

  return (
    <div className="home-page">
      <header className="home-header">
        <span className="home-brand">Trinity Roots</span>
        <nav className="home-nav" aria-label="Main navigation">
          <a className="home-link" href="#rooms">Rooms</a>
          <a className="home-link" href="#equipment">Equipment</a>
          <button type="button" className="home-link" onClick={onSignIn}>Sign in</button>
        </nav>
      </header>
      <main>
        <div className="home-hero">
          <div className="home-intro">
            <h1>Make room for good work.</h1>
            <p>A place to plan your meetings and equipment needs.</p>
            <div className="home-actions">
              <button type="button" className="home-primary" onClick={onRegister}>Create account</button>
              <button type="button" className="home-link" onClick={onSignIn}>Sign in</button>
            </div>
          </div>
          <img className="home-photo" src={`${import.meta.env.BASE_URL}meeting-room.webp`} alt="A sunlit meeting room with an oak table and green chairs" width="1200" height="900" fetchPriority="high" />
        </div>
        <RoomGallery />
        <EquipmentCatalog />
      </main>
      {hours && (
        <footer className="home-hours">
          <strong>Opening hours</strong>
          <span>Daily {hours.opens_at}–{hours.closes_at} Bangkok time.</span>
        </footer>
      )}
    </div>
  )
}
