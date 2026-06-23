import { fetchOrder, verifyOrderRecord } from '../_order.js';

export async function onRequestGet(context) {
  const orderId = new URL(context.request.url).searchParams.get('order_id');
  if (!orderId || !/^\d+$/.test(orderId)) {
    return Response.json({ ok: false, error: 'missing order_id' }, { status: 400 });
  }

  const apiKey = context.env.LEMONSQUEEZY_API_KEY;
  if (!apiKey) {
    return Response.json({ ok: false, error: 'not configured' }, { status: 503 });
  }

  try {
    const order = await fetchOrder(orderId, apiKey);
    const storeId = context.env.LEMONSQUEEZY_STORE_ID || '';
    if (!verifyOrderRecord(order, storeId)) {
      return Response.json({ ok: false, error: 'not found' }, { status: 404 });
    }
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ ok: false, error: 'verify failed' }, { status: 502 });
  }
}
