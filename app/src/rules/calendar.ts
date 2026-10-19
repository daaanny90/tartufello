import calendarData from './er-calendar-2026-2030.json'

export type ZoneId = 'collina' | 'pianura'

export interface Season {
  from: string // MM-DD
  to: string // MM-DD, può scavalcare il capodanno
  zones?: string[]
}

export interface SpeciesRule {
  id: string
  latin: string
  common: string
  target?: boolean
  seasons: Season[]
}

export interface Suspension {
  from: string
  to: string
  label: string
}

export interface Requirement {
  id: string
  title: string
  text: string
  ref: string
}

export interface Calendar {
  id: string
  title: string
  legalBasis: string
  source: string
  transcribedFrom: string
  verified: boolean
  verificationNote: string
  validYears: { from: number; to: number }
  zones: { id: string; label: string }[]
  zonesNote: string
  species: SpeciesRule[]
  suspensions: Suspension[]
  requirements: Requirement[]
}

export const calendar = calendarData as Calendar

export interface SpeciesStatus {
  species: SpeciesRule
  open: boolean
  /** Data dell'evento successivo: chiusura se aperto, apertura se chiuso. */
  nextChange: Date | null
  /** Giorni interi fino a nextChange. */
  daysToChange: number | null
}

export interface DayStatus {
  date: Date
  suspension: Suspension | null
  inValidity: boolean
  species: SpeciesStatus[]
}

const pad = (n: number) => String(n).padStart(2, '0')

export function mmdd(d: Date): string {
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Intervallo chiuso [from, to] su MM-DD; gestisce gli intervalli a cavallo di capodanno. */
export function inRange(day: string, from: string, to: string): boolean {
  return from <= to ? day >= from && day <= to : day >= from || day <= to
}

export function suspensionOn(d: Date, cal: Calendar = calendar): Suspension | null {
  const day = mmdd(d)
  return cal.suspensions.find((s) => inRange(day, s.from, s.to)) ?? null
}

export function isOpen(species: SpeciesRule, d: Date, zone: ZoneId, cal: Calendar = calendar): boolean {
  if (suspensionOn(d, cal)) return false
  const day = mmdd(d)
  return species.seasons.some((s) => (!s.zones || s.zones.includes(zone)) && inRange(day, s.from, s.to))
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
}

/** Primo giorno, dopo d, in cui lo stato di apertura cambia. Al massimo un anno avanti. */
export function nextChange(species: SpeciesRule, d: Date, zone: ZoneId, cal: Calendar = calendar): Date | null {
  const start = startOfDay(d)
  const now = isOpen(species, start, zone, cal)
  for (let i = 1; i <= 366; i++) {
    const day = addDays(start, i)
    if (isOpen(species, day, zone, cal) !== now) return day
  }
  return null
}

export function daysBetween(a: Date, b: Date): number {
  return Math.round((startOfDay(b).getTime() - startOfDay(a).getTime()) / 86_400_000)
}

export function dayStatus(d: Date, zone: ZoneId, cal: Calendar = calendar): DayStatus {
  const date = startOfDay(d)
  return {
    date,
    suspension: suspensionOn(date, cal),
    inValidity: date.getFullYear() >= cal.validYears.from && date.getFullYear() <= cal.validYears.to,
    species: cal.species.map((species) => {
      const change = nextChange(species, date, zone, cal)
      return {
        species,
        open: isOpen(species, date, zone, cal),
        nextChange: change,
        daysToChange: change ? daysBetween(date, change) : null,
      }
    }),
  }
}

/** Stato sintetico per il tartufo nero target (aestivum + uncinatum, stessa specie). */
export function targetStatus(d: Date, zone: ZoneId, cal: Calendar = calendar) {
  const status = dayStatus(d, zone, cal)
  const targets = status.species.filter((s) => s.species.target)
  const openNow = targets.filter((s) => s.open)
  if (openNow.length) {
    const closes = openNow
      .map((s) => s.nextChange)
      .filter((x): x is Date => !!x)
      .sort((a, b) => b.getTime() - a.getTime())[0] ?? null
    return { open: true, forms: openNow.map((s) => s.species), until: closes, from: null as Date | null }
  }
  const opens = targets
    .map((s) => ({ s, at: s.nextChange }))
    .filter((x): x is { s: SpeciesStatus; at: Date } => !!x.at)
    .sort((a, b) => a.at.getTime() - b.at.getTime())[0]
  return { open: false, forms: opens ? [opens.s.species] : [], until: null as Date | null, from: opens?.at ?? null }
}

const MONTHS = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic']

export function formatMmdd(s: string): string {
  const [m, d] = s.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]}`
}

export function formatDate(d: Date): string {
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

export function seasonLabel(species: SpeciesRule, zone?: ZoneId): string {
  return species.seasons
    .filter((s) => !zone || !s.zones || s.zones.includes(zone))
    .map((s) => `${formatMmdd(s.from)} - ${formatMmdd(s.to)}${s.zones && !zone ? ` (${s.zones.join(', ')})` : ''}`)
    .join('; ')
}
