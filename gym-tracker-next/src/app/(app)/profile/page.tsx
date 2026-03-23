'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

interface Profile {
  id: number
  username: string
  email: string
  created_at: string
}

const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${localStorage.getItem('access_token')}`,
})

export default function ProfilePage() {
  const router = useRouter()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)

  // Email form
  const [email, setEmail] = useState('')
  const [emailMsg, setEmailMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [emailSaving, setEmailSaving] = useState(false)

  // Password form
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm: '' })
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [pwSaving, setPwSaving] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('access_token')) {
      router.push('/login')
      return
    }
    fetch('/api/profile', { headers: authHeaders() })
      .then(res => {
        if (res.status === 401) { router.push('/login'); return null }
        return res.json()
      })
      .then(data => {
        if (data?.user) {
          setProfile(data.user)
          setEmail(data.user.email)
        }
        setLoading(false)
      })
  }, [router])

  async function saveEmail(e: React.FormEvent) {
    e.preventDefault()
    setEmailMsg(null)
    setEmailSaving(true)
    const res = await fetch('/api/profile', {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ email }),
    })
    const data = await res.json()
    setEmailSaving(false)
    if (res.ok) {
      setProfile(p => p ? { ...p, email: data.user?.email ?? email } : p)
      setEmailMsg({ ok: true, text: 'E-Mail aktualisiert.' })
    } else {
      setEmailMsg({ ok: false, text: data.error || 'Fehler beim Speichern.' })
    }
  }

  async function savePassword(e: React.FormEvent) {
    e.preventDefault()
    setPwMsg(null)
    if (pwForm.new_password !== pwForm.confirm) {
      setPwMsg({ ok: false, text: 'Passwörter stimmen nicht überein.' })
      return
    }
    if (pwForm.new_password.length < 6) {
      setPwMsg({ ok: false, text: 'Passwort muss mind. 6 Zeichen haben.' })
      return
    }
    setPwSaving(true)
    const res = await fetch('/api/profile/password', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ current_password: pwForm.current_password, new_password: pwForm.new_password }),
    })
    const data = await res.json()
    setPwSaving(false)
    if (res.ok) {
      setPwForm({ current_password: '', new_password: '', confirm: '' })
      setPwMsg({ ok: true, text: 'Passwort geändert.' })
    } else {
      setPwMsg({ ok: false, text: data.error || 'Fehler beim Ändern.' })
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-4">
        <h1 className="text-xl font-bold">Profil</h1>
      </header>

      <div className="max-w-lg mx-auto p-4 space-y-5">
        {/* Profile info card */}
        <div className="bg-gray-900 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-blue-600 flex items-center justify-center text-2xl font-bold">
              {profile?.username?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div>
              <div className="font-bold text-lg">{profile?.username}</div>
              <div className="text-gray-400 text-sm">{profile?.email}</div>
              <div className="text-gray-500 text-xs mt-0.5">
                Dabei seit {profile?.created_at ? new Date(profile.created_at).toLocaleDateString('de-DE') : ''}
              </div>
            </div>
          </div>
        </div>

        {/* Update email */}
        <div className="bg-gray-900 rounded-2xl p-5 space-y-4">
          <h2 className="font-semibold text-gray-200">E-Mail ändern</h2>
          <form onSubmit={saveEmail} className="space-y-3">
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
            {emailMsg && (
              <p className={`text-sm ${emailMsg.ok ? 'text-green-400' : 'text-red-400'}`}>{emailMsg.text}</p>
            )}
            <button
              type="submit"
              disabled={emailSaving}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-2 rounded-lg transition-colors"
            >
              {emailSaving ? 'Speichern...' : 'Speichern'}
            </button>
          </form>
        </div>

        {/* Change password */}
        <div className="bg-gray-900 rounded-2xl p-5 space-y-4">
          <h2 className="font-semibold text-gray-200">Passwort ändern</h2>
          <form onSubmit={savePassword} className="space-y-3">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Aktuelles Passwort</label>
              <input
                type="password"
                value={pwForm.current_password}
                onChange={e => setPwForm(f => ({ ...f, current_password: e.target.value }))}
                className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Neues Passwort</label>
              <input
                type="password"
                value={pwForm.new_password}
                onChange={e => setPwForm(f => ({ ...f, new_password: e.target.value }))}
                className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                required
                minLength={6}
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Passwort bestätigen</label>
              <input
                type="password"
                value={pwForm.confirm}
                onChange={e => setPwForm(f => ({ ...f, confirm: e.target.value }))}
                className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            {pwMsg && (
              <p className={`text-sm ${pwMsg.ok ? 'text-green-400' : 'text-red-400'}`}>{pwMsg.text}</p>
            )}
            <button
              type="submit"
              disabled={pwSaving}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-2 rounded-lg transition-colors"
            >
              {pwSaving ? 'Ändern...' : 'Passwort ändern'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
