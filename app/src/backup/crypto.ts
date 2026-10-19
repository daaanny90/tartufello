/**
 * Cifratura del backup con passphrase: PBKDF2-SHA256 -> AES-GCM 256.
 * Solo WebCrypto, niente librerie.
 */

export const PBKDF2_ITERATIONS = 600_000

export interface Envelope {
  format: 'fiuto-backup'
  version: 1
  createdAt: string
  kdf: { name: 'PBKDF2'; hash: 'SHA-256'; iterations: number; salt: string }
  cipher: { name: 'AES-GCM'; iv: string }
  compression: 'gzip'
  payload: string
}

export function toBase64(bytes: Uint8Array): string {
  let s = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    s += String.fromCharCode(...bytes.subarray(i, i + chunk))
  }
  return btoa(s)
}

export function fromBase64(b64: string): Uint8Array<ArrayBuffer> {
  const s = atob(b64)
  const out = new Uint8Array(s.length)
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i)
  return out
}

async function pipeThrough(data: Uint8Array<ArrayBuffer>, stream: CompressionStream | DecompressionStream) {
  const out = new Blob([data]).stream().pipeThrough(stream)
  return new Uint8Array(await new Response(out).arrayBuffer())
}

async function deriveKey(passphrase: string, salt: Uint8Array<ArrayBuffer>, iterations: number) {
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(passphrase), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', hash: 'SHA-256', salt, iterations },
    base,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export async function encrypt(plain: string, passphrase: string, iterations = PBKDF2_ITERATIONS): Promise<Envelope> {
  if (passphrase.length < 8) throw new Error('La passphrase deve avere almeno 8 caratteri.')
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(passphrase, salt, iterations)
  const zipped = await pipeThrough(new TextEncoder().encode(plain), new CompressionStream('gzip'))
  const cipher = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, zipped))
  return {
    format: 'fiuto-backup',
    version: 1,
    createdAt: new Date().toISOString(),
    kdf: { name: 'PBKDF2', hash: 'SHA-256', iterations, salt: toBase64(salt) },
    cipher: { name: 'AES-GCM', iv: toBase64(iv) },
    compression: 'gzip',
    payload: toBase64(cipher),
  }
}

export class WrongPassphraseError extends Error {
  constructor() {
    super('Passphrase sbagliata o file danneggiato.')
  }
}

export async function decrypt(env: Envelope, passphrase: string): Promise<string> {
  if (env.format !== 'fiuto-backup' || env.version !== 1) throw new Error('Non è un backup di fiuto riconosciuto.')
  const key = await deriveKey(passphrase, fromBase64(env.kdf.salt), env.kdf.iterations)
  let zipped: Uint8Array<ArrayBuffer>
  try {
    zipped = new Uint8Array(
      await crypto.subtle.decrypt({ name: 'AES-GCM', iv: fromBase64(env.cipher.iv) }, key, fromBase64(env.payload)),
    )
  } catch {
    throw new WrongPassphraseError()
  }
  return new TextDecoder().decode(await pipeThrough(zipped, new DecompressionStream('gzip')))
}
