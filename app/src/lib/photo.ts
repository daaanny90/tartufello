/**
 * Riduce la foto a max 1600 px e la ricodifica in JPEG.
 * La ricodifica toglie anche i metadati EXIF, GPS compreso.
 */
export async function shrinkPhoto(file: Blob, maxSide = 1600, quality = 0.82): Promise<Blob> {
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
  const w = Math.round(bitmap.width * scale)
  const h = Math.round(bitmap.height * scale)
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, w, h)
  bitmap.close()
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Conversione foto fallita'))), 'image/jpeg', quality),
  )
}
