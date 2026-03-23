import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest, hashPassword, checkPassword } from '@/lib/auth'

export async function POST(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({}))
  const { current_password, new_password } = body
  if (!current_password || !new_password)
    return NextResponse.json({ error: 'Alle Felder sind Pflicht.' }, { status: 400 })
  if (new_password.length < 6)
    return NextResponse.json({ error: 'Neues Passwort muss mind. 6 Zeichen haben.' }, { status: 400 })

  const db = getDb()
  const dbUser = db.prepare('SELECT password_hash FROM users WHERE id=?').get(user.sub) as any
  if (!dbUser) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  if (!checkPassword(current_password, dbUser.password_hash))
    return NextResponse.json({ error: 'Aktuelles Passwort ist falsch.' }, { status: 400 })

  db.prepare('UPDATE users SET password_hash=? WHERE id=?').run(hashPassword(new_password), user.sub)
  return NextResponse.json({ status: 'password_changed' })
}
