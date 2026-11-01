// Invalidations coalesce into one frame. Static/hidden views do no rendering;
// OrbitControls can request another frame while its damping is still moving.
export function renderScheduler(draw,{
  interval=()=>33,now=()=>performance.now(),
  requestFrame=cb=>requestAnimationFrame(cb),cancelFrame=id=>cancelAnimationFrame(id),
  later=(cb,ms)=>setTimeout(cb,ms),cancelLater=id=>clearTimeout(id),
}={}){
  let dirty=false,visible=true,disposed=false,drawing=false,frame=null,timer=null,last=-Infinity;
  function cancel(){if(frame!==null)cancelFrame(frame);if(timer!==null)cancelLater(timer);frame=timer=null;}
  function schedule(){
    if(disposed||!visible||!dirty||drawing||frame!==null||timer!==null)return;
    const delay=Math.max(0,interval()-(now()-last));
    if(delay>0)timer=later(()=>{timer=null;schedule()},delay);
    else frame=requestFrame(()=>{frame=null;render()});
  }
  function render(){
    if(disposed||!visible||!dirty)return;
    dirty=false;drawing=true;
    try{if(draw())dirty=true}finally{drawing=false;last=now();schedule()}
  }
  return {
    invalidate(){if(disposed)return;dirty=true;schedule()},
    visible(value){if(disposed)return;visible=value;if(!value)cancel();else schedule()},
    flush(){if(disposed)return;cancel();dirty=true;render()},
    dispose(){disposed=true;dirty=false;cancel()},
  };
}
