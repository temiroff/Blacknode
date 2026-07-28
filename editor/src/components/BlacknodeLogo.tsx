type BlacknodeLogoProps = {
  className?: string
  label?: string
}

export default function BlacknodeLogo({
  className = '',
  label,
}: BlacknodeLogoProps) {
  return (
    <span
      className={`bn-logo ${className}`.trim()}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <img
        className="bn-logo-image bn-logo-image-dark"
        src="/blacknode-logo-dark.png"
        alt=""
      />
      <img
        className="bn-logo-image bn-logo-image-light"
        src="/blacknode-logo-light.png"
        alt=""
      />
    </span>
  )
}
