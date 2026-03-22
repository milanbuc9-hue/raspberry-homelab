/**
 * In-memory rate limiter + brute-force protection.
 * Acts as application-level Fail2Ban.
 * Resets on process restart – sufficient for homelab use.
 */

interface RateBucket {
  count: number
  resetAt: number
}

interface BanEntry {
  bannedUntil: number
  reason: string
}

const buckets = new Map<string, RateBucket>()
const bans = new Map<string, BanEntry>()
const failedLogins = new Map<string, number[]>()

const FAILED_LOGIN_WINDOW = 60 * 60 * 1000  // 1h
const FAILED_LOGIN_LIMIT = 10               // 10 failures → ban
const BAN_DURATION = 60 * 60 * 1000         // 1h ban

/** General rate limiter: max `limit` requests per `windowMs` */
export function rateLimit(key: string, limit: number, windowMs: number): boolean {
  const now = Date.now()
  const bucket = buckets.get(key)

  if (!bucket || now > bucket.resetAt) {
    buckets.set(key, { count: 1, resetAt: now + windowMs })
    return true
  }

  if (bucket.count >= limit) return false
  bucket.count++
  return true
}

/** Track a failed login attempt. Returns true if IP/user should be banned. */
export function recordFailedLogin(identifier: string): boolean {
  const now = Date.now()
  const cutoff = now - FAILED_LOGIN_WINDOW
  const attempts = (failedLogins.get(identifier) || []).filter(t => t > cutoff)
  attempts.push(now)
  failedLogins.set(identifier, attempts)

  if (attempts.length >= FAILED_LOGIN_LIMIT) {
    bans.set(identifier, {
      bannedUntil: now + BAN_DURATION,
      reason: `Too many failed login attempts (${attempts.length})`,
    })
    return true
  }
  return false
}

export function clearFailedLogins(identifier: string) {
  failedLogins.delete(identifier)
  bans.delete(identifier)
}

export function isBanned(identifier: string): { banned: boolean; reason?: string } {
  const ban = bans.get(identifier)
  if (!ban) return { banned: false }
  if (Date.now() > ban.bannedUntil) {
    bans.delete(identifier)
    return { banned: false }
  }
  return { banned: true, reason: ban.reason }
}

export function getClientIp(req: Request): string {
  const headers = new Headers(req.headers)
  return (
    headers.get('cf-connecting-ip') ||
    headers.get('x-real-ip') ||
    headers.get('x-forwarded-for')?.split(',')[0].trim() ||
    'unknown'
  )
}
