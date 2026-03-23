import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id } = await params
  const db = getDb()
  const entry = db.prepare('SELECT id FROM food_log WHERE id=? AND user_id=?').get(Number(id), user.sub)
  if (!entry) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  db.prepare('DELETE FROM food_log WHERE id=?').run(Number(id))
  return NextResponse.json({ status: 'deleted' })
}
