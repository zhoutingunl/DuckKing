import './site-nav.js';
import './style.css';
import './training.css';

// This lightweight selection page needs no room claim, model, physics or timers.
// Carry an existing shared room into the chosen scene; the scene owns validation.
const room=new URL(location.href).searchParams.get('room');
if(room&&/^\d+$/.test(room)){
 for(const link of document.querySelectorAll('a[href]')){
  const target=new URL(link.href);if(target.origin!==location.origin)continue;
  target.searchParams.set('room',room);link.href=target;
 }
}
