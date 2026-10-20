/** Ogni quanti giorni ricordare il backup, se ci sono dati. */
export const BACKUP_REMINDER_DAYS = 14

export function backupOverdue(lastBackupAt: string, hasData: boolean, now = new Date()): boolean {
  if (!hasData) return false
  if (!lastBackupAt) return true
  return now.getTime() - new Date(lastBackupAt).getTime() > BACKUP_REMINDER_DAYS * 86_400_000
}
