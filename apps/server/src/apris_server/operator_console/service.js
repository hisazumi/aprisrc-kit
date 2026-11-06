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
    $('connection').textContent = state.live ? 'サービス実行中' : 'サービス待機／終了';
    const key = JSON.stringify([state.runEpoch, state.prompt?.id, state.answered]);
    if (key !== last) {
      last = key; $('answers').replaceChildren(); $('result').textContent = '';
      $('question').textContent = state.prompt?.message || '質問を待っています';
      if (state.answered) $('result').textContent = state.prompt.stationary ? '回答済み。運用者の退避確認を待っています。' : '回答済み';
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
