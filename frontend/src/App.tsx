import { useEffect, useState, type FormEvent } from 'react'
import { BusinessHours } from './BusinessHours'
import { HomePage } from './HomePage'
import './App.css'

type Account = { id: number; email: string }
type Mode = 'login' | 'register'

function App() {
  const [showAuth, setShowAuth] = useState(false)
  const [mode, setMode] = useState<Mode>('login')
  const [account, setAccount] = useState<Account | null>(null)
  const [checking, setChecking] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [email, setEmail] = useState('')
  const registering = mode === 'register'

  useEffect(() => {
    const controller = new AbortController()
    async function loadAccount() {
      try {
        const response = await fetch('/api/auth/me', { signal: controller.signal })
        if (response.ok) setAccount(await response.json())
      } catch {
        if (!controller.signal.aborted) setError('Could not connect. Try again.')
      } finally {
        if (!controller.signal.aborted) setChecking(false)
      }
    }
    void loadAccount()
    return () => controller.abort()
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    const password = data.get('password')
    if (registering && password !== data.get('confirm')) {
      setError('Passwords do not match.')
      return
    }
    setPending(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/auth/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        signal: AbortSignal.timeout(10000),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(typeof body.detail === 'string' ? body.detail : 'Check your details and try again.')
      }
      if (registering) {
        setMode('login')
        setNotice('Account created. Sign in to continue.')
      } else {
        setAccount(await response.json())
      }
      form.reset()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Please try again.')
    } finally {
      setPending(false)
    }
  }

  async function signOut() {
    setPending(true)
    setError('')
    try {
      const response = await fetch('/api/auth/logout', { method: 'POST', signal: AbortSignal.timeout(10000) })
      if (!response.ok) throw new Error()
      setAccount(null)
      setShowAuth(false)
    } catch {
      setError('Could not sign out. Try again.')
    } finally {
      setPending(false)
    }
  }

  function openAuth(nextMode: Mode) {
    setMode(nextMode)
    setError('')
    setNotice('')
    setShowAuth(true)
  }

  if (!checking && !account && !showAuth) {
    return <HomePage onSignIn={() => openAuth('login')} onRegister={() => openAuth('register')} />
  }

  return (
    <main className={account ? 'auth-page' : 'auth-page auth-entry'}>
      <section className="auth-card" aria-labelledby="auth-title">
        {!checking && !account && (
          <button type="button" className="auth-home-link" disabled={pending} onClick={() => setShowAuth(false)}>← Home</button>
        )}
        <div className="auth-brand">Trinity Roots</div>
        <h1 id="auth-title">{checking ? 'Resource Booking' : account ? 'You’re signed in' : registering ? 'Create account' : 'Sign in'}</h1>
        {checking ? (
          <p role="status">Checking your session…</p>
        ) : account ? (
          <>
            <p className="account-email">{account.email}</p>
            <BusinessHours />
            <button className="auth-primary" type="button" disabled={pending} onClick={signOut}>Sign out</button>
          </>
        ) : (
          <>
            <form key={mode} onSubmit={submit} className="auth-form">
              <label htmlFor="email">Email</label>
              <input id="email" name="email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} required />
              <label htmlFor="password">Password</label>
              <input id="password" name="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'} minLength={registering ? 8 : undefined} maxLength={128} aria-describedby={registering ? 'password-hint' : undefined} required />
              {registering && (
                <>
                  <small id="password-hint">Use at least 8 characters.</small>
                  <label htmlFor="confirm">Confirm password</label>
                  <input id="confirm" name="confirm" type="password" autoComplete="new-password" maxLength={128} required />
                </>
              )}
              <button className="auth-primary" disabled={pending}>{pending ? 'Please wait…' : registering ? 'Create account' : 'Sign in'}</button>
            </form>
            <p className="auth-switch">
              {registering ? 'Already have an account?' : 'New to Trinity Roots?'}{' '}
              <button type="button" disabled={pending} onClick={() => {
                setMode(registering ? 'login' : 'register')
                setError('')
                setNotice('')
              }}>{registering ? 'Sign in' : 'Create account'}</button>
            </p>
          </>
        )}
        {notice && <p className="auth-feedback" role="status">{notice}</p>}
        {error && <p className="auth-feedback auth-error" role="alert">{error}</p>}
      </section>
      {!checking && !account && (
        <img
          className="auth-photo"
          src={`${import.meta.env.BASE_URL}meeting-room.webp`}
          alt=""
          width="1200"
          height="900"
        />
      )}
    </main>
  )
}

export default App
