
def is_paid_order(attrs):
  if not attrs:
    return False
  return attrs.get('status') == 'paid' and not attrs.get('refunded')


def verify_order_record(order, store_id=''):
  if not order or order.get('type') != 'orders':
    return False
  attrs = order.get('attributes') or {}
  if store_id and str(attrs.get('store_id')) != str(store_id):
    return False
  return is_paid_order(attrs)


def test_is_paid_order():
  assert is_paid_order({'status': 'paid', 'refunded': False}) is True
  assert is_paid_order({'status': 'paid', 'refunded': True}) is False
  assert is_paid_order({'status': 'pending', 'refunded': False}) is False


def test_verify_order_record_store():
  order = {'type': 'orders', 'attributes': {'status': 'paid', 'refunded': False, 'store_id': 9}}
  assert verify_order_record(order, '9') is True
  assert verify_order_record(order, '1') is False
