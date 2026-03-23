'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

interface Exercise {
  id: number
  name: string
  sets: number
  reps: number
  weight: number
  notes: string | null
}

interface Workout {
  id: number
  name: string
  date: string
  notes: string | null
  exercise_count: number
  exercises?: Exercise[]
}

function getToken() {
  return typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
}

function authHeaders() {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` }
}

export default function DashboardPage() {
  const router = useRouter()
  const [workouts, setWorkouts] = useState<Workout[]>([])
  const [selected, setSelected] = useState<Workout | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [newWorkout, setNewWorkout] = useState({ name: '', date: new Date().toISOString().slice(0, 10), notes: '' })
  const [newExercise, setNewExercise] = useState({ name: '', sets: 3, reps: 10, weight: 0, notes: '' })
  const [addingEx, setAddingEx] = useState(false)

  const fetchWorkouts = useCallback(async () => {
    const res = await fetch('/api/workouts', { headers: authHeaders() })
    if (res.status === 401) { router.push('/login'); return }
    const data = await res.json()
    setWorkouts(data.workouts || [])
    setLoading(false)
  }, [router])

  useEffect(() => {
    if (!getToken()) { router.push('/login'); return }
    fetchWorkouts()
  }, [fetchWorkouts, router])

  async function openWorkout(id: number) {
    const res = await fetch(`/api/workouts/${id}`, { headers: authHeaders() })
    const data = await res.json()
    setSelected(data)
  }

  async function createWorkout(e: React.FormEvent) {
    e.preventDefault()
    const res = await fetch('/api/workouts', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(newWorkout),
    })
    if (res.ok) {
      setShowNew(false)
      setNewWorkout({ name: '', date: new Date().toISOString().slice(0, 10), notes: '' })
      fetchWorkouts()
    }
  }

  async function deleteWorkout(id: number) {
    if (!confirm('Delete this workout?')) return
    await fetch(`/api/workouts/${id}`, { method: 'DELETE', headers: authHeaders() })
    setSelected(null)
    fetchWorkouts()
  }

  async function addExercise(e: React.FormEvent) {
    e.preventDefault()
    if (!selected) return
    const res = await fetch(`/api/workouts/${selected.id}/exercises`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(newExercise),
    })
    if (res.ok) {
      setAddingEx(false)
      setNewExercise({ name: '', sets: 3, reps: 10, weight: 0, notes: '' })
      openWorkout(selected.id)
    }
  }

  function logout() {
    fetch('/api/auth/logout', { method: 'POST', headers: authHeaders() }).catch(() => {})
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    router.push('/login')
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
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">Gym Tracker</h1>
        <button onClick={logout} className="text-gray-400 hover:text-white text-sm transition-colors">
          Logout
        </button>
      </header>

      <div className="max-w-4xl mx-auto p-4 flex flex-col gap-4 md:flex-row">
        <div className="md:w-72 shrink-0 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-300">Workouts</h2>
            <button
              onClick={() => setShowNew(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
            >
              + New
            </button>
          </div>

          {showNew && (
            <form onSubmit={createWorkout} className="bg-gray-900 rounded-xl p-4 space-y-3">
              <input
                type="text"
                placeholder="Workout name"
                value={newWorkout.name}
                onChange={e => setNewWorkout(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500"
                required
                autoFocus
              />
              <input
                type="date"
                value={newWorkout.date}
                onChange={e => setNewWorkout(f => ({ ...f, date: e.target.value }))}
                className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
              />
              <textarea
                placeholder="Notes (optional)"
                value={newWorkout.notes}
                onChange={e => setNewWorkout(f => ({ ...f, notes: e.target.value }))}
                className="w-full bg-gray-800 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500 resize-none"
                rows={2}
              />
              <div className="flex gap-2">
                <button type="submit" className="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-sm py-2 rounded-lg transition-colors">
                  Create
                </button>
                <button type="button" onClick={() => setShowNew(false)} className="flex-1 bg-gray-700 hover:bg-gray-600 text-white text-sm py-2 rounded-lg transition-colors">
                  Cancel
                </button>
              </div>
            </form>
          )}

          {workouts.length === 0 ? (
            <p className="text-gray-500 text-sm">No workouts yet.</p>
          ) : (
            workouts.map(w => (
              <button
                key={w.id}
                onClick={() => openWorkout(w.id)}
                className={`w-full text-left bg-gray-900 hover:bg-gray-800 rounded-xl p-4 transition-colors border ${selected?.id === w.id ? 'border-blue-500' : 'border-transparent'}`}
              >
                <div className="font-medium text-white">{w.name}</div>
                <div className="text-xs text-gray-500 mt-1 flex justify-between">
                  <span>{w.date}</span>
                  <span>{w.exercise_count} exercises</span>
                </div>
              </button>
            ))
          )}
        </div>

        <div className="flex-1">
          {!selected ? (
            <div className="bg-gray-900 rounded-2xl p-8 text-center text-gray-500">
              Select a workout to view details
            </div>
          ) : (
            <div className="bg-gray-900 rounded-2xl p-6 space-y-5">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-bold">{selected.name}</h2>
                  <p className="text-gray-400 text-sm mt-1">{selected.date}</p>
                  {selected.notes && <p className="text-gray-400 text-sm mt-1">{selected.notes}</p>}
                </div>
                <button
                  onClick={() => deleteWorkout(selected.id)}
                  className="text-red-400 hover:text-red-300 text-sm transition-colors"
                >
                  Delete
                </button>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-gray-300">Exercises</h3>
                  <button
                    onClick={() => setAddingEx(true)}
                    className="bg-green-600 hover:bg-green-700 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
                  >
                    + Add
                  </button>
                </div>

                {addingEx && (
                  <form onSubmit={addExercise} className="bg-gray-800 rounded-xl p-4 space-y-3">
                    <input
                      type="text"
                      placeholder="Exercise name"
                      value={newExercise.name}
                      onChange={e => setNewExercise(f => ({ ...f, name: e.target.value }))}
                      className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-green-500 placeholder-gray-500"
                      required
                      autoFocus
                    />
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <label className="text-xs text-gray-400">Sets</label>
                        <input type="number" min={0} value={newExercise.sets} onChange={e => setNewExercise(f => ({ ...f, sets: Number(e.target.value) }))} className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-green-500" />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Reps</label>
                        <input type="number" min={0} value={newExercise.reps} onChange={e => setNewExercise(f => ({ ...f, reps: Number(e.target.value) }))} className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-green-500" />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400">Weight (kg)</label>
                        <input type="number" min={0} step={0.5} value={newExercise.weight} onChange={e => setNewExercise(f => ({ ...f, weight: Number(e.target.value) }))} className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-green-500" />
                      </div>
                    </div>
                    <input type="text" placeholder="Notes (optional)" value={newExercise.notes} onChange={e => setNewExercise(f => ({ ...f, notes: e.target.value }))} className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-green-500 placeholder-gray-500" />
                    <div className="flex gap-2">
                      <button type="submit" className="flex-1 bg-green-600 hover:bg-green-700 text-white text-sm py-2 rounded-lg transition-colors">Add</button>
                      <button type="button" onClick={() => setAddingEx(false)} className="flex-1 bg-gray-700 hover:bg-gray-600 text-white text-sm py-2 rounded-lg transition-colors">Cancel</button>
                    </div>
                  </form>
                )}

                {(!selected.exercises || selected.exercises.length === 0) ? (
                  <p className="text-gray-500 text-sm">No exercises yet.</p>
                ) : (
                  selected.exercises.map((ex, i) => (
                    <div key={ex.id} className="bg-gray-800 rounded-xl p-4">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{i + 1}. {ex.name}</span>
                        <div className="text-sm text-gray-400 flex gap-3">
                          <span>{ex.sets} × {ex.reps}</span>
                          {ex.weight > 0 && <span>{ex.weight} kg</span>}
                        </div>
                      </div>
                      {ex.notes && <p className="text-xs text-gray-500 mt-1">{ex.notes}</p>}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
