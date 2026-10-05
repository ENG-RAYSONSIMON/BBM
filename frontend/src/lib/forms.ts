import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'

import { ApiError } from './api'

/**
 * Put DRF field errors on the matching form fields; anything else (detail,
 * non-field, network) goes on `root.server`.
 */
export function applyServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly Path<T>[],
) {
  if (!(error instanceof ApiError)) {
    setError('root.server', { message: 'Something went wrong. Please try again.' })
    return
  }
  const fieldErrors = error.fieldErrors()
  let matched = false
  for (const field of fields) {
    const message = fieldErrors[field]
    if (message) {
      setError(field, { message })
      matched = true
    }
  }
  if (!matched) setError('root.server', { message: error.message })
}
