import { EyeIcon, EyeOffIcon } from 'lucide-react'
import { useState } from 'react'
import type { ComponentProps } from 'react'
import { useTranslation } from 'react-i18next'

import { FormField } from '@/components/form-field'
import { Button } from '@/components/ui/button'

type PasswordFieldProps = Omit<ComponentProps<typeof FormField>, 'type' | 'trailing'>

/** Password input with an eye button to show what was typed. Each field has its own. */
export function PasswordField(props: PasswordFieldProps) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(false)
  const label = visible ? t('common.hidePassword') : t('common.showPassword')

  return (
    <FormField
      {...props}
      type={visible ? 'text' : 'password'}
      // No autocorrect or capitals while the text is visible.
      autoCapitalize="none"
      autoCorrect="off"
      spellCheck={false}
      trailing={
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-foreground size-9 md:size-8"
          aria-label={label}
          aria-pressed={visible}
          title={label}
          // Keep the cursor in the field.
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </Button>
      }
    />
  )
}
