import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

/** One button vocabulary for the whole app.
 *  `default` is the current section's colour (data-mode on the page), so a
 *  primary action is blue in the library, amber in flashcards, violet in
 *  quizzes, emerald in analytics without any per-page classes. */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-[background-color,border-color,color,box-shadow,transform] duration-150 active:translate-y-px disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:ring-[3px] focus-visible:ring-mode/30",
  {
    variants: {
      variant: {
        default: 'bg-mode text-white hover:bg-mode-hover',
        ink: 'bg-slate-900 text-white hover:bg-slate-800',
        destructive: 'bg-mode-danger text-white hover:bg-red-700 focus-visible:ring-red-500/40',
        outline: 'border border-slate-300 bg-white text-slate-900 hover:bg-slate-50',
        // Outline in the mode colour: a secondary action that still belongs to the section.
        tinted: 'border border-mode/40 bg-white text-mode hover:bg-mode/10',
        secondary: 'bg-slate-100 text-slate-900 hover:bg-slate-200',
        ghost: 'text-slate-700 hover:bg-slate-100 hover:text-slate-900',
        link: 'text-mode underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 has-[>svg]:px-3',
        sm: 'h-8 gap-1.5 px-3 text-sm has-[>svg]:px-2.5',
        lg: 'h-11 px-5 text-base has-[>svg]:px-4',
        icon: 'size-10',
        'icon-sm': 'size-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot : 'button'

  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
