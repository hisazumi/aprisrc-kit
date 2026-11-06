const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem('apris-console-token') || '';
if (location.hash) { sessionStorage.setItem('apris-console-token', token); history.replaceState(null, '', '/console'); }
let state, operatorId = null, sequence = 0, busy = false, updating = false, active = null;
let seenEpoch, seenGuard, connected = false;
const id = () => crypto.randomUUID();
async function api(path, body) {
  const response = await fetch('/api/' + path, { method: body === undefined ? 'GET' : 'POST',
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(1500) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || response.statusText);
  return result;
}
function control(kind, fields = {}) {
  return api('control', { protocolVersion: 1, connectionEpoch: state.controlEpoch,
    requestId: id(), robotId: 'fake-only', kind, ...fields });
}
function runFields() { return { runId: state.control.runId, runEpoch: state.control.runEpoch }; }
function render() {
  if (!connected) { for (const button of document.querySelectorAll('button')) button.disabled = true; return; }
  const c = state.control, owned = operatorId && c.operatorId === operatorId;
  const stopped = !state.moving && !c.stopPending;
  $('owner').textContent = owned ? 'この画面が操作中' : c.operatorId ? '別の接続が操作中' : '未取得';
  $('motion').textContent = c.stopPending ? '処理中／停止確認待ち' : state.moving ? '移動中' : c.inhibited ? '移動禁止' : '待機';
  $('guard').textContent = c.guardId ? '受け渡し中（移動禁止）' : 'なし';
  const p = state.state.pose; $('pose').textContent = `x ${p.x.toFixed(3)} m / y ${p.y.toFixed(3)} m / ${p.yaw.toFixed(3)} rad`;
  $('connect').disabled = busy || !!c.operatorId || c.stopPending;
  $('stop').disabled = false;
  $('start').disabled = busy || !owned || !!c.runEpoch || !!c.guardId || c.inhibited || !stopped;
  $('close').disabled = busy || !owned || !c.runEpoch;
  $('recover').disabled = busy || !owned || !!c.runEpoch || !stopped || !$('clearance').checked;
  $('hold').disabled = state.serviceAttached || busy || !owned || !c.runEpoch || !!c.guardId || c.inhibited || !stopped;
  $('clear').disabled = busy || !owned || !c.guardId || !stopped || !$('clearance').checked;
  for (const k of ['move', 'turn']) $(k).disabled = state.serviceAttached || busy || !owned || !c.runEpoch || c.inhibited || !!c.guardId || !stopped || !!active;
  $('events').textContent = state.events.slice(-8).map(e => e.kind === 'terminal' ? `${e.outcome}: ${e.reason} / 証拠: ${e.evidence?.kind}` : `${e.kind}: ${e.reason || ''}`).join('\n') || 'まだ操作はありません';
}
async function refresh() {
  const next = await api('state');
  if (seenEpoch !== next.controlEpoch || seenGuard !== next.control.guardId) $('clearance').checked = false;
  if (seenEpoch && seenEpoch !== next.controlEpoch) { operatorId = null; active = null; }
  seenEpoch = next.controlEpoch; seenGuard = next.control.guardId; state = next; connected = true;
  if (operatorId !== state.control.operatorId) { operatorId = null; active = null; }
  if (active && state.events.some(e => e.kind === 'terminal' && e.operationId === active.operationId)) active = null;
  $('connection').textContent = '接続済み · 平面Simulator'; render();
}
function lost(error) {
  connected = false;
  operatorId = null; active = null; $('clearance').checked = false;
  $('connection').textContent = '操作接続が無効です。状態を再取得し、操作権と復帰を明示してください。';
  $('error').textContent = String(error);
  for (const button of document.querySelectorAll('button')) button.disabled = true;
}
for (const k of ['clearance']) $(k).onchange = () => state && render();
function action(name, fn) {
  $(name).onclick = async () => {
    if (!state || !connected) return;
    busy = true; $('error').textContent = ''; render();
    try { await fn(); await refresh(); } catch (e) { $('error').textContent = String(e); }
    finally { busy = false; if (state) render(); }
  };
}
action('connect', async () => { operatorId = (await control('openOperator')).operatorId; sequence = 0; });
action('stop', async () => { active = null; await control('globalStop'); });
action('recover', async () => {
  if (!$('clearance').checked) throw new Error('退避確認が必要です');
  await control('recover', { operatorId, guardId: state.control.guardId, confirmed: true }); $('clearance').checked = false;
});
action('start', () => control('openRun', { operatorId, runId: id() }));
action('close', () => control('closeRun', runFields()));
action('hold', () => control('acquireHandover', runFields()));
action('clear', async () => {
  if (!$('clearance').checked) throw new Error('退避確認が必要です');
  await control('clearHandover', { operatorId, guardId: state.control.guardId, confirmed: true }); $('clearance').checked = false;
});
async function move(goal) {
  const scope = { protocolVersion: 1, connectionEpoch: state.control.runEpoch,
    requestId: id(), robotId: 'fake-only', runId: state.control.runId, activityId: id(), operationId: id() };
  const accepted = await api('motion', { ...scope, kind: 'startMotion', goal });
  if (accepted.kind !== 'accepted') throw new Error(accepted.reason || '移動を受け付けませんでした');
  active = { ...scope, generation: accepted.generation };
}
action('move', () => move({ kind: 'move', distanceM: .04, speedMps: .1 }));
action('turn', () => move({ kind: 'turn', angleRad: .1, speedRadS: .7 }));
async function tick() {
  if (updating || document.hidden) return;
  updating = true;
  try {
    await refresh();
    if (operatorId) {
      await control('operatorHeartbeat', { operatorId, sequence: ++sequence });
      if (state.control.runEpoch && !state.serviceAttached) await control('runnerHeartbeat', { ...runFields(), sequence });
      await api('front', { clear: $('front').checked });
      if (active && state.operation && !state.operation.finishing)
        await api('motion', { ...active, kind: 'renewMotion', requestId: id() });
    }
  } catch (e) { lost(e); }
  finally { updating = false; }
}
await tick(); setInterval(tick, 100);
