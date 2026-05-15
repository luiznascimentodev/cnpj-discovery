import * as Slider from '@radix-ui/react-slider'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

const SliderImpl = forwardRef<
  React.ElementRef<typeof Slider.Root>,
  React.ComponentPropsWithoutRef<typeof Slider.Root>
>(({ className, ...props }, ref) => (
  <Slider.Root
    ref={ref}
    className={cn('relative flex items-center select-none touch-none w-full h-5', className)}
    {...props}
  >
    <Slider.Track className="bg-[var(--color-gray-200)] relative grow rounded-full h-1">
      <Slider.Range className="absolute bg-[var(--color-action)] rounded-full h-full" />
    </Slider.Track>
    <Slider.Thumb
      className="block h-4 w-4 bg-white border-2 border-[var(--color-action)] rounded-full focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
      aria-label="valor"
    />
  </Slider.Root>
))
SliderImpl.displayName = 'Slider'

export { SliderImpl as Slider }
