import { NextRequest, NextResponse } from 'next/server'
import { getDb } from '@/lib/db'
import { getUserFromRequest } from '@/lib/auth'

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id } = await params
  const db = getDb()
  const body = await req.json().catch(() => ({}))
  const is_done = body.is_done ? 1 : 0

  // Try personal todo first, then shared
  const personal = db.prepare('SELECT id FROM personal_todos WHERE id=? AND user_id=?').get(Number(id), user.sub)
  if (personal) {
    db.prepare('UPDATE personal_todos SET is_done=? WHERE id=?').run(is_done, Number(id))
    return NextResponse.json({ status: 'updated' })
  }
  const shared = db.prepare('SELECT id FROM todos WHERE id=?').get(Number(id))
  if (shared) {
    db.prepare('UPDATE todos SET is_done=? WHERE id=?').run(is_done, Number(id))
    return NextResponse.json({ status: 'updated' })
  }
  return NextResponse.json({ error: 'Not found' }, { status: 404 })
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const user = getUserFromRequest(req)
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { id } = await params
  const db = getDb()

  const personal = db.prepare('SELECT id FROM personal_todos WHERE id=? AND user_id=?').get(Number(id), user.sub)
  if (personal) {
    db.prepare('DELETE FROM personal_todos WHERE id=?').run(Number(id))
    return NextResponse.json({ status: 'deleted' })
  }
  const shared = db.prepare('SELECT id FROM todos WHERE id=?').get(Number(id))
  if (shared) {
    db.prepare('DELETE FROM todos WHERE id=?').run(Number(id))
    return NextResponse.json({ status: 'deleted' })
  }
  return NextResponse.json({ error: 'Not found' }, { status: 404 })
}
