export let currentRoom = null;
export const setRoom = room => { currentRoom = room; };

// Resolve against the page directory, so the same build works at / and /duckking/.
export function appURL(path='') {
  const url = new URL(path.replace(/^\/+/,''),new URL('./',location.href));
  if(currentRoom&&path.replace(/^\/+/,'').startsWith('api/')&&!path.includes('/rooms'))url.searchParams.set('room',currentRoom);
  return url;
}

export function socketURL(path) {
  const url=appURL(path);
  url.protocol=url.protocol==='https:'?'wss:':'ws:';
  return url;
}
