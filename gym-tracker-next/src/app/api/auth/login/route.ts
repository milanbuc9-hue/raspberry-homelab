import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { checkPassword, generateAccessToken, generateRefreshToken, getRefreshTokenExpiry } from '@/lib/auth'

export async function POST(req: NextRequest) {
  const data = await req.json().catch(() => ({}))
  const username = (data.username || '').trim()
  const password = data.password || ''

  if (!username || !password)
    return NextResponse.json({ error: 'Username and password required' }, { status: 400 })

  const db = getDb()
  const user = db.prepare(
    'SELECT * FROM users WHERE username=? COLLATE NOCASE'
  ).get(username) as any

  if (!user || !checkPassword(password, user.password_hash))
    return NextResponse.json({ error: 'Invalid username or password' }, { status: 401 })

  if (!user.is_active)
    return NextResponse.json({ error: 'Account inactive' }, { status: 403 })

  const accessToken = generateAccessToken(user.id, user.username)
  const { raw, hash } = generateRefreshToken()

  db.prepare(
    'INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)'
  ).run(user.id, hash, getRefreshTokenExpiry())

  return NextResponse.json({
    access_token: accessToken,
    refresh_token: raw,
    user: { id: user.id, username: user.username, email: user.email },
  })
}
