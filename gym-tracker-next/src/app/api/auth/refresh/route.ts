import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { hashRefreshToken, generateAccessToken, generateRefreshToken, getRefreshTokenExpiry } from '@/lib/auth'

export async function POST(req: NextRequest) {
  const data = await req.json().catch(() => ({}))
  const rawToken = data.refresh_token || ''
  if (!rawToken) return NextResponse.json({ error: 'refresh_token required' }, { status: 400 })

  const db = getDb()
  const tokenHash = hashRefreshToken(rawToken)
  const stored = db.prepare(
    'SELECT * FROM refresh_tokens WHERE token_hash=?'
  ).get(tokenHash) as any

  if (!stored) return NextResponse.json({ error: 'Invalid refresh token' }, { status: 401 })
  if (new Date(stored.expires_at) < new Date())
    return NextResponse.json({ error: 'Refresh token expired' }, { status: 401 })

  const user = db.prepare('SELECT id, username FROM users WHERE id=?').get(stored.user_id) as any
  if (!user) return NextResponse.json({ error: 'User not found' }, { status: 404 })

  // Rotate refresh token
  db.prepare('DELETE FROM refresh_tokens WHERE token_hash=?').run(tokenHash)
  const { raw, hash } = generateRefreshToken()
  db.prepare(
    'INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)'
  ).run(user.id, hash, getRefreshTokenExpiry())

  return NextResponse.json({
    access_token: generateAccessToken(user.id, user.username),
    refresh_token: raw,
  })
}
