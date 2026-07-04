const MANIFEST_KEY = 'manifest.json';
const TOKEN_TTL_SEC = 3600;

export function parseVersion(s) {
  const parts = String(s || '').trim().split('.');
  if (!parts.length || !parts.every((p) => /^\d+$/.test(p))) return null;
  return parts.map((p) => Number(p));
}

export function isNewer(available, current) {
  const a = parseVersion(available);
  const b = parseVersion(current);
  if (!a || !b) return false;
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    const av = a[i] || 0;
    const bv = b[i] || 0;
    if (av > bv) return true;
    if (av < bv) return false;
  }
  return false;
}

export function platformEntry(manifest, platform) {
  if (!manifest) return null;
  const platforms = manifest.platforms || {};
  return platforms[platform] || null;
}

export function pickUpdate(manifest, platform, currentVersion) {
  if (!manifest) return null;
  const latest = String(manifest.version || '').trim();
  if (!latest || !isNewer(latest, currentVersion)) return null;
  const entry = platformEntry(manifest, platform);
  if (!entry || !entry.object_key || !entry.sha256) return null;
  return {
    version: latest,
    sha256: entry.sha256,
    object_key: entry.object_key,
    release_notes: manifest.release_notes || '',
  };
}

export async function readManifest(bucket) {
  const obj = await bucket.get(MANIFEST_KEY);
  if (!obj) return null;
  const text = await obj.text();
  return JSON.parse(text);
}

function b64url(bytes) {
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function fromB64url(s) {
  const pad = '='.repeat((4 - (s.length % 4)) % 4);
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/') + pad;
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

async function hmacKey(secret) {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify'],
  );
}

export async function signDownloadToken(secret, payload) {
  const enc = new TextEncoder();
  const body = b64url(enc.encode(JSON.stringify(payload)));
  const key = await hmacKey(secret);
  const sig = new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(body)));
  return `${body}.${b64url(sig)}`;
}

export async function verifyDownloadToken(secret, token) {
  const parts = String(token || '').split('.');
  if (parts.length !== 2) return null;
  const enc = new TextEncoder();
  const key = await hmacKey(secret);
  const ok = await crypto.subtle.verify('HMAC', key, fromB64url(parts[1]), enc.encode(parts[0]));
  if (!ok) return null;
  try {
    const json = new TextDecoder().decode(fromB64url(parts[0]));
    const payload = JSON.parse(json);
    if (!payload.exp || payload.exp < Math.floor(Date.now() / 1000)) return null;
    if (!payload.object_key || !payload.sha256) return null;
    return payload;
  } catch {
    return null;
  }
}

export function makeDownloadPayload(objectKey, sha256) {
  return {
    object_key: objectKey,
    sha256,
    exp: Math.floor(Date.now() / 1000) + TOKEN_TTL_SEC,
  };
}

export { MANIFEST_KEY, TOKEN_TTL_SEC };
