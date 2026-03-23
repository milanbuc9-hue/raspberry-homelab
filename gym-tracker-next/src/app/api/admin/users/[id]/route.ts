import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'

function isAdmin(userId: number): boolean {
  const db = getDb()
  if (userId === 1) return true
  const u = db.prepare('SELECT is_admin FROM users WHERE id=?').get(userId) as any
  return u?.is_admin === 1
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  if (!isAdmin(user.sub)) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  const { id } = await params
  const body = await req.json().catch(() => ({}))
  const db = getDb()

  const target = db.prepare('SELECT id FROM users WHERE id=?').get(Number(id))
  if (!target) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  db.prepare('UPDATE users SET is_active=? WHERE id=?').run(body.is_active === 1 ? 1 : 0, Number(id))
  const updated = db.prepare('SELECT id, username, email, created_at, is_active, is_admin FROM users WHERE id=?').get(Number(id))
  return NextResponse.json({ user: updated })
}
