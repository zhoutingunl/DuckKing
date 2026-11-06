import {templates} from './ui-templates.js';
const escape = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const literalSize=source=>source.replace(/\{\d+\}/g,'').length;
const compiled = [...templates].sort((a,b)=>literalSize(b[0])-literalSize(a[0])).map(([source,en,fr,rawValues]) => {
  const regex = new RegExp('^'+source.split(/\{\d+\}/).map(escape).join('(.*?)')+'$');
  const format = text => (...values) => text.replace(/\{(\d+)\}/g, (_,index)=>values[Number(index)]);
  return [regex, format(en), format(fr), true, rawValues];
});
// Parameterized UI messages. Captures are translated separately, never evaluated.
export const patterns = [
 ...compiled,
 [/^(\d{2}) (.+)$/, (n,s)=>`${n} ${s}`, (n,s)=>`${n} ${s}`],
 [/^房间\s*(\d+)\s*·\s*独立语音与场景$/, n=>`Room ${n} · private voice and scene`, n=>`Salon ${n} · voix et scénario privés`],
 [/^房间\s*(\d+)$/, n=>`Room ${n}`, n=>`Salon ${n}`],
 [/^(\d+)\s*\/\s*(\d+)\s*个房间\s*·\s*物理场景\s*(\d+)\s*\/\s*(\d+)$/, (a,b,c,d)=>`${a} / ${b} rooms · physics ${c} / ${d}`, (a,b,c,d)=>`${a} / ${b} salons · physique ${c} / ${d}`],
 [/^(\d+)\s*个房间\s*·\s*物理场景\s*(\d+)\s*\/\s*(\d+)$/, (a,c,d)=>`${a} rooms · physics ${c} / ${d}`, (a,c,d)=>`${a} salons · physique ${c} / ${d}`],
 [/^本地识别 · 动作完整匹配(?: · (\d+) ms)?$/, n=>`Local recognition · full action match${n?` · ${n} ms`:''}`, n=>`Reconnaissance locale · correspondance complète${n?` · ${n} ms`:''}`],
 [/^正在(.+)$/, s=>`In progress: ${s}`, s=>`En cours : ${s}`],
 [/^(.+) · 完成$/, s=>`${s} · completed`, s=>`${s} · terminé`],
 [/^(.+) · 失败$/, s=>`${s} · failed`, s=>`${s} · échec`],
 [/^(.+) · 已取消$/, s=>`${s} · cancelled`, s=>`${s} · annulé`],
 [/^第\s*(\d+)\s*关\s*·\s*(.+)$/, (n,s)=>`Level ${n} · ${s}`, (n,s)=>`Niveau ${n} · ${s}`],
 [/^第\s*(\d+)\s*幕$/, n=>`Act ${n}`, n=>`Scène ${n}`],
 [/^([\d,.]+)\s*步$/, n=>`${n} steps`, n=>`${n} étapes`],
 [/^([\d,.]+)\s*秒$/, n=>`${n} s`, n=>`${n} s`],
 [/^([\d,.]+)\s*次$/, n=>`${n} times`, n=>`${n} fois`],
 [/^展开其余 (\d+) 项$/, n=>`Show ${n} more`, n=>`Afficher ${n} autres`],
 [/^对比上次成功部署 (.+)$/, id=>`Compared with last successful deployment ${id}`, id=>`Comparé au dernier déploiement réussi ${id}`],
 [/^更新于 (.+) · 每 (\d+) 秒更新$/, (time,n)=>`Updated ${time} · refreshes every ${n} s`, (time,n)=>`Mis à jour à ${time} · toutes les ${n} s`],
 [/^本地后端请求失败（HTTP (\d+)），请检查服务与端口。$/, n=>`Local request failed (HTTP ${n}). Check the service and port.`, n=>`Échec de la requête locale (HTTP ${n}). Vérifie le service et le port.`],
 [/^连接未成功，请检查绑定、额度与网络（(.+)）$/, reason=>`Connection failed. Check binding, quota and network (${reason}).`, reason=>`Échec de connexion. Vérifie liaison, quota et réseau (${reason}).`],
];
