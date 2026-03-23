import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'

export async function GET(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const db = getDb()
  const dbUser = db.prepare('SELECT id, username, email, created_at FROM users WHERE id=?').get(user.sub)
  if (!dbUser) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  return NextResponse.json({ user: dbUser })
}

export async function PATCH(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({}))
  const email = (body.email || '').trim()
  if (!email || !email.includes('@'))
    return NextResponse.json({ error: 'Ungültige E-Mail-Adresse.' }, { status: 400 })

  const db = getDb()
  const existing = db.prepare('SELECT id FROM users WHERE email=? AND id!=?').get(email, user.sub)
  if (existing) return NextResponse.json({ error: 'E-Mail bereits vergeben.' }, { status: 409 })

  db.prepare('UPDATE users SET email=? WHERE id=?').run(email, user.sub)
  const updated = db.prepare('SELECT id, username, email, created_at FROM users WHERE id=?').get(user.sub)
  return NextResponse.json({ user: updated })
}
