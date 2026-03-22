'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

export default function LoginPage() {
  const router = useRouter()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()

      if (!res.ok) {
        setError(data.error || 'Login failed')
        return
      }

      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      router.push('/dashboard')
    } catch {
      setError('Network error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-bold text-white mb-8 text-center">Gym Tracker</h1>

        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-2xl p-6 space-y-4">
          <h2 className="text-lg font-semibold text-white">Login</h2>

          {error && (
            <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-3 py-2 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-3">
            <input
              type="text"
              placeholder="Username"
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
              className="w-full bg-gray-800 text-white rounded-lg px-4 py-3 outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500"
              required
            />
            <input
              type="password"
              placeholder="Password"
              value={form.password}
              onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
              className="w-full bg-gray-800 text-white rounded-lg px-4 py-3 outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-lg py-3 transition-colors"
          >
            {loading ? 'Logging in...' : 'Login'}
          </button>

          <p className="text-center text-gray-500 text-sm">
            No account?{' '}
            <Link href="/register" className="text-blue-400 hover:underline">Register</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
