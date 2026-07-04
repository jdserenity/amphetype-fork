import { validateLicense } from '../_license.js';
import {
  makeDownloadPayload,
  pickUpdate,
  readManifest,
  signDownloadToken,
} from '../_update.js';

const ALLOWED_PLATFORMS = new Set(['darwin', 'win32', 'linux']);

export async function onRequestPost(context) {
  let body;
  try {
    body = await context.request.json();
  } catch {
    return Response.json({ error: 'invalid json' }, { status: 400 });
  }

  const licenseKey = String(body.license_key || '').trim();
  const instanceId = String(body.instance_id || '').trim();
  const platform = String(body.platform || '').trim();
  const currentVersion = String(body.current_version || '').trim();

  if (!licenseKey || !instanceId) {
    return Response.json({ error: 'missing license' }, { status: 400 });
  }
  if (!ALLOWED_PLATFORMS.has(platform)) {
    return Response.json({ error: 'unsupported platform' }, { status: 400 });
  }
  if (!currentVersion) {
    return Response.json({ error: 'missing current_version' }, { status: 400 });
  }

  const lic = await validateLicense(licenseKey, instanceId);
  if (!lic.ok) {
    return Response.json({ error: lic.error || 'invalid license' }, { status: 403 });
  }

  const bucket = context.env.UPDATES;
  if (!bucket) {
    return Response.json({ error: 'updates not configured' }, { status: 503 });
  }

  let manifest;
  try {
    manifest = await readManifest(bucket);
  } catch {
    return Response.json({ error: 'manifest unreadable' }, { status: 503 });
  }
  if (!manifest) {
    return Response.json({ update_available: false });
  }

  const hit = pickUpdate(manifest, platform, currentVersion);
  if (!hit) {
    return Response.json({ update_available: false });
  }

  const secret = context.env.UPDATE_SIGNING_SECRET;
  if (!secret) {
    return Response.json({ error: 'signing not configured' }, { status: 503 });
  }

  const token = await signDownloadToken(secret, makeDownloadPayload(hit.object_key, hit.sha256));
  const origin = new URL(context.request.url).origin;
  return Response.json({
    update_available: true,
    version: hit.version,
    sha256: hit.sha256,
    release_notes: hit.release_notes,
    download_url: `${origin}/api/download-update?token=${encodeURIComponent(token)}`,
  });
}
