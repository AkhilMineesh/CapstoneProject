import type { ButtonHTMLAttributes } from 'react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string
}

export default function ShimmerButton({ label, className = '', ...rest }: Props) {
  return (
    <button className={`shimmerButton ${className}`.trim()} {...rest}>
      <span className="shimmerButtonInner">{label}</span>
    </button>
  )
}
