// Logos fournis par l'équipe (public/logos/, fichiers NON modifiés) et leur zone visible, mesurée sur les images
// (les fichiers ont une marge transparente). Pour changer de logo : remplacer le fichier et ajuster box / size.
export type LogoSpec = {
  src: string
  alt: string
  // zone visible dans l'image d'origine (pixels) et taille totale de l'image
  box: { x: number; y: number; w: number; h: number }
  size: { w: number; h: number }
}

const base = import.meta.env.BASE_URL

export const LOGOS = {
  deutscheBoerse: {
    src: `${base}logos/boerse.png`,
    alt: 'Deutsche Börse',
    box: { x: 53, y: 73, w: 294, h: 54 },
    size: { w: 400, h: 200 },
  },
  pbb: {
    src: `${base}logos/Deutsche_Pfandbriefbank_logo.svg.webp`,
    alt: 'Deutsche Pfandbriefbank AG',
    box: { x: 35, y: 35, w: 1210, h: 1184 },
    size: { w: 1280, h: 1254 },
  },
} satisfies Record<string, LogoSpec>
