import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

LICENSE_API = 'https://api.lemonsqueezy.com/v1/licenses'
DEFAULT_CHECKOUT_URL = 'https://YOUR_STORE.lemonsqueezy.com/checkout/buy/VARIANT_ID'

_KEY = 'license_key'
_INSTANCE = 'license_instance_id'
_MACHINE = 'license_machine_id'


class LicenseError(Exception):
  pass


class LicenseNetworkError(LicenseError):
  pass


def checkout_url():
  return os.environ.get('TYPING_PROGRAM_CHECKOUT_URL', DEFAULT_CHECKOUT_URL)


def license_bypassed():
  if os.environ.get('TYPING_PROGRAM_SKIP_LICENSE', '').lower() in ('1', 'true', 'yes'):
    return True
  from typing_program import cli_options
  return getattr(cli_options, 'skip_license', False)


def stored_license(settings):
  key = (settings.value(_KEY, '', type=str) or '').strip()
  instance_id = (settings.value(_INSTANCE, '', type=str) or '').strip()
  return key, instance_id


def save_license(settings, license_key, instance_id):
  settings.setValue(_KEY, license_key.strip())
  settings.setValue(_INSTANCE, instance_id.strip())


def clear_license(settings):
  settings.remove(_KEY)
  settings.remove(_INSTANCE)


def machine_id(settings):
  mid = (settings.value(_MACHINE, '', type=str) or '').strip()
  if not mid:
    mid = str(uuid.uuid4())
    settings.setValue(_MACHINE, mid)
  return mid


def _post(path, fields, opener=None):
  open_fn = opener or urllib.request.urlopen
  body = urllib.parse.urlencode(fields).encode('utf-8')
  req = urllib.request.Request(
    LICENSE_API + path,
    data=body,
    headers={'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'},
    method='POST',
  )
  try:
    with open_fn(req, timeout=20) as resp:
      raw = resp.read().decode('utf-8')
  except urllib.error.URLError as e:
    raise LicenseNetworkError(str(e.reason or e)) from e
  try:
    return json.loads(raw)
  except json.JSONDecodeError as e:
    raise LicenseError('invalid response from license server') from e


def activate(license_key, instance_name, opener=None):
  data = _post('/activate', {'license_key': license_key.strip(), 'instance_name': instance_name}, opener=opener)
  if not data.get('activated'):
    err = data.get('error') or 'license activation failed'
    raise LicenseError(err)
  instance = data.get('instance') or {}
  instance_id = instance.get('id')
  if not instance_id:
    raise LicenseError('license server did not return an instance id')
  return data


def validate(license_key, instance_id=None, opener=None):
  fields = {'license_key': license_key.strip()}
  if instance_id:
    fields['instance_id'] = instance_id.strip()
  return _post('/validate', fields, opener=opener)


def is_validate_ok(data, instance_id=None):
  if not data.get('valid'):
    return False
  lk = data.get('license_key') or {}
  if lk.get('status') != 'active':
    return False
  if instance_id:
    inst = data.get('instance') or {}
    return bool(inst.get('id')) and inst.get('id') == instance_id
  return True


def ensure_licensed(app, settings, opener=None):
  if license_bypassed():
    return True
  key, instance_id = stored_license(settings)
  if key and instance_id:
    try:
      if is_validate_ok(validate(key, instance_id, opener=opener), instance_id):
        return True
      clear_license(settings)
    except LicenseNetworkError:
      return True
  from typing_program.LicenseDialog import LicenseDialog
  while True:
    dlg = LicenseDialog(settings, opener=opener)
    if dlg.exec_() != dlg.Accepted:
      return False
    key, instance_id = stored_license(settings)
    if key and instance_id:
      return True
