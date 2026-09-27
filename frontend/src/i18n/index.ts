import es from './es.json'
import pt from './pt.json'

export type Lang = 'es' | 'pt'
export type Strings = typeof es

export const strings: Record<Lang, Strings> = { es, pt }
