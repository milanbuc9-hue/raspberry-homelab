import { getDb } from './db'

export type AuditAction =
  | 'auth.register'
  | 'auth.login'
  | 'auth.login.failed'
  | 'auth.logout'
  | 'auth.refresh'
  | 'workout.create'
  | 'workout.delete'
  | 'exercise.create'
  | 'exercise.update'
  | 'exercise.delete'
  | 'calories.log'
  | 'calories.delete'
  | 'admin.view_logs'
  | 'admin.clear_logs'

export interface AuditEntry {
  userId: number | null
  username: string | null
  action: AuditAction
  ip: string | null
  detail?: string
}

export function auditLog(entry: AuditEntry) {
  try {
    const db = getDb()
    db.prepare(`
      INSERT INTO audit_logs (user_id, username, action, ip, detail)
      VALUES (?, ?, ?, ?, ?)
    `).run(
      entry.userId ?? null,
      entry.username ?? null,
      entry.action,
      entry.ip ?? null,
      entry.detail ? entry.detail.slice(0, 500) : null
    )
  } catch {
    // Never crash the app due to logging failure
  }
}

export function initAuditTable() {
  const db = getDb()
  db.exec(`
    CREATE TABLE IF NOT EXISTS audit_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      username TEXT,
      action TEXT NOT NULL,
      ip TEXT,
      detail TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
    CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
  `)
}
