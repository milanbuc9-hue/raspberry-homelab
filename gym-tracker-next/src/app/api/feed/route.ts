import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'

export async function GET(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const db = getDb()
  const posts = db.prepare(`
    SELECT fp.id, fp.caption, fp.calories, fp.protein, fp.carbs, fp.fat, fp.created_at,
           COALESCE(fp.author, u.username) AS author
    FROM feed_posts fp
    LEFT JOIN users u ON fp.user_id = u.id
    ORDER BY fp.created_at DESC
    LIMIT 50
  `).all()

  return NextResponse.json({ posts })
}

export async function POST(req: NextRequest) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json().catch(() => ({}))
  const caption = (body.caption || '').trim()
  if (!caption) return NextResponse.json({ error: 'caption is required' }, { status: 400 })

  const db = getDb()
  const result = db.prepare(
    'INSERT INTO feed_posts (user_id, author, caption, calories, protein, carbs, fat) VALUES (?, ?, ?, ?, ?, ?, ?)'
  ).run(user.sub, user.username, caption, body.calories ?? 0, body.protein ?? 0, body.carbs ?? 0, body.fat ?? 0)

  const post = db.prepare('SELECT * FROM feed_posts WHERE id=?').get(result.lastInsertRowid)
  return NextResponse.json({ post }, { status: 201 })
}
