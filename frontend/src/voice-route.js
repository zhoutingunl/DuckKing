// Describe routing without inferring action success or speaker playback from ready.
export function voiceRouteText({mode,state,route,reason='',asrMs,localFeedback=''}){
  const baseline=mode==='local_first'?'整句动作匹配后本地执行；完成后播放本地预录语音确认。':'灵矽负责识别和回复。';
  if(['disconnected','disconnecting','busy','awaiting_binding','recovering','interrupting'].includes(state))return baseline;
  if(state==='error')return '本轮语音未完成，请查看连接提示后重试。';
  if(state==='listening')return '正在接收本轮录音，松开后处理。';
  if(route==='cloud_fallback'){
    if(state==='ready')return '本轮由灵矽处理。';
    if(state==='speaking')return '灵矽正在回复本轮指令。';
    if(state==='connecting')return `${reason||'本地未匹配'}，正在连接灵矽并转交原录音。`;
    return `${reason||'本地未匹配'}，本轮转交灵矽处理，请稍候。`;
  }
  if(localFeedback)return `${localFeedback} · 本地反馈，本轮未调用灵矽。`;
  if(route==='local')return `本地识别 · 动作完整匹配${Number.isFinite(asrMs)?` · ${asrMs} ms`:''}`;
  if(route==='no_speech')return '未收到清晰语音，请重试。';
  if(mode==='local_first'&&state==='thinking')return '正在本地识别本轮录音。';
  return baseline;
}
