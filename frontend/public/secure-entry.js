// These public entries have certificates. Leave local/LAN HTTP development alone.
(function () {
  var page = new URL(window.location.href);
  if (page.protocol !== 'http:' || page.port) return;
  var duckking = page.hostname === 'duck.qbox.net';
  var gateway = page.hostname === 'ztmonitor.qbox.net' &&
    (page.pathname === '/duckking' || page.pathname.indexOf('/duckking/') === 0);
  if (!duckking && !gateway) return;
  page.protocol = 'https:';
  window.location.replace(page.href);
})();
