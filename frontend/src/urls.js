// Resolve against the page directory, so the same build works at / and /duckking/.
export function appURL(path='') {
  return new URL(path.replace(/^\/+/,''),new URL('./',location.href));
}

export function socketURL(path) {
  const url=appURL(path);
  url.protocol=url.protocol==='https:'?'wss:':'ws:';
  return url;
}
