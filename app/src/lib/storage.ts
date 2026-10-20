/**
 * Chiede al browser di non cancellare IndexedDB quando manca spazio.
 * Chrome lo concede in silenzio alle PWA installate; altrove può chiedere conferma.
 */
export async function ensurePersisted(): Promise<boolean> {
  try {
    if (!navigator.storage?.persist) return false
    if (await navigator.storage.persisted()) return true
    return await navigator.storage.persist()
  } catch {
    return false
  }
}

export const outingLabel = (kind?: string) => (kind === 'sopralluogo' ? 'Sopralluogo' : 'Uscita')
