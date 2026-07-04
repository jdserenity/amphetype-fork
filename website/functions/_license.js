const LICENSE_API = 'https://api.lemonsqueezy.com/v1/licenses';

export async function validateLicense(licenseKey, instanceId) {
  const body = new URLSearchParams({ license_key: licenseKey.trim() });
  if (instanceId) body.set('instance_id', instanceId.trim());
  const res = await fetch(`${LICENSE_API}/validate`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  });
  const raw = await res.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return { ok: false, error: 'invalid license response' };
  }
  if (!data.valid) return { ok: false, error: data.error || 'invalid license' };
  const lk = data.license_key || {};
  if (lk.status !== 'active') return { ok: false, error: 'license not active' };
  if (instanceId) {
    const inst = data.instance || {};
    if (!inst.id || inst.id !== instanceId.trim()) return { ok: false, error: 'instance mismatch' };
  }
  return { ok: true };
}
