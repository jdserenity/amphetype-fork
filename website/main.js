(function () {
  var toggle = document.querySelector('.nav-toggle');
  var mobileNav = document.getElementById('mobile-nav');
  if (toggle && mobileNav) {
    toggle.addEventListener('click', function () {
      var open = mobileNav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      mobileNav.hidden = !open;
    });
    mobileNav.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        mobileNav.classList.remove('is-open');
        mobileNav.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  var checkoutUrl = null;
  var notice = document.getElementById('checkout-notice');

  function configured(url) {
    return url && url.indexOf('YOUR_STORE') < 0 && url.indexOf('VARIANT_ID') < 0;
  }

  function showNotice() {
    if (!notice) return;
    notice.hidden = false;
    notice.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function onCheckoutClick(e) {
    e.preventDefault();
    if (configured(checkoutUrl)) {
      window.open(checkoutUrl, '_blank', 'noopener,noreferrer');
      return;
    }
    showNotice();
  }

  document.querySelectorAll('[data-checkout]').forEach(function (el) {
    el.addEventListener('click', onCheckoutClick);
  });

  fetch('checkout.json', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (cfg) {
      if (cfg && cfg.checkout_url) checkoutUrl = cfg.checkout_url;
      if (!configured(checkoutUrl) && notice) notice.hidden = false;
    })
    .catch(function () { if (notice) notice.hidden = false; });
})();
