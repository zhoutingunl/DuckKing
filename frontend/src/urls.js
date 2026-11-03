export let currentRoom = null;
export let serviceInstance = null;
export let roomUnavailable = false;
export const setServiceInstance=value=>{serviceInstance=value};
export const setRoomUnavailable=value=>{roomUnavailable=value};
export const setRoom = room => { currentRoom = room; };

// Resolve against the page directory, so the same build works at / and /duckking/.
export function appURL(path='') {
  const url = new URL(path.replace(/^\/+/,''),new URL('./',location.href));
  if(currentRoom&&path.replace(/^\/+/,'').startsWith('api/')&&!path.includes('/rooms'))url.searchParams.set('room',currentRoom);
  const resource=path.replace(/^\/+/, '');
  if(serviceInstance&&(resource.startsWith('api/')&&!resource.startsWith('api/rooms')&&!resource.startsWith('api/models/microduck')))url.searchParams.set('server_instance',serviceInstance);
  return url;
}

export function socketURL(path) {
  const url=appURL(path);
  url.protocol=url.protocol==='https:'?'wss:':'ws:';
  return url;
}
