'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

interface AdminUser {
  id: number
  username: string
  email: string
  created_at: string
  is_active: number
  is_admin: number
}

const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${localStorage.getItem('access_token')}`,
})

export default function AdminPage() {
  const router = useRouter()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [forbidden, setForbidden] = useState(false)

  async function fetchUsers() {
    const res = await fetch('/api/admin/users', { headers: authHeaders() })
    if (res.status === 401) { router.push('/login'); return }
    if (res.status === 403) { setForbidden(true); setLoading(false); return }
    const data = await res.json()
    setUsers(data.users || [])
    setLoading(false)
  }

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('access_token')) {
      router.push('/login')
      return
    }
    fetchUsers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function toggleActive(id: number, current: number) {
    await fetch(`/api/admin/users/${id}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ is_active: current === 1 ? 0 : 1 }),
    })
    fetchUsers()
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    )
  }

  if (forbidden) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="bg-gray-900 rounded-2xl p-8 text-center space-y-2">
          <div className="text-4xl">🚫</div>
          <div className="text-xl font-bold text-red-400">Kein Zugriff</div>
          <div className="text-gray-400 text-sm">Du hast keine Admin-Rechte.</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-4">
        <h1 className="text-xl font-bold">Admin – Benutzerverwaltung</h1>
      </header>

      <div className="max-w-4xl mx-auto p-4">
        <div className="bg-gray-900 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400">
                  <th className="text-left px-4 py-3 font-medium">ID</th>
                  <th className="text-left px-4 py-3 font-medium">Benutzername</th>
                  <th className="text-left px-4 py-3 font-medium">E-Mail</th>
                  <th className="text-left px-4 py-3 font-medium">Registriert</th>
                  <th className="text-left px-4 py-3 font-medium">Admin</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {users.map(user => (
                  <tr key={user.id} className="border-b border-gray-800 last:border-0 hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3 text-gray-500">{user.id}</td>
                    <td className="px-4 py-3 font-medium">{user.username}</td>
                    <td className="px-4 py-3 text-gray-400">{user.email}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(user.created_at).toLocaleDateString('de-DE')}
                    </td>
                    <td className="px-4 py-3">
                      {user.is_admin === 1 ? (
                        <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded-full">Admin</span>
                      ) : (
                        <span className="text-gray-600">–</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        user.is_active === 1
                          ? 'bg-green-500/20 text-green-300'
                          : 'bg-red-500/20 text-red-300'
                      }`}>
                        {user.is_active === 1 ? 'Aktiv' : 'Inaktiv'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => toggleActive(user.id, user.is_active)}
                        className={`text-xs px-3 py-1 rounded-lg transition-colors ${
                          user.is_active === 1
                            ? 'bg-red-600/20 hover:bg-red-600/40 text-red-300'
                            : 'bg-green-600/20 hover:bg-green-600/40 text-green-300'
                        }`}
                      >
                        {user.is_active === 1 ? 'Deaktivieren' : 'Aktivieren'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
