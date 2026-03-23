import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'

export async function GET(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const db = getDb()
  const { searchParams } = new URL(req.url)
  const date = searchParams.get('date')

  const entries = date
    ? db.prepare('SELECT * FROM food_log WHERE user_id=? AND date=? ORDER BY id DESC').all(user.sub, date)
    : db.prepare('SELECT * FROM food_log WHERE user_id=? ORDER BY id DESC').all(user.sub)

  return NextResponse.json({ entries })
}

export async function POST(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({}))
  const { name, calories, protein, carbs, fat, date } = body
  if (!name) return NextResponse.json({ error: 'name is required' }, { status: 400 })

  const db = getDb()
  const result = db.prepare(
    'INSERT INTO food_log (user_id, name, calories, protein, carbs, fat, date) VALUES (?, ?, ?, ?, ?, ?, ?)'
  ).run(user.sub, name, calories ?? 0, protein ?? 0, carbs ?? 0, fat ?? 0, date ?? new Date().toISOString().slice(0, 10))

  const entry = db.prepare('SELECT * FROM food_log WHERE id=?').get(result.lastInsertRowid)
  return NextResponse.json({ entry }, { status: 201 })
}
