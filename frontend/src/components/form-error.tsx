import { CircleAlertIcon } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { useTranslateMessage } from '@/i18n'

export function FormError({ message }: { message?: string }) {
  const translate = useTranslateMessage()
  if (!message) return null
  return (
    <Alert variant="destructive" role="alert">
      <CircleAlertIcon />
      <AlertDescription>{translate(message)}</AlertDescription>
    </Alert>
  )
}
