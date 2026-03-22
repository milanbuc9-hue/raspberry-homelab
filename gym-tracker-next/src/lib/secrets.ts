/**
 * Secrets management layer.
 * Priority: Infisical (if token set) → environment variables → error
 *
 * To enable Infisical:
 *   1. Create a project + machine identity in Infisical UI (port 8096)
 *   2. Set INFISICAL_TOKEN in .env (machine identity client secret)
 *   3. Set secrets in Infisical under the same key names (JWT_SECRET, etc.)
 */

interface SecretCache {
  value: string
  fetchedAt: number
}

const cache = new Map<string, SecretCache>()
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 min

async function fetchFromInfisical(key: string): Promise<string | null> {
  const token = process.env.INFISICAL_TOKEN
  const siteUrl = process.env.INFISICAL_SITE_URL || 'http://infisical:8080'
  if (!token) return null

  const cached = cache.get(key)
  if (cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS) {
    return cached.value
  }

  try {
    const res = await fetch(
      `${siteUrl}/api/v3/secrets/raw/${key}?environment=production&workspaceSlug=gym-tracker`,
      {
        headers: { Authorization: `Bearer ${token}` },
        next: { revalidate: 0 },
      }
    )
    if (!res.ok) return null
    const data = await res.json()
    const value = data?.secret?.secretValue
    if (value) cache.set(key, { value, fetchedAt: Date.now() })
    return value ?? null
  } catch {
    return null
  }
}

export async function getSecret(key: string): Promise<string> {
  // Try Infisical first
  const infisicalValue = await fetchFromInfisical(key)
  if (infisicalValue) return infisicalValue

  // Fall back to environment variable
  const envValue = process.env[key]
  if (envValue) return envValue

  throw new Error(`Secret "${key}" not found in Infisical or environment variables`)
}

// Sync version for use in non-async contexts (reads env only)
export function getSecretSync(key: string): string {
  const value = process.env[key]
  if (!value) throw new Error(`Secret "${key}" not set in environment`)
  return value
}
