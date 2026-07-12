import * as React from 'react'

import { cn } from '@/lib/utils'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-base text-slate-900 shadow-sm transition-[color,box-shadow] outline-none',
        'placeholder:text-slate-500',
        'selection:bg-blue-600 selection:text-white',
        'file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-slate-900',
        'focus-visible:border-blue-500 focus-visible:ring-blue-500/25 focus-visible:ring-[4px]',
        'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
        'aria-invalid:border-red-500 aria-invalid:ring-red-500/30',
        className,
      )}
      {...props}
    />
  )
}

export { Input }
