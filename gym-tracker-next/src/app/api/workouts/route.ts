import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'
import { auditLog } from '@/lib/audit'
import { rateLimit, getClientIp } from '@/lib/ratelimit'

export async function GET(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const db = getDb()
  const workouts = db.prepare(`
    SELECT w.id, w.name, w.date, w.notes, w.created_at,
           COUNT(e.id) as exercise_count
    FROM workouts w
    LEFT JOIN exercises e ON e.workout_id = w.id
    WHERE w.user_id = ?
    GROUP BY w.id
    ORDER BY w.date DESC, w.created_at DESC
    LIMIT 100
  `).all(user.sub)

  return NextResponse.json({ workouts })
}

export async function POST(req: NextRequest) {
  const ip = getClientIp(req)
  if (!rateLimit(`workout:${ip}`, 30, 60_000))
    return NextResponse.json({ error: 'Too many requests' }, { status: 429 })

  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const data = await req.json().catch(() => ({}))
  const name = (data.name || '').trim()
  const date = (data.date || new Date().toISOString().slice(0, 10)).trim()
  const notes = (data.notes || '').trim()

  if (!name) return NextResponse.json({ error: 'Workout name required' }, { status: 400 })

  const db = getDb()
  const result = db.prepare(
    'INSERT INTO workouts (user_id, name, date, notes) VALUES (?, ?, ?, ?)'
  ).run(user.sub, name, date, notes || null)

  auditLog({ userId: user.sub, username: user.username, action: 'workout.create', ip, detail: name })

  return NextResponse.json({ id: result.lastInsertRowid, name, date, notes }, { status: 201 })
}
