import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'
import { auditLog } from '@/lib/audit'
import { getClientIp } from '@/lib/ratelimit'

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id } = await params
  const db = getDb()
  const workout = db.prepare(
    'SELECT id FROM workouts WHERE id=? AND user_id=?'
  ).get(Number(id), user.sub)

  if (!workout) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  const data = await req.json().catch(() => ({}))
  const name = (data.name || '').trim()
  if (!name) return NextResponse.json({ error: 'Exercise name required' }, { status: 400 })

  const result = db.prepare(
    'INSERT INTO exercises (workout_id, name, sets, reps, weight, notes, order_index) VALUES (?, ?, ?, ?, ?, ?, ?)'
  ).run(
    Number(id),
    name,
    data.sets ?? 0,
    data.reps ?? 0,
    data.weight ?? 0,
    data.notes || null,
    data.order_index ?? 0
  )

  auditLog({ userId: user.sub, username: user.username, action: 'exercise.create', ip: getClientIp(req), detail: name })

  return NextResponse.json({ id: result.lastInsertRowid, name }, { status: 201 })
}
