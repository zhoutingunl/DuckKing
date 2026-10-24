import './style.css';
import './statistics.css';
import './deploys.css';
import { appURL } from './urls.js';

const $ = id => document.getElementById(id);
const states = {ok:'版本一致',development:'本地开发',untracked:'缺少发布信息',unrecorded:'等待部署记录',mismatch:'运行版本与发布记录不一致',unknown:'发布信息异常'};
states.staged='后端就绪 · 等待 HTTPS 验证';
const notes = {ok:'当前进程与最近一次成功发布一致。',development:'当前服务未使用发布包，尚未部署。',untracked:'已有发布流水，但当前进程没有发布信息。',unrecorded:'当前版本尚无成功记录，可能正在部署或自检失败。',mismatch:'当前进程与最近一次成功发布不同，请检查服务或回滚结果。',unknown:'无法确认当前发布版本，请检查服务器发布信息。'};
notes.staged='独立后端已通过本机检查，HTTPS 入口和真实云端语音尚未完成验收。';
const time = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '—';
function node(tag,text,className='') { const el=document.createElement(tag);el.textContent=text;el.className=className;return el; }
function commitLink(commit) {
  if (!/^[a-f0-9]{40}$/.test(commit ?? '')) return node('span','—');
  const a=node('a',commit.slice(0,10),'commit-link');a.href=`https://github.com/zhoutingunl/DuckKing/commit/${commit}`;a.target='_blank';a.rel='noopener';return a;
}
function render(data) {
  const current=data.current;
  $('release-state').textContent=states[data.state] ?? '未知状态';
  $('release-version').textContent=current?.version ?? '开发工作台';
  $('release-commit').replaceChildren(commitLink(current?.commit));
  $('release-target').textContent=current?.target ?? '本地';
  $('release-built').textContent=time(current?.built_at);
  $('release-note').textContent=[notes[data.state],...data.warnings].filter(Boolean).join(' ');
  $('deploy-rows').replaceChildren();
  for (const row of data.records) {
    const tr=node('tr',''),version=node('td',''),operator=node('td',''),result=node('td','');
    version.append(node('strong',row.version),commitLink(row.commit));
    operator.append(node('span',row.operator ?? '—'),node('small',row.target ?? '—'));
    result.append(node('span',row.status==='staged'?'后端就绪，待接入':row.status==='success'?'部署成功':'部署失败',row.status==='success'?'deploy-success':row.status==='failed'?'deploy-failed':''));
    result.append(node('small',row.selftest==='passed'?'自检通过':row.selftest==='backend_passed'?'本机自检通过，待 HTTPS 验证':'自检未通过'));
    if (row.rollback && row.rollback!=='not_needed') result.append(node('small',({restored:'已恢复上一版本',failed:'恢复失败，请检查服务',not_available:'没有可恢复的旧版本',unchanged:'原版本未切换'})[row.rollback] ?? '回滚状态未知'));
    tr.append(version,node('td',time(row.ts)),operator,result);$('deploy-rows').append(tr);
  }
  $('deploy-empty').hidden=data.records.length>0;
}
let loading=false;
async function refresh() {
  if(loading)return;loading=true;$('refresh-deploys').disabled=true;
  try {
    const response=await fetch(appURL('api/deployments'),{cache:'no-store',signal:AbortSignal.timeout(8000)});
    if(!response.ok)throw new Error('unavailable');
    render(await response.json());$('deploy-error').hidden=true;
    $('deploy-updated').textContent=`更新于 ${new Date().toLocaleTimeString('zh-CN')} · 每 10 秒更新`;
  } catch {
    $('deploy-error').textContent='暂时无法读取部署记录，已显示的内容可能过期。请稍后刷新。';$('deploy-error').hidden=false;
  } finally {loading=false;$('refresh-deploys').disabled=false;}
}
$('refresh-deploys').addEventListener('click',refresh);
refresh();setInterval(()=>{if(!document.hidden)refresh();},10000);
