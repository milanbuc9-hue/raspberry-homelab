'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

interface FoodEntry {
  id: number
  name: string
  calories: number
  protein: number
  carbs: number
  fat: number
  date: string
}

const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${localStorage.getItem('access_token')}`,
})

const today = () => new Date().toISOString().slice(0, 10)

export default function CaloriesPage() {
  const router = useRouter()
  const [date, setDate] = useState(today())
  const [entries, setEntries] = useState<FoodEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', calories: 0, protein: 0, carbs: 0, fat: 0 })

  const fetchEntries = useCallback(async (d: string) => {
    setLoading(true)
    const res = await fetch(`/api/food?date=${d}`, { headers: authHeaders() })
    if (res.status === 401) { router.push('/login'); return }
    const data = await res.json()
    setEntries(data.entries || [])
    setLoading(false)
  }, [router])

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('access_token')) {
      router.push('/login')
      return
    }
    fetchEntries(date)
  }, [date, fetchEntries, router])

  async function addEntry(e: React.FormEvent) {
    e.preventDefault()
    const res = await fetch('/api/food', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ ...form, date }),
    })
    if (res.ok) {
      setShowForm(false)
      setForm({ name: '', calories: 0, protein: 0, carbs: 0, fat: 0 })
      fetchEntries(date)
    }
  }

  async function deleteEntry(id: number) {
    await fetch(`/api/food/${id}`, { method: 'DELETE', headers: authHeaders() })
    fetchEntries(date)
  }

  const totals = entries.reduce(
    (acc, e) => ({
      calories: acc.calories + e.calories,
      protein: acc.protein + e.protein,
      carbs: acc.carbs + e.carbs,
      fat: acc.fat + e.fat,
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0 }
  )

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">Kalorien</h1>
        <input
          type="date"
          value={date}
          onChange={e => setDate(e.target.value)}
          className="bg-gray-800 text-white rounded-lg px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
      </header>

      <div className="max-w-2xl mx-auto p-4 space-y-4">
        {/* Daily totals */}
        <div className="bg-gray-900 rounded-2xl p-4 grid grid-cols-4 gap-3 text-center">
          <div>
            <div className="text-2xl font-bold text-orange-400">{Math.round(totals.calories)}</div>
            <div className="text-xs text-gray-400 mt-0.5">kcal</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-blue-400">{totals.protein.toFixed(1)}g</div>
            <div className="text-xs text-gray-400 mt-0.5">Protein</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-yellow-400">{totals.carbs.toFixed(1)}g</div>
            <div className="text-xs text-gray-400 mt-0.5">Carbs</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-red-400">{totals.fat.toFixed(1)}g</div>
            <div className="text-xs text-gray-400 mt-0.5">Fett</div>
          </div>
        </div>

        {/* Add button */}
        <div className="flex justify-end">
          <button
            onClick={() => setShowForm(v => !v)}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg transition-colors"
          >
            + Hinzufügen
          </button>
        </div>

        {/* Add form */}
        {showForm && (
          <form onSubmit={addEntry} className="bg-gray-900 rounded-2xl p-4 space-y-3">
            <input
              type="text"
              placeholder="Lebensmittel"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500"
              required
              autoFocus
            />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Kalorien (kcal)</label>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={form.calories}
                  onChange={e => setForm(f => ({ ...f, calories: Number(e.target.value) }))}
                  className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Protein (g)</label>
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={form.protein}
                  onChange={e => setForm(f => ({ ...f, protein: Number(e.target.value) }))}
                  className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Carbs (g)</label>
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={form.carbs}
                  onChange={e => setForm(f => ({ ...f, carbs: Number(e.target.value) }))}
                  className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Fett (g)</label>
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={form.fat}
                  onChange={e => setForm(f => ({ ...f, fat: Number(e.target.value) }))}
                  className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" className="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-sm py-2 rounded-lg transition-colors">
                Speichern
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="flex-1 bg-gray-700 hover:bg-gray-600 text-white text-sm py-2 rounded-lg transition-colors">
                Abbrechen
              </button>
            </div>
          </form>
        )}

        {/* Entries list */}
        {loading ? (
          <div className="text-gray-400 text-center py-8">Loading...</div>
        ) : entries.length === 0 ? (
          <div className="bg-gray-900 rounded-2xl p-8 text-center text-gray-500">
            Keine Einträge für diesen Tag.
          </div>
        ) : (
          <div className="space-y-2">
            {entries.map(entry => (
              <div key={entry.id} className="bg-gray-900 rounded-xl px-4 py-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-white">{entry.name}</div>
                  <div className="text-xs text-gray-400 mt-0.5 flex gap-3">
                    <span className="text-orange-400">{entry.calories} kcal</span>
                    <span>P: {entry.protein}g</span>
                    <span>C: {entry.carbs}g</span>
                    <span>F: {entry.fat}g</span>
                  </div>
                </div>
                <button
                  onClick={() => deleteEntry(entry.id)}
                  className="text-gray-600 hover:text-red-400 transition-colors text-lg leading-none ml-3"
                  aria-label="Löschen"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
