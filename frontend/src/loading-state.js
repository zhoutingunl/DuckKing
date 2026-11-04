const labels={request:'正在请求模型信息',cache:'正在读取模型缓存',cache_write:'正在保存已验证的模型缓存',download:'正在接收官方外观',parse:'正在校验模型数据',assemble:'正在组装模型',draw:'正在绘制第一帧',backend:'服务器正在准备物理场景',waiting:'正在等待服务器准备场景',policies:'服务器正在准备动作策略',models:'服务器正在编译物理模型',settling:'服务器正在稳定初始姿态',retry:'网络或响应超时，正在重试一次'};
export function loadingError(error){
  if(error?.name==='TimeoutError')return '等待超时，请检查网络后重试。';
  if(error instanceof TypeError||/Failed to fetch|Load failed|NetworkError/i.test(error?.message??''))return '模型下载中断，请检查网络后重新加载。';
  return error?.message||'暂时无法加载，请重试。';
}
export function createLoadingState(node){
  let current;
  return {
    get active(){return !!current?.active},
    begin({phase='backend',cancel,retry,retryLabel='重新加载模型'}={}){
      current?.stop();const began=performance.now(),label=document.createElement('span'),detail=document.createElement('small'),bar=document.createElement('progress'),actions=document.createElement('span');
      node.classList.add('loading-feedback');node.hidden=false;node.setAttribute('role','status');node.replaceChildren(label,detail,bar,actions);
      const session={active:true,phase,detail:{},stop(){clearInterval(timer);document.removeEventListener('visibilitychange',render);session.active=false},
        progress(value){if(current!==session||!session.active)return;session.detail=typeof value==='string'?{phase:value}:value;session.phase=session.detail.phase??session.phase;render()},
        ready(){if(current!==session)return;session.stop();session.outcome='ready';node.hidden=true},
        cancelled(){if(current!==session)return;session.stop();session.outcome='cancelled';bar.hidden=true;label.textContent='已停止等待';detail.textContent='可以重新选择；服务器可能仍在完成已受理的准备工作。';actions.replaceChildren();if(retry)add(retryLabel,retry)},
        setRetry(callback,text='重新加载模型'){retry=callback;retryLabel=text},
        fail(error){if(current!==session)return;session.stop();session.outcome='failed';node.hidden=false;node.setAttribute('role','alert');bar.hidden=true;label.textContent='加载未完成';detail.textContent=loadingError(error);actions.replaceChildren();if(retry)add(retryLabel,retry)},
      };
      function add(text,callback){const button=document.createElement('button');button.type='button';button.className='load-action';button.textContent=text;button.addEventListener('click',callback);actions.append(button)}
      function render(){if(current!==session)return;const d=session.detail;let text=labels[session.phase]??labels.backend;
        if(Number.isFinite(d.total)&&d.total>0)text+=` ${d.completed??0}/${d.total}`;
        label.textContent=text;const elapsed=Math.floor((performance.now()-began)/1000);
        let extra='首次访问或网络较慢时可能更久';
        if(Number.isFinite(d.loaded)){extra=`已接收 ${(d.loaded/1048576).toFixed(1)} MB（解压后）`;}
        if(d.totalBytes>0&&d.loaded<=d.totalBytes){bar.max=d.totalBytes;bar.value=d.loaded;extra=`${Math.floor(d.loaded/d.totalBytes*100)}% · ${extra}`;}else bar.removeAttribute('value');
        detail.textContent=`已等待 ${elapsed} 秒 · ${extra}${document.hidden?' · 页面在后台，显示可能延后':''}`;
      }
      current=session;if(cancel)add('停止等待',cancel);const timer=setInterval(render,1000);document.addEventListener('visibilitychange',render);render();return session;
    },
    cancel(){current?.cancelled()},
  };
}
