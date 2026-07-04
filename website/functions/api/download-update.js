import { verifyDownloadToken } from '../_update.js';

export async function onRequestGet(context) {
  const token = new URL(context.request.url).searchParams.get('token');
  const secret = context.env.UPDATE_SIGNING_SECRET;
  const bucket = context.env.UPDATES;
  if (!secret || !bucket) {
    return new Response('not configured', { status: 503 });
  }

  const payload = await verifyDownloadToken(secret, token);
  if (!payload) {
    return new Response('invalid or expired token', { status: 403 });
  }

  const obj = await bucket.get(payload.object_key);
  if (!obj) {
    return new Response('not found', { status: 404 });
  }

  const headers = new Headers();
  headers.set('Content-Type', obj.httpMetadata?.contentType || 'application/octet-stream');
  headers.set('Cache-Control', 'private, no-store');
  if (obj.size) headers.set('Content-Length', String(obj.size));
  return new Response(obj.body, { status: 200, headers });
}
