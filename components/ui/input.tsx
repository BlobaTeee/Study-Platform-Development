import * as React from 'react'

import { cn } from '@/lib/utils'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'h-10 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 transition-[border-color,box-shadow] duration-150 outline-none',
        'placeholder:text-slate-500',
        'selection:bg-mode selection:text-white',
        'file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-slate-900',
        'focus-visible:border-mode focus-visible:ring-[3px] focus-visible:ring-mode/25',
        'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
        'aria-invalid:border-red-500 aria-invalid:ring-red-500/30',
        className,
      )}
      {...props}
    />
  )
}

export { Input }
