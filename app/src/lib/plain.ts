/**
 * Copia profonda senza Proxy di Vue: IndexedDB non sa clonare gli oggetti reattivi.
 * Solo per dati JSON (niente Blob).
 */
export function plain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
