import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { checkPassword, generateAccessToken, generateRefreshToken, getRefreshTokenExpiry } from '@/lib/auth'
import { auditLog } from '@/lib/audit'
import { rateLimit, recordFailedLogin, clearFailedLogins, isBanned, getClientIp } from '@/lib/ratelimit'

export async function POST(req: NextRequest) {
  const ip = getClientIp(req)

  // Rate limit: 10 attempts per minute per IP
  if (!rateLimit(`login:${ip}`, 10, 60_000))
    return NextResponse.json({ error: 'Too many requests' }, { status: 429 })

  // Fail2Ban: check if IP is banned
  const banCheck = isBanned(ip)
  if (banCheck.banned)
    return NextResponse.json({ error: 'Too many failed attempts. Try again later.' }, { status: 429 })

  const data = await req.json().catch(() => ({}))
  const username = (data.username || '').trim()
  const password = data.password || ''

  if (!username || !password)
    return NextResponse.json({ error: 'Username and password required' }, { status: 400 })

  // Check username-level ban too
  const userBan = isBanned(`user:${username.toLowerCase()}`)
  if (userBan.banned)
    return NextResponse.json({ error: 'Too many failed attempts. Try again later.' }, { status: 429 })

  const db = getDb()
  const user = db.prepare(
    'SELECT * FROM users WHERE username=? COLLATE NOCASE'
  ).get(username) as any

  if (!user || !checkPassword(password, user.password_hash)) {
    const banned = recordFailedLogin(ip)
    recordFailedLogin(`user:${username.toLowerCase()}`)
    auditLog({ userId: null, username, action: 'auth.login.failed', ip, detail: `attempt from ${ip}` })
    if (banned)
      return NextResponse.json({ error: 'Too many failed attempts. Temporarily banned.' }, { status: 429 })
    return NextResponse.json({ error: 'Invalid username or password' }, { status: 401 })
  }

  if (!user.is_active)
    return NextResponse.json({ error: 'Account inactive' }, { status: 403 })

  clearFailedLogins(ip)
  clearFailedLogins(`user:${username.toLowerCase()}`)

  const accessToken = generateAccessToken(user.id, user.username)
  const { raw, hash } = generateRefreshToken()

  db.prepare(
    'INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)'
  ).run(user.id, hash, getRefreshTokenExpiry())

  auditLog({ userId: user.id, username: user.username, action: 'auth.login', ip })

  return NextResponse.json({
    access_token: accessToken,
    refresh_token: raw,
    user: { id: user.id, username: user.username, email: user.email },
  })
}
