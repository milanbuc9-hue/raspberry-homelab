import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'
import { auditLog } from '@/lib/audit'
import { getClientIp } from '@/lib/ratelimit'

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id } = await params
  const db = getDb()
  const workout = db.prepare(
    'SELECT * FROM workouts WHERE id=? AND user_id=?'
  ).get(Number(id), user.sub) as any

  if (!workout) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  const exercises = db.prepare(
    'SELECT * FROM exercises WHERE workout_id=? ORDER BY order_index, id'
  ).all(workout.id)

  return NextResponse.json({ ...workout, exercises })
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id } = await params
  const db = getDb()
  const workout = db.prepare(
    'SELECT id, name FROM workouts WHERE id=? AND user_id=?'
  ).get(Number(id), user.sub) as any

  if (!workout) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  db.prepare('DELETE FROM workouts WHERE id=?').run(workout.id)
  auditLog({ userId: user.sub, username: user.username, action: 'workout.delete', ip: getClientIp(req), detail: workout.name })

  return NextResponse.json({ status: 'deleted' })
}
