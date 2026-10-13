export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const IMAGE_MAX_BYTES = 2 * 1024 * 1024

/** Quick client-side check for feedback (an i18n key); the server validates the real file. */
export function checkImageFile(file: File): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return 'errors.imageType'
  if (file.size > IMAGE_MAX_BYTES) return 'errors.imageTooLarge'
  return null
}
