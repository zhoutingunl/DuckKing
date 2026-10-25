import './style.css';
import './statistics.css';
import './deploys.css';
import { appURL } from './urls.js';

const $ = id => document.getElementById(id);
const states = {ok:'版本一致',development:'本地开发',untracked:'缺少发布信息',unrecorded:'等待部署记录',mismatch:'运行版本与发布记录不一致',unknown:'发布信息异常'};
states.staged='后端就绪 · 等待完整验收';
const notes = {ok:'当前进程与最近一次成功发布一致。',development:'当前服务未使用发布包，尚未部署。',untracked:'已有发布流水，但当前进程没有发布信息。',unrecorded:'当前版本尚无成功记录，可能正在部署或自检失败。',mismatch:'当前进程与最近一次成功发布不同，请检查服务或回滚结果。',unknown:'无法确认当前发布版本，请检查服务器发布信息。'};
notes.staged='独立后端已通过本机检查，HTTPS 入口和真实云端语音尚未完成验收。';
const time = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '—';
function node(tag,text,className='') { const el=document.createElement(tag);el.textContent=text;el.className=className;return el; }
function commitLink(commit) {
  if (!/^[a-f0-9]{40}$/.test(commit ?? '')) return node('span','—');
  const a=node('a',commit.slice(0,10),'commit-link');a.href=`https://github.com/zhoutingunl/DuckKing/commit/${commit}`;a.target='_blank';a.rel='noopener';return a;
}
function changesCell(row,expanded) {
  const cell=node('td','','deploy-changes');
  const valid=value=>/^[a-f0-9]{40}$/.test(value??'');
  if(valid(row.previous_commit)&&valid(row.commit)){
    const rollback=row.change_state==='rollback';
    const link=node('a',`${rollback?'回退前版本':'对比上次成功部署'} ${row.previous_commit.slice(0,10)}`,'compare-link');
    const [base,head]=rollback?[row.commit,row.previous_commit]:[row.previous_commit,row.commit];
    link.href=`https://github.com/zhoutingunl/DuckKing/compare/${base}...${head}`;
    link.target='_blank';link.rel='noopener';cell.append(link);
  }
  const messages={unavailable:'此版本缺少完整提交记录，可通过提交或对比链接查看。',identical:'提交与上次成功部署相同。',rollback:'回退至较早提交，上方链接列出被回退的提交。',initial:'无更早成功记录，列出此版本的提交历史。'};
  if(messages[row.change_state])cell.append(node('small',messages[row.change_state]));
  const entries=Array.isArray(row.changes)?row.changes.filter(item=>valid(item?.commit)&&typeof item.subject==='string').slice(0,50):[];
  const entry=item=>{
    const line=node('div','','change-entry');line.append(commitLink(item.commit),node('span',item.subject));return line;
  };
  entries.slice(0,3).forEach(item=>cell.append(entry(item)));
  if(entries.length>3){
    const details=node('details','','change-more');details.dataset.record=`${row.version}|${row.ts}`;
    details.open=expanded.has(details.dataset.record);
    details.append(node('summary',`展开其余 ${entries.length-3} 项`));
    entries.slice(3).forEach(item=>details.append(entry(item)));cell.append(details);
  }
  if(row.change_count>entries.length)cell.append(node('small',`共 ${row.change_count} 项，当前列出 ${entries.length} 项。`));
  if(!row.change_state&&!entries.length)cell.append(node('small','此版本尚未记录变更提交。'));
  return cell;
}
function coverageCell(row,metric) {
  const coverage=row.coverage,counts=coverage?.[metric];
  const cell=node('td','','deploy-coverage');
  if(coverage?.scope!=='backend'||coverage.commit!==row.commit||!Number.isInteger(counts?.covered)||!Number.isInteger(counts?.total)||counts.total<=0||counts.covered<0||counts.covered>counts.total){
    cell.append(node('span','未记录'));return cell;
  }
  const label=`${(100*counts.covered/counts.total).toFixed(2)}%`;
  const safe=/^https:\/\/github\.com\/zhoutingunl\/DuckKing\/actions\/runs\/[0-9]+$/.test(coverage.source_url??'');
  const value=node(safe?'a':'span',label,'coverage-value');
  if(safe){value.href=coverage.source_url;value.target='_blank';value.rel='noopener'}
  value.title=`${counts.covered} / ${counts.total}`;
  cell.append(value,node('small','后端'));return cell;
}
function render(data) {
  const current=data.current;
  const publicReady=data.state==='staged'&&data.records[0]?.selftest==='https_passed_cloud_pending';
  $('release-state').textContent=states[data.state] ?? '未知状态';
  if(publicReady)$('release-state').textContent='HTTPS 已验证 · 等待云端验收';
  $('release-version').textContent=current?.version ?? '开发工作台';
  $('release-commit').replaceChildren(commitLink(current?.commit));
  $('release-target').textContent=current?.target ?? '本地';
  $('release-built').textContent=time(current?.built_at);
  $('release-note').textContent=[publicReady?'HTTPS 页面、API 与语音传输已通过检查；服务器设备绑定及真实灵矽对话仍待验收。':notes[data.state],...data.warnings].filter(Boolean).join(' ');
  const expanded=new Set([...$('deploy-rows').querySelectorAll('details[open]')].map(el=>el.dataset.record));
  $('deploy-rows').replaceChildren();
  for (const row of data.records) {
    const tr=node('tr',''),version=node('td',''),operator=node('td',''),result=node('td','');
    version.append(node('strong',row.version),commitLink(row.commit));
    operator.append(node('span',row.operator ?? '—'),node('small',row.target ?? '—'));
    result.append(node('span',row.status==='staged'?'服务就绪，待完整验收':row.status==='success'?'部署成功':'部署失败',row.status==='success'?'deploy-success':row.status==='failed'?'deploy-failed':''));
    result.append(node('small',row.selftest==='passed'?'自检通过':row.selftest==='https_passed_cloud_pending'?'HTTPS 验证通过，云端语音待验收':row.selftest==='backend_passed'?'本机自检通过，待 HTTPS 验证':'自检未通过'));
    if (row.rollback && row.rollback!=='not_needed') result.append(node('small',({restored:'已恢复上一版本',failed:'恢复失败，请检查服务',not_available:'没有可恢复的旧版本',unchanged:'原版本未切换'})[row.rollback] ?? '回滚状态未知'));
    tr.append(version,node('td',time(row.ts)),operator,result,coverageCell(row,'lines'),coverageCell(row,'branches'),changesCell(row,expanded));$('deploy-rows').append(tr);
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
