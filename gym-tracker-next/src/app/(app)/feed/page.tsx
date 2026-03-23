'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

interface Post {
  id: number
  author: string
  caption: string
  calories: number
  protein: number
  carbs: number
  fat: number
  created_at: string
}

const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${localStorage.getItem('access_token')}`,
})

function formatDate(dt: string) {
  return new Date(dt).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function FeedPage() {
  const router = useRouter()
  const [posts, setPosts] = useState<Post[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ caption: '', calories: 0, protein: 0, carbs: 0, fat: 0 })
  const [submitting, setSubmitting] = useState(false)

  const fetchPosts = useCallback(async () => {
    const res = await fetch('/api/feed', { headers: authHeaders() })
    if (res.status === 401) { router.push('/login'); return }
    const data = await res.json()
    setPosts(data.posts || [])
    setLoading(false)
  }, [router])

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('access_token')) {
      router.push('/login')
      return
    }
    fetchPosts()
  }, [fetchPosts, router])

  async function createPost(e: React.FormEvent) {
    e.preventDefault()
    if (!form.caption.trim()) return
    setSubmitting(true)
    const res = await fetch('/api/feed', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(form),
    })
    setSubmitting(false)
    if (res.ok) {
      setShowForm(false)
      setForm({ caption: '', calories: 0, protein: 0, carbs: 0, fat: 0 })
      fetchPosts()
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">Feed</h1>
        <button
          onClick={() => setShowForm(v => !v)}
          className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
        >
          + Post
        </button>
      </header>

      <div className="max-w-xl mx-auto p-4 space-y-4">
        {/* New post form */}
        {showForm && (
          <form onSubmit={createPost} className="bg-gray-900 rounded-2xl p-4 space-y-3">
            <textarea
              placeholder="Was hast du heute gemacht?"
              value={form.caption}
              onChange={e => setForm(f => ({ ...f, caption: e.target.value }))}
              className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500 resize-none"
              rows={3}
              required
              autoFocus
            />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Kalorien (optional)</label>
                <input
                  type="number"
                  min={0}
                  value={form.calories || ''}
                  placeholder="0"
                  onChange={e => setForm(f => ({ ...f, calories: Number(e.target.value) }))}
                  className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Protein (g)</label>
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={form.protein || ''}
                  placeholder="0"
                  onChange={e => setForm(f => ({ ...f, protein: Number(e.target.value) }))}
                  className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Carbs (g)</label>
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={form.carbs || ''}
                  placeholder="0"
                  onChange={e => setForm(f => ({ ...f, carbs: Number(e.target.value) }))}
                  className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Fett (g)</label>
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={form.fat || ''}
                  placeholder="0"
                  onChange={e => setForm(f => ({ ...f, fat: Number(e.target.value) }))}
                  className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-600"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={submitting}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-2 rounded-lg transition-colors"
              >
                {submitting ? 'Posten...' : 'Posten'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="flex-1 bg-gray-700 hover:bg-gray-600 text-white text-sm py-2 rounded-lg transition-colors"
              >
                Abbrechen
              </button>
            </div>
          </form>
        )}

        {/* Posts */}
        {loading ? (
          <div className="text-gray-400 text-center py-8">Loading...</div>
        ) : posts.length === 0 ? (
          <div className="bg-gray-900 rounded-2xl p-8 text-center text-gray-500">
            Noch keine Posts. Sei der Erste!
          </div>
        ) : (
          posts.map(post => (
            <div key={post.id} className="bg-gray-900 rounded-2xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-sm font-bold">
                    {post.author?.[0]?.toUpperCase() ?? '?'}
                  </div>
                  <span className="font-medium text-sm">{post.author}</span>
                </div>
                <span className="text-xs text-gray-500">{formatDate(post.created_at)}</span>
              </div>
              <p className="text-gray-200 text-sm leading-relaxed">{post.caption}</p>
              {(post.calories > 0 || post.protein > 0 || post.carbs > 0 || post.fat > 0) && (
                <div className="flex flex-wrap gap-2">
                  {post.calories > 0 && (
                    <span className="text-xs bg-orange-500/20 text-orange-300 px-2.5 py-1 rounded-full">
                      {post.calories} kcal
                    </span>
                  )}
                  {post.protein > 0 && (
                    <span className="text-xs bg-blue-500/20 text-blue-300 px-2.5 py-1 rounded-full">
                      {post.protein}g Protein
                    </span>
                  )}
                  {post.carbs > 0 && (
                    <span className="text-xs bg-yellow-500/20 text-yellow-300 px-2.5 py-1 rounded-full">
                      {post.carbs}g Carbs
                    </span>
                  )}
                  {post.fat > 0 && (
                    <span className="text-xs bg-red-500/20 text-red-300 px-2.5 py-1 rounded-full">
                      {post.fat}g Fett
                    </span>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
