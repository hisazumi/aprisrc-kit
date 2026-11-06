const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem('apris-console-token') || '';
if (location.hash) { sessionStorage.setItem('apris-console-token', token); history.replaceState(null, '', '/app'); }
async function api(path, body) {
  const response = await fetch('/api/service/' + path, { method: body === undefined ? 'GET' : 'POST',
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(1500) });
  const value = await response.json(); if (!response.ok) throw new Error(value.detail); return value;
}
let viewId, last = '', busy = false;
async function tick() {
  if (busy) return; busy = true;
  try {
    const state = await api('state');
    $('messages').textContent = state.messages.join('\n');
    const ending = state.result;
    const label = ending?.status === 'completed' ? '正常終了' : ending?.status === 'failed' ? '失敗して終了' : ending ? '中断しました' : '未開始';
    $('connection').textContent = state.live ? 'サービス実行中' : label;
    const key = JSON.stringify([state.runEpoch, state.prompt?.id, state.answered, state.result]);
    if (key !== last) {
      last = key; $('answers').replaceChildren(); $('result').textContent = '';
      $('question').textContent = state.prompt?.message || (state.live ? '処理中です' : ending ? label : '運用コンソールで準備し、サービスを開始してください');
      if (!state.live && ending) $('result').textContent = ending.status === 'completed' ? 'サービスが最後まで完了しました。' : 'サービスは終了しています。再実行には運用側の操作が必要です。理由: ' + ending.reason;
      else if (state.answered) $('result').textContent = state.prompt.stationary ? '回答済み。運用者の退避確認を待っています。' : '回答済み';
      else if (state.prompt) for (const choice of state.prompt.choices) {
        const button = document.createElement('button'); button.textContent = choice;
        button.onclick = async () => {
          for (const b of $('answers').querySelectorAll('button')) b.disabled = true;
          try {
            await api('answer', { viewId, runEpoch: state.runEpoch, questionId: state.prompt.id, value: choice });
            last = ''; await tick();
          } catch (e) { $('result').textContent = '回答を受け付けませんでした：' + String(e); }
        };
        $('answers').append(button);
      }
    }
  } catch (e) { $('connection').textContent = '接続を確認してください：' + String(e); $('answers').replaceChildren(); last = ''; }
  finally { busy = false; }
}
try { ({ viewId } = await api('view', {})); await tick(); setInterval(tick, 200); }
catch (e) { $('connection').textContent = String(e); }
