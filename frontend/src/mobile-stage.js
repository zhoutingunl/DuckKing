import './mobile-stage.css';

// Move existing views, never clone canvases or create another renderer/scene.
// Comment anchors restore their exact desktop positions when the viewport widens.
for(const workspace of document.querySelectorAll('[data-mobile-workspace]')){
  const views=[...workspace.querySelectorAll('[data-mobile-stage]')];
  if(!views.length)continue;
  const toolbar=workspace.querySelector('[data-mobile-stage-toolbar]');
  const parts=[toolbar,...views].filter(Boolean);
  const anchors=parts.map(element=>{
    const anchor=document.createComment('desktop stage position');element.before(anchor);return {element,anchor};
  });
  const dock=document.createElement('div');dock.className='mobile-stage-dock';
  dock.classList.toggle('mobile-stage-pair',views.length>1);
  const row=document.createElement('div');row.className='mobile-stage-views';dock.append(row);
  const query=matchMedia('(max-width:760px) and (min-height:480px)');
  const update=()=>{
    if(query.matches){
      workspace.prepend(dock);
      if(toolbar)dock.prepend(toolbar);
      row.append(...views);
    }else{
      for(const {element,anchor} of anchors)anchor.after(element);
      dock.remove();
    }
    workspace.classList.toggle('mobile-stage-layout',query.matches);
  };
  query.addEventListener('change',update);update();
  window.addEventListener('pagehide',event=>{
    if(!event.persisted)query.removeEventListener('change',update);
  });
}
