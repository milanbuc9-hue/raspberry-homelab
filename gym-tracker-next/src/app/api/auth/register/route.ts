import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { hashPassword, generateAccessToken, generateRefreshToken, getRefreshTokenExpiry } from '@/lib/auth'

export async function POST(req: NextRequest) {
  const data = await req.json().catch(() => ({}))
  const username = (data.username || '').trim()
  const password = data.password || ''
  const email = (data.email || '').trim()

  if (!username || username.length < 3)
    return NextResponse.json({ error: 'Username must be at least 3 characters' }, { status: 400 })
  if (!password || password.length < 6)
    return NextResponse.json({ error: 'Password must be at least 6 characters' }, { status: 400 })
  if (email && !email.includes('@'))
    return NextResponse.json({ error: 'Valid email address required' }, { status: 400 })

  const db = getDb()

  if (db.prepare('SELECT id FROM users WHERE username=? COLLATE NOCASE').get(username))
    return NextResponse.json({ error: 'Username already taken' }, { status: 409 })

  if (email && db.prepare('SELECT id FROM users WHERE email=? COLLATE NOCASE').get(email))
    return NextResponse.json({ error: 'Email already registered' }, { status: 409 })

  const pwHash = hashPassword(password)
  const result = db.prepare(
    'INSERT INTO users (username, email, password_hash, is_active, email_verified) VALUES (?, ?, ?, 1, 1)'
  ).run(username, email || null, pwHash)

  const userId = result.lastInsertRowid as number
  const accessToken = generateAccessToken(userId, username)
  const { raw, hash } = generateRefreshToken()

  db.prepare(
    'INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)'
  ).run(userId, hash, getRefreshTokenExpiry())

  return NextResponse.json({
    access_token: accessToken,
    refresh_token: raw,
    user: { id: userId, username },
  }, { status: 201 })
}
