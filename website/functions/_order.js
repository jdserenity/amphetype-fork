export function isPaidOrder(attrs) {
  if (!attrs) return false;
  return attrs.status === 'paid' && !attrs.refunded;
}

export async function fetchOrder(orderId, apiKey) {
  const res = await fetch(`https://api.lemonsqueezy.com/v1/orders/${encodeURIComponent(orderId)}`, {
    headers: {
      Accept: 'application/vnd.api+json',
      Authorization: `Bearer ${apiKey}`,
    },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`lemon squeezy api ${res.status}`);
  const body = await res.json();
  return body.data || null;
}

export function verifyOrderRecord(order, storeId) {
  if (!order || order.type !== 'orders') return false;
  const attrs = order.attributes || {};
  if (storeId && String(attrs.store_id) !== String(storeId)) return false;
  return isPaidOrder(attrs);
}
