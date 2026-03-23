import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'

function isAdmin(userId: number): boolean {
  const db = getDb()
  if (userId === 1) return true
  const u = db.prepare('SELECT is_admin FROM users WHERE id=?').get(userId) as any
  return u?.is_admin === 1
}

export async function GET(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  if (!isAdmin(user.sub)) return NextResponse.json({ error: 'Forbidden' }, { status: 403 })

  const db = getDb()
  const users = db.prepare(
    'SELECT id, username, email, created_at, is_active, is_admin FROM users ORDER BY id ASC'
  ).all()
  return NextResponse.json({ users })
}
