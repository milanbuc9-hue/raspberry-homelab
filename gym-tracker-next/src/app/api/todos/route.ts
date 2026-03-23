import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'

export async function GET(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const db = getDb()
  const { searchParams } = new URL(req.url)
  const type = searchParams.get('type')

  const todos = type === 'personal'
    ? db.prepare('SELECT id, text, is_done FROM personal_todos WHERE user_id=? ORDER BY id DESC').all(user.sub)
    : db.prepare("SELECT id, text, is_done, author FROM todos WHERE type='suggestion' ORDER BY id DESC").all()

  return NextResponse.json({ todos })
}

export async function POST(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({}))
  const text = (body.text || '').trim()
  if (!text) return NextResponse.json({ error: 'text is required' }, { status: 400 })

  const db = getDb()

  if (body.type === 'personal') {
    const result = db.prepare('INSERT INTO personal_todos (user_id, text, is_done) VALUES (?, ?, 0)').run(user.sub, text)
    const todo = db.prepare('SELECT * FROM personal_todos WHERE id=?').get(result.lastInsertRowid)
    return NextResponse.json({ todo }, { status: 201 })
  } else {
    const result = db.prepare(
      "INSERT INTO todos (text, type, author, created_by, is_done) VALUES (?, 'suggestion', ?, ?, 0)"
    ).run(text, user.username, user.sub)
    const todo = db.prepare('SELECT * FROM todos WHERE id=?').get(result.lastInsertRowid)
    return NextResponse.json({ todo }, { status: 201 })
  }
}
