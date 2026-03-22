import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest, hashRefreshToken } from '@/lib/auth'

export async function POST(req: NextRequest) {
  const payload = getUserFromRequest(req)
  const data = await req.json().catch(() => ({}))
  const rawToken = data.refresh_token || ''

  const db = getDb()

  if (rawToken) {
    db.prepare('DELETE FROM refresh_tokens WHERE token_hash=?').run(hashRefreshToken(rawToken))
  } else if (payload) {
    db.prepare('DELETE FROM refresh_tokens WHERE user_id=?').run(payload.sub)
  }

  return NextResponse.json({ status: 'logged_out' })
}
