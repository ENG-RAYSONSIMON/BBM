/**
 * The emailed reset link is /reset-password#token=… (a fragment, so the
 * token never reaches server logs). See backend accounts/services.py.
 */
export function readTokenFromHash(hash: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, '')).get('token')
}
