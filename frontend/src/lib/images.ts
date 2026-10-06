export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const IMAGE_MAX_BYTES = 2 * 1024 * 1024

/** Quick client-side check for feedback; the server validates the real file. */
export function checkImageFile(file: File): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return 'Use a JPEG, PNG or WebP image.'
  if (file.size > IMAGE_MAX_BYTES) return 'Image is too large. The limit is 2 MB.'
  return null
}
