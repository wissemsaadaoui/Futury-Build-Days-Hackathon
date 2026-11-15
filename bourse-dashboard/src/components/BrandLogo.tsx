// Marque texte de l'application (aucun logo tiers) : monogramme « IIH », hauteur via la variable CSS --logo-h.
export function BrandLogo({ text = 'IIH', className = '' }: { text?: string; className?: string }) {
  return (
    <span className={`brand-wordmark ${className}`} aria-hidden="true">
      {text}
    </span>
  )
}
