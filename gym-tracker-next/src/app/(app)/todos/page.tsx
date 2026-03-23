'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

interface Todo {
  id: number
  text: string
  is_done: boolean
  type?: string
}

const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${localStorage.getItem('access_token')}`,
})

export default function TodosPage() {
  const router = useRouter()
  const [tab, setTab] = useState<'personal' | 'shared'>('personal')
  const [personalTodos, setPersonalTodos] = useState<Todo[]>([])
  const [sharedTodos, setSharedTodos] = useState<Todo[]>([])
  const [loading, setLoading] = useState(true)
  const [newText, setNewText] = useState('')

  const fetchTodos = useCallback(async () => {
    setLoading(true)
    const [pRes, sRes] = await Promise.all([
      fetch('/api/todos?type=personal', { headers: authHeaders() }),
      fetch('/api/todos?type=shared', { headers: authHeaders() }),
    ])
    if (pRes.status === 401) { router.push('/login'); return }
    const [pData, sData] = await Promise.all([pRes.json(), sRes.json()])
    setPersonalTodos(pData.todos || [])
    setSharedTodos(sData.todos || [])
    setLoading(false)
  }, [router])

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('access_token')) {
      router.push('/login')
      return
    }
    fetchTodos()
  }, [fetchTodos, router])

  async function addTodo(e: React.FormEvent) {
    e.preventDefault()
    if (!newText.trim()) return
    const res = await fetch('/api/todos', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ text: newText.trim(), type: tab === 'personal' ? 'personal' : 'suggestion' }),
    })
    if (res.ok) {
      setNewText('')
      fetchTodos()
    }
  }

  async function toggleTodo(id: number, is_done: boolean) {
    await fetch(`/api/todos/${id}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ is_done: !is_done }),
    })
    fetchTodos()
  }

  async function deleteTodo(id: number) {
    await fetch(`/api/todos/${id}`, { method: 'DELETE', headers: authHeaders() })
    fetchTodos()
  }

  const todos = tab === 'personal' ? personalTodos : sharedTodos

  function TodoList({ items }: { items: Todo[] }) {
    if (items.length === 0) return <p className="text-gray-500 text-sm py-4 text-center">Keine Todos.</p>
    return (
      <ul className="space-y-2">
        {items.map(todo => (
          <li key={todo.id} className="bg-gray-900 rounded-xl px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => toggleTodo(todo.id, todo.is_done)}
              className={`w-5 h-5 rounded border-2 flex items-center justify-center shrink-0 transition-colors ${
                todo.is_done ? 'bg-green-600 border-green-600' : 'border-gray-600 hover:border-green-500'
              }`}
              aria-label="Toggle"
            >
              {todo.is_done && <span className="text-white text-xs leading-none">✓</span>}
            </button>
            <span className={`flex-1 text-sm ${todo.is_done ? 'line-through text-gray-500' : 'text-white'}`}>
              {todo.text}
            </span>
            <button
              onClick={() => deleteTodo(todo.id)}
              className="text-gray-600 hover:text-red-400 transition-colors text-lg leading-none"
              aria-label="Löschen"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-4">
        <h1 className="text-xl font-bold">Todos</h1>
      </header>

      <div className="max-w-xl mx-auto p-4 space-y-4">
        {/* Tabs */}
        <div className="flex bg-gray-900 rounded-xl p-1 gap-1">
          <button
            onClick={() => setTab('personal')}
            className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'personal' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Persönlich
          </button>
          <button
            onClick={() => setTab('shared')}
            className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'shared' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Geteilt
          </button>
        </div>

        {/* Add form */}
        <form onSubmit={addTodo} className="flex gap-2">
          <input
            type="text"
            placeholder={tab === 'personal' ? 'Neues Todo...' : 'Neuer Vorschlag...'}
            value={newText}
            onChange={e => setNewText(e.target.value)}
            className="flex-1 bg-gray-900 text-white rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500"
          />
          <button
            type="submit"
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-xl transition-colors"
          >
            + Hinzu
          </button>
        </form>

        {loading ? (
          <div className="text-gray-400 text-center py-8">Loading...</div>
        ) : (
          <TodoList items={todos} />
        )}
      </div>
    </div>
  )
}
