import jwt from 'jsonwebtoken'
import bcrypt from 'bcryptjs'
import crypto from 'crypto'
import { NextRequest } from 'next/server'

const JWT_SECRET = process.env.JWT_SECRET || 'change-me-in-production'
const ACCESS_TOKEN_EXP = 15 * 60        // 15 min
const REFRESH_TOKEN_EXP = 30 * 24 * 3600 // 30 days

export interface TokenPayload {
  sub: number
  username: string
  iat: number
  exp: number
}

export function hashPassword(password: string): string {
  return bcrypt.hashSync(password, 12)
}

export function checkPassword(password: string, hash: string): boolean {
  return bcrypt.compareSync(password, hash)
}

export function generateAccessToken(userId: number, username: string): string {
  return jwt.sign(
    { sub: userId, username },
    JWT_SECRET,
    { expiresIn: ACCESS_TOKEN_EXP }
  )
}

export function generateRefreshToken(): { raw: string; hash: string } {
  const raw = crypto.randomBytes(64).toString('base64url')
  const hash = crypto.createHash('sha256').update(raw).digest('hex')
  return { raw, hash }
}

export function hashRefreshToken(raw: string): string {
  return crypto.createHash('sha256').update(raw).digest('hex')
}

export function decodeAccessToken(token: string): TokenPayload | null {
  try {
    return jwt.verify(token, JWT_SECRET) as unknown as TokenPayload
  } catch {
    return null
  }
}

export function getRefreshTokenExpiry(): string {
  return new Date(Date.now() + REFRESH_TOKEN_EXP * 1000).toISOString()
}

export function getUserFromRequest(req: NextRequest): TokenPayload | null {
  const auth = req.headers.get('authorization') || ''
  if (!auth.startsWith('Bearer ')) return null
  return decodeAccessToken(auth.slice(7))
}
