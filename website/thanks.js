(function () {
  var ok = document.getElementById('thanks-ok');
  var denied = document.getElementById('thanks-denied');
  var loading = document.getElementById('thanks-loading');
  if (!ok || !denied || !loading) return;

  function show(el) {
    ok.hidden = el !== ok;
    denied.hidden = el !== denied;
    loading.hidden = el !== loading;
  }

  var params = new URLSearchParams(window.location.search);
  var orderId = params.get('order_id');
  if (!orderId) {
    show(denied);
    return;
  }

  fetch('/api/verify-order?order_id=' + encodeURIComponent(orderId), { cache: 'no-store' })
    .then(function (r) { return r.json().then(function (body) { return { status: r.status, body: body }; }); })
    .then(function (res) {
      if (res.status === 200 && res.body && res.body.ok) show(ok);
      else show(denied);
    })
    .catch(function () { show(denied); });
})();
