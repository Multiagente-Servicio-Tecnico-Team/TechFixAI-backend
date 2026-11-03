const $ = id => document.getElementById(id);
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST',
    headers: {'Content-Type': 'application/json', 'X-Portal-Request': '1'},
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) showLogin();
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Revisa los datos enviados.');
  }
  return data;
}
function showLogin() { $('access').hidden = false; $('chat').hidden = true; $('messages').replaceChildren(); }
function render(message) {
  $('empty')?.remove();
  const bubble = document.createElement('div');
  bubble.className = `bubble ${message.role === 'user' ? 'user' : 'assistant'}`;
  const author = document.createElement('span'); author.className = 'author';
  author.textContent = message.role === 'user' ? 'Tú' : 'Asistente';
  bubble.append(author, document.createTextNode(message.content));
  if (message.quote) {
    const q = message.quote, details = document.createElement('div'); details.className = 'quote';
    details.textContent = `MANO DE OBRA\n${q.labor.map(i => `${i.description} × ${i.quantity}: S/ ${i.amount}`).join('\n') || 'Pendiente'}\nREPUESTOS\n${q.parts.map(i => `${i.description} × ${i.quantity}: S/ ${i.amount}`).join('\n') || 'Pendiente'}\nTOTAL: ${q.total === null ? 'Pendiente de datos' : `S/ ${q.total}`}\n${q.missing_data.join('\n')}`;
    bubble.append(details);
  }
  $('messages').append(bubble); $('messages').scrollTop = $('messages').scrollHeight;
}
async function load() {
  const data = await api('/api/messages');
  $('access').hidden = true; $('chat').hidden = false;
  $('welcome').textContent = `Hola, ${data.username}`;
  $('messages').replaceChildren();
  if (!data.messages.length) {
    const empty = document.createElement('p'); empty.id = 'empty'; empty.textContent = '¿Qué necesitas hoy? Puedo ayudarte con soporte técnico, componentes, cotizaciones o garantías.'; $('messages').append(empty);
  }
  data.messages.forEach(render);
}
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; $('status').textContent = '';
  try { await api('/api/login', {username: $('username').value, password: $('password').value}); $('password').value = ''; await load(); }
  catch (error) { $('status').textContent = error.message; }
  finally { button.disabled = false; }
});
$('message-form').addEventListener('submit', async event => {
  event.preventDefault(); const message = $('message').value.trim(); if (!message) return;
  $('send').disabled = true; $('status').textContent = 'Preparando respuesta…';
  try { const reply = await api('/api/chat', {message}); render({role:'user', content:message}); render(reply); $('message').value = ''; $('status').textContent = ''; }
  catch (error) { $('status').textContent = error.message; }
  finally { $('send').disabled = false; $('message').focus(); }
});
$('logout').addEventListener('click', async () => {
  try { await api('/api/logout', {}); showLogin(); $('status').textContent = ''; }
  catch (error) { $('status').textContent = error.message; }
});
load().catch(error => { showLogin(); if (error.message !== 'Inicia sesión para continuar') $('status').textContent = error.message; });
