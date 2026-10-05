import { CircleAlertIcon } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'

export function FormError({ message }: { message?: string }) {
  if (!message) return null
  return (
    <Alert variant="destructive" role="alert">
      <CircleAlertIcon />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
