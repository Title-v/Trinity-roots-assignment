import { useState } from 'react'
import './App.css'

function App() {
  const [message, setMessage] = useState('ยังไม่ได้ตรวจสอบ')
  const [loading, setLoading] = useState(false)

  async function checkBackend() {
    setLoading(true)
    setMessage('กำลังเชื่อมต่อ...')

    try {
      const response = await fetch('/api/health/db', {
        signal: AbortSignal.timeout(10000),
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const data = await response.json()
      if (data?.status !== 'ok' || data.database !== 'connected') {
        throw new Error('รูปแบบคำตอบจาก Backend ไม่ตรงที่คาดไว้')
      }
      setMessage('เชื่อมต่อ FastAPI และ Neon สำเร็จ')
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Unknown error'
      setMessage(`เชื่อมต่อไม่สำเร็จ: ${detail}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main id="center">
      <h1>Resource Booking</h1>
      <p>ระบบจองห้องและอุปกรณ์</p>
      <button
        type="button"
        className="counter"
        onClick={checkBackend}
        disabled={loading}
      >
        {loading ? 'กำลังตรวจสอบ...' : 'ตรวจสอบ Backend'}
      </button>
      <p role="status">{message}</p>
    </main>
  )
}

export default App
