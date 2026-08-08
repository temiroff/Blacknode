import { useEffect, useState } from 'react'

import { api } from '../api'

type VerificationState = 'checking' | 'verified' | 'invalid'

function fragmentToken(): string {
  const fragment = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash
  return new URLSearchParams(fragment).get('token')?.trim() ?? ''
}

export default function EmailVerificationPage() {
  const [state, setState] = useState<VerificationState>('checking')
  const [message, setMessage] = useState('Verifying your Blacknode Cloud email…')

  useEffect(() => {
    const token = fragmentToken()
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
    if (!token) {
      setState('invalid')
      setMessage('This verification link is missing its secure token.')
      return
    }
    let cancelled = false
    void api.verifyCloudEmail(token)
      .then(result => {
        if (cancelled) return
        setState('verified')
        setMessage(`${result.account.email} is verified.`)
      })
      .catch(error => {
        if (cancelled) return
        setState('invalid')
        setMessage(error instanceof Error ? error.message : 'This verification link is invalid or expired.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="bn-cloud-verification-page">
      <section className={`bn-cloud-verification-card is-${state}`} aria-live="polite">
        <div className="bn-cloud-verification-mark" aria-hidden="true">BN</div>
        <p className="bn-cloud-verification-eyebrow">Blacknode Robotics</p>
        <h1>{state === 'verified' ? 'Email verified' : state === 'invalid' ? 'Verification failed' : 'Verifying email'}</h1>
        <p>{message}</p>
        {state === 'verified' && <p>You can close this page and return to the Blacknode Editor.</p>}
        {state === 'invalid' && <p>Request a new verification email from your Cloud account settings.</p>}
      </section>
    </main>
  )
}
