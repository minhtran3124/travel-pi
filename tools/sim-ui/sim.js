// Live 2D lobby client. Connects to the bus over WebSocket, turns UI-contract-v1
// events (design §5.7) into scene state, and renders an isometric room (option B,
// style-study 2026-09-25) plus the side panel and roster. No build step, no CDN.

const W = 960, H = 520;

// --- isometric projection of the floor-plan coordinates the sim runs on ---
const K = .76, OX = 436, OY = 70;
const iso = (x, y) => ({ x: OX + (x - y) * K, y: OY + (x + y) * K / 2 });
const RW = 640, RD = 520, WALL_H = 56;
const DOOR = { x: 24, y: 470 }, EXIT = { x: 616, y: 470 }, AISLE_Y = 300, QUEUE_Y = 470;
const qSlot = i => ({ x: 84 + i * 40, y: QUEUE_Y });

// --- deterministic persona palette (batch_start only gives id/name/cc/language) ---
const BODY = ['#C0504D', '#4F7CAC', '#8E6BB0', '#D08A3A', '#3E8E7E', '#B5577E', '#5B8C5A', '#C77F3B'];
const SKIN = ['#F1C9A5', '#F3D6C1', '#9C6645', '#EFC8A6', '#D6A17A', '#C48660', '#E8B98C', '#7A4A2B'];
const HAIR = ['#1F1A17', '#D9A441', '#1C1410', '#3A2419', '#171311', '#6B3A1E', '#2E2A26', '#4A2E1A'];
const VERDICTS = new Set(['pass', 'warn', 'fail']);
const MAX_SEATS = 6;
function hash(s){ let h = 2166136261; for (let i = 0; i < s.length; i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
const pick = (arr, id, salt) => arr[hash(id + salt) % arr.length];

const TOOL_ICON = name => {
  const n = (name || '').toLowerCase();
  if (n.includes('flight')) return '✈';
  if (n.includes('hotel')) return '🏨';
  if (n.includes('budget') || n.includes('expense')) return '💰';
  if (n.includes('weather') || n.includes('climate')) return '🌤';
  if (n.includes('place') || n.includes('search')) return '🔎';
  return '⚙';
};

// --- DOM helpers ---
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const mmss = t => `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
const statusLabel = s => ({ pending: 'not arrived', queued: 'queued', talking: 'at desk', grading: 'grading', ungraded: 'ungraded', skipped: 'skipped', aborted: 'aborted', pass: 'pass', warn: 'warn', fail: 'fail', error: 'error' }[s] || s);
const LEAVE_STATUS = { done: 'grading', max_turns: 'grading', quota: 'skipped', aborted: 'aborted', driver_error: 'error', bot_error: 'error' };

const canvas = $('scene');
let ctx = null;
try { ctx = canvas && canvas.getContext ? canvas.getContext("2d") : null; } catch (e){ ctx = null; }
const mm = q => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(q) : null);
const reduceMedia = mm('(prefers-reduced-motion: reduce)');
const reduceMotion = !!(reduceMedia && reduceMedia.matches);
const now = () => (typeof performance !== 'undefined' ? performance : Date).now();

let T = {};
function readTokens(){
  if (typeof getComputedStyle === 'undefined') return;
  const cs = getComputedStyle(document.documentElement);
  for (const k of ['floor', 'tile', 'ink', 'muted', 'faint', 'line', 'desk', 'desk-top', 'stool', 'bot-bubble',
    'bot-bubble-ink', 'user-bubble', 'user-bubble-line', 'ok', 'warn', 'fail', 'info', 'lime', 'on-accent',
    'estimated', 'board', 'panel', 'panel-raised', 'lime-soft', 'robot', 'robot-line'])
    T[k] = cs.getPropertyValue('--' + k).trim();
}

// --- scene state, rebuilt from scratch on each batch_start (covers reconnect replay) ---
let state, selected = null, tab = 't', animT = 0;

function seatXs(n){
  if (n <= 1) return [310];
  const lo = 150, hi = 470;
  return Array.from({ length: n }, (_, i) => Math.round(lo + i * (hi - lo) / (n - 1)));
}

function makePerson(meta){
  const id = meta.id;
  return {
    id,
    name: meta.name || id,
    cc: meta.country_code || '',
    lang: meta.language || '',
    color: pick(BODY, id, ''),
    skin: pick(SKIN, id, 'skin'),
    hair: pick(HAIR, id, 'hair'),
    phase: 'pending', x: DOOR.x, y: DOOR.y, path: [], walk: 0,
    seat: null, seatIdx: null, turns: 0, transcript: [],
    status: 'pending', stream: null, bubble: null, grade: null,
  };
}

function resetBatch(personas, seats, batchId){
  const requested = Number.isFinite(seats) ? seats : (Array.isArray(seats) ? seats.length : 3);
  const n = Math.max(1, Math.min(MAX_SEATS, requested));
  state = {
    tMs: 0, q5: 0, q7: 0, resets: null, requestedSeats: requested,
    order: [], people: new Map(), queue: [], events: [],
    total: personas.length, ended: false, summary: null, departed: 0, batchId: batchId || null,
    seats: seatXs(n).map((x, i) => ({ i, x, y: 204, busy: null, sub: null, tool: null, bubble: null, approval: false })),
  };
  if (requested > n) warn(`batch_start requested ${requested} seats; rendering ${n} (layout cap)`);
  for (const meta of personas){
    const p = makePerson(meta);
    state.people.set(p.id, p);
    state.order.push(p.id);
  }
  if (!state.people.has(selected)) selected = state.order[0] || null;
}
resetBatch([], 3);

const person = id => state.people.get(id);

// --- event stream warnings (visible in the #events tab) ---
function warn(message){
  if (!state) return;
  state.events.push({ t: state.tMs, type: 'ui_warning', persona_id: null, message });
  if (state.events.length > 500) state.events.shift();
}

// --- event handling ---
function handle(ev){
  if (!ev || typeof ev !== 'object') return;
  if (typeof ev.t === 'number') state.tMs = ev.t;
  const p = ev.persona_id != null ? person(ev.persona_id) : null;
  switch (ev.type){
    case 'batch_start': {
      resetBatch(Array.isArray(ev.personas) ? ev.personas : [], ev.seats, ev.batch);
      break;
    }
    case 'persona_queue': {
      if (!p) break;
      p.phase = 'queue'; p.status = 'queued';
      if (!state.queue.includes(p)) state.queue.push(p);
      break;
    }
    case 'walk_to_desk': {
      if (!p) break;
      const seat = state.seats[ev.seat];
      if (!seat){ warn(`walk_to_desk: seat ${ev.seat} out of range (${state.seats.length} seats)`); break; }
      const i = state.queue.indexOf(p); if (i >= 0) state.queue.splice(i, 1);
      seat.busy = p; seat.sub = null; seat.tool = null; seat.bubble = null; seat.approval = false;
      p.seat = seat; p.seatIdx = seat.i;
      p.path = [{ x: p.x, y: AISLE_Y }, { x: seat.x, y: AISLE_Y }, { x: seat.x, y: seat.y }];
      p.phase = 'walking'; p.status = 'talking';
      break;
    }
    case 'user_say': {
      if (!p) break;
      p.turns++;
      if (p.seat) p.seat.bubble = null;
      p.bubble = { text: ev.text || '', until: animT + 4 };
      p.transcript.push({ who: 'user', text: ev.text || '' });
      break;
    }
    case 'bot_subagent': {
      if (p && p.seat) p.seat.sub = ev.name;
      break;
    }
    case 'bot_tool': {
      if (!p || !p.seat) break;
      const status = ev.status || 'running';
      const seat = p.seat;
      // only a running event creates or replaces the chip; a result settles the
      // chip it correlates to by id and never overwrites a different running one
      if (status === 'running'){
        seat.tool = { id: ev.id != null ? ev.id : null, name: ev.name, status, until: 0 };
        p.transcript.push({ who: 'tool', text: ev.name });
      } else if (seat.tool){
        const cur = seat.tool;
        const idMatch = ev.id != null && cur.id != null && String(cur.id) === String(ev.id);
        if (idMatch || ((ev.id == null || cur.id == null) && cur.status === 'running')){
          cur.status = status; cur.until = animT + 1.6;
        }
      }
      break;
    }
    case 'bot_token': {
      if (!p) break;
      if (!p.stream) p.stream = { text: '' };
      p.stream.text += ev.text || '';
      if (p.seat) p.seat.bubble = { who: 'bot', text: p.stream.text };
      break;
    }
    case 'bot_reset': {
      if (!p) break;
      p.stream = null;
      if (p.seat) p.seat.bubble = null;
      break;
    }
    case 'bot_done': {
      if (!p) break;
      const reply = ev.reply != null ? ev.reply : (p.stream ? p.stream.text : '');
      if (reply.trim()){
        if (p.seat) p.seat.bubble = { who: 'bot', text: reply };
        p.transcript.push({ who: 'bot', text: reply });
      } else if (!p.awaitingApproval){
        p.transcript.push({ who: 'error', text: '(empty reply)' });
      }
      p.awaitingApproval = false;
      p.stream = null;
      break;
    }
    case 'bot_interrupt': {
      if (!p) break;
      if (p.seat) p.seat.approval = true;
      p.awaitingApproval = true;
      p.transcript.push({ who: 'approval', text: `Tin asks to approve (${ev.kind || 'approval'})` });
      break;
    }
    case 'bot_error': {
      if (!p) break;
      p.status = 'error';
      if (p.seat) p.seat.tool = { name: (p.seat.tool && p.seat.tool.name) || 'turn', status: 'error', until: animT + 3 };
      p.transcript.push({ who: 'error', text: `bot_error · ${ev.code || 'error'}: ${ev.message || ''}` });
      break;
    }
    case 'persona_leave': {
      if (!p) break;
      const qi = state.queue.indexOf(p); if (qi >= 0) state.queue.splice(qi, 1);
      const seat = p.seat;
      if (seat){ Object.assign(seat, { busy: null, sub: null, tool: null, bubble: null, approval: false }); }
      p.seat = null;
      const from = seat ? { x: seat.x, y: AISLE_Y } : { x: p.x, y: AISLE_Y };
      const slot = state.departed++;
      p.path = [from, { x: EXIT.x, y: AISLE_Y }, { x: EXIT.x, y: EXIT.y }, { x: EXIT.x - 44 - (slot % 8) * 46, y: EXIT.y + 34 + Math.floor(slot / 8) * 34 }];
      p.phase = 'leaving'; p.leaveReason = ev.reason || 'done'; p.left = true;
      if (p.status !== 'error') p.status = LEAVE_STATUS[p.leaveReason] || 'grading';
      break;
    }
    case 'session_graded': {
      if (!p) break;
      let verdict = null;
      if (VERDICTS.has(ev.verdict)) verdict = ev.verdict;
      else if (ev.verdict != null) warn(`session_graded: invalid verdict ${JSON.stringify(ev.verdict)}`);
      p.grade = { score: ev.score, verdict };
      if (verdict){ p.status = verdict; p.transcript.push({ who: 'grade', text: '', score: ev.score, verdict }); }
      break;
    }
    case 'quota': {
      if (typeof ev.five_hour === 'number') state.q5 = ev.five_hour;
      if (typeof ev.seven_day === 'number') state.q7 = ev.seven_day;
      state.resets = ev.resets_at || state.resets;
      break;
    }
    case 'batch_end': {
      state.ended = true; state.summary = ev.summary || null;
      for (const q of state.people.values()) if (q.status === 'grading') q.status = 'ungraded';
      break;
    }
  }
  state.events.push(ev);
  if (state.events.length > 500) state.events.shift();
}

// --- tweened walking ---
function update(dt){
  animT += dt;
  if (!state) return;
  state.queue.forEach((p, i) => {
    const s = qSlot(i), last = p.path[p.path.length - 1] || p;
    if (last.x !== s.x || last.y !== s.y) p.path = [s];
  });
  for (const id of state.order){
    const p = state.people.get(id);
    if (p.path.length){
      const tgt = p.path[0], dx = tgt.x - p.x, dy = tgt.y - p.y, d = Math.hypot(dx, dy), step = 170 * dt;
      p.walk += dt;
      if (d <= step || reduceMotion){ p.x = tgt.x; p.y = tgt.y; p.path.shift(); }
      else { p.x += dx / d * step; p.y += dy / d * step; }
      if (!p.path.length){
        if (p.phase === 'walking') p.phase = 'seated';
        else if (p.phase === 'leaving') p.phase = 'gone';
      }
    }
  }
}

// --- drawing ---
function roundRect(x, y, w, h, r){ ctx.beginPath(); ctx.roundRect(x, y, w, h, r); }
function wrap(text, maxW, maxLines){
  const words = String(text).split(' '), lines = []; let cur = '';
  for (const w of words){
    const t = cur ? cur + ' ' + w : w;
    if (ctx.measureText(t).width > maxW && cur){ lines.push(cur); cur = w; } else cur = t;
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines){
    const keep = lines.slice(0, maxLines); let last = keep[maxLines - 1];
    while (ctx.measureText(last + '…').width > maxW && last.length) last = last.slice(0, -1);
    keep[maxLines - 1] = last + '…'; return keep;
  }
  return lines;
}
function poly(pts, fill, stroke){
  ctx.beginPath(); pts.forEach((q, i) => i ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y)); ctx.closePath();
  if (fill){ ctx.fillStyle = fill; ctx.fill(); }
  if (stroke){ ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
}
const up = (q, h) => ({ x: q.x, y: q.y - h });
function ground(x0, y0, x1, y1, fill, stroke){ poly([iso(x0, y0), iso(x1, y0), iso(x1, y1), iso(x0, y1)], fill, stroke); }
function box(x0, y0, x1, y1, h, top, front, side){
  const a = iso(x0, y1), b = iso(x1, y1), c = iso(x1, y0);
  poly([a, b, up(b, h), up(a, h)], front);
  poly([b, c, up(c, h), up(b, h)], side);
  poly([up(iso(x0, y0), h), up(c, h), up(b, h), up(a, h)], top);
}
function pill(cx, cy, label, bg, fg, font){
  ctx.font = font || '500 10.5px Menlo, monospace';
  const w = Math.round(ctx.measureText(label).width + 18);
  ctx.fillStyle = bg; roundRect(cx - w / 2, cy - 10, w, 20, 10); ctx.fill();
  ctx.fillStyle = fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(label, cx, cy + .5); ctx.textAlign = 'left';
}
function bubble(x, y, text, dark, caption, below){
  ctx.font = '500 11.5px Inter, sans-serif';
  const lines = wrap(text || '…', 150, dark ? 2 : 3), capH = caption ? 15 : 0;
  const h = 14 + capH + lines.length * 15, bw = 168, top = below ? y : y - h;
  ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.14)'; ctx.shadowBlur = 12; ctx.shadowOffsetY = 3;
  ctx.fillStyle = dark ? T['bot-bubble'] : T['user-bubble']; roundRect(x, top, bw, h, 10); ctx.fill(); ctx.restore();
  ctx.fillStyle = dark ? T['bot-bubble'] : T['user-bubble'];
  ctx.beginPath();
  if (below){ ctx.moveTo(x + 10, y + 1); ctx.lineTo(x + 6, y - 8); ctx.lineTo(x + 22, y + 1); }
  else { ctx.moveTo(x + 10, y - 1); ctx.lineTo(x + 2, y + 8); ctx.lineTo(x + 22, y - 1); }
  ctx.fill();
  ctx.textBaseline = 'top';
  if (caption){ ctx.fillStyle = dark ? T.lime : T.muted; ctx.font = '600 10px Inter, sans-serif'; ctx.fillText(caption, x + 10, top + 7); ctx.font = '500 11.5px Inter, sans-serif'; }
  ctx.fillStyle = dark ? T['bot-bubble-ink'] : T.ink;
  lines.forEach((l, i) => ctx.fillText(l, x + 10, top + 8 + capH + i * 15));
}
const ringColor = s => ({ talking: T.info, grading: T.muted, ungraded: T.muted, skipped: T.muted, aborted: T.muted, pass: T.ok, warn: T.warn, fail: T.fail, error: T.fail }[s] || null);
const verdictColor = v => v === 'pass' ? T.ok : v === 'warn' ? T.warn : (v === 'fail' || v === 'error') ? T.fail : null;

function drawRobot(s){
  const q = iso(s.x, 78), busy = !!s.busy, bob = reduceMotion ? 0 : Math.sin(animT * 2 + s.i) * 1.2;
  ctx.fillStyle = 'rgba(0,0,0,.12)'; ctx.beginPath(); ctx.ellipse(q.x, q.y, 16, 8, 0, 0, 7); ctx.fill();
  ctx.fillStyle = T.board; roundRect(q.x - 13, q.y - 32 + bob, 26, 32, 11); ctx.fill();
  roundRect(q.x - 15, q.y - 58 + bob, 30, 24, 8); ctx.fill();
  const blink = !reduceMotion && (animT * 1.3 + s.i) % 4 < .12;
  ctx.fillStyle = busy ? T.lime : T.muted;
  roundRect(q.x - 9, q.y - 51 + bob, 5, blink ? 1.5 : 9, 2.5); ctx.fill();
  roundRect(q.x + 4, q.y - 51 + bob, 5, blink ? 1.5 : 9, 2.5); ctx.fill();
  ctx.strokeStyle = T.board; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(q.x, q.y - 58 + bob); ctx.lineTo(q.x, q.y - 66 + bob); ctx.stroke();
  ctx.fillStyle = busy ? T.lime : T.muted; ctx.beginPath(); ctx.arc(q.x, q.y - 68 + bob, 3.5, 0, 7); ctx.fill();
}

function drawPerson(p){
  const q = iso(p.x, p.y), moving = p.path.length > 0 && !reduceMotion;
  const bob = moving ? Math.abs(Math.sin(p.walk * 9)) * 2.4 : 0, x = q.x, y = q.y;
  ctx.fillStyle = 'rgba(0,0,0,.13)'; ctx.beginPath(); ctx.ellipse(x, y, 12, 6, 0, 0, 7); ctx.fill();
  const rc = p.id === selected ? T.lime : ringColor(p.status);
  if (rc){ ctx.strokeStyle = rc; ctx.lineWidth = p.id === selected ? 3 : 2.5; ctx.beginPath(); ctx.ellipse(x, y, 15, 7.5, 0, 0, 7); ctx.stroke(); }
  ctx.fillStyle = p.color; roundRect(x - 8, y - 27 - bob, 16, 25, 8); ctx.fill();
  ctx.fillStyle = p.skin; ctx.beginPath(); ctx.arc(x, y - 35 - bob, 7.5, 0, 7); ctx.fill();
  ctx.fillStyle = p.hair; ctx.beginPath(); ctx.arc(x, y - 36.5 - bob, 7.8, Math.PI * 1.05, Math.PI * 1.95); ctx.fill();
  ctx.fillStyle = T.ink; ctx.font = '500 10.5px Inter, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillText(p.name.split(' ')[0], x, y + 9); ctx.textAlign = 'left';
  const vc = verdictColor(p.status);
  if (vc && (p.phase === 'leaving' || p.phase === 'gone')){
    ctx.fillStyle = vc; ctx.beginPath(); ctx.arc(x + 10, y - 46 - bob, 7, 0, 7); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.font = '700 9px Inter, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(p.status === 'pass' ? '✓' : p.status === 'warn' ? '!' : '✕', x + 10, y - 45.5); ctx.textAlign = 'left';
  }
}

function avatarSVG(p){
  return `<svg viewBox="0 0 24 24" width="100%" height="100%" aria-hidden="true">
    <rect x="7" y="12" width="10" height="13" rx="5" fill="${p.color}"/>
    <circle cx="12" cy="8.5" r="4.6" fill="${p.skin}"/>
    <path d="M7.2 8 A4.9 4.9 0 0 1 16.8 8 Z" fill="${p.hair}"/></svg>`;
}

function draw(){
  if (!ctx) return;
  ctx.fillStyle = T.floor || '#f4f4f2'; ctx.fillRect(0, 0, W, H);
  poly([iso(0, 0), iso(RW, 0), up(iso(RW, 0), WALL_H), up(iso(0, 0), WALL_H)], T.panel, T.line);
  poly([iso(0, 0), iso(0, RD), up(iso(0, RD), WALL_H), up(iso(0, 0), WALL_H)], T['panel-raised'], T.line);
  const wq = up(iso(0, 330), 26);
  ctx.save(); ctx.transform(.894, -.447, 0, 1, wq.x, wq.y);
  ctx.fillStyle = T.muted; ctx.font = '700 12px Inter, sans-serif'; ctx.textBaseline = 'middle';
  ctx.fillText('TIN · TRAVEL ASSISTANT DESK', 0, 0); ctx.restore();
  for (let i = 0; i < RW / 40; i++) for (let j = 0; j < RD / 40; j++)
    ground(i * 40, j * 40, i * 40 + 40, j * 40 + 40, (i + j) % 2 ? T.panel : T['panel-raised'], T.line);
  ground(0, 446, 48, 494, T['lime-soft']); ground(592, 446, 640, 494, T['lime-soft']);
  for (const s of state.seats) ground(s.x - 20, s.y - 14, s.x + 20, s.y + 14, T['lime-soft']);
  for (const s of state.seats) drawRobot(s);
  box(100, 96, 520, 132, 26, T['desk-top'], T.desk, T.board);
  for (const yy of [446, 494]){
    const posts = [64, 150, 236, 322].map(x => iso(x, yy));
    ctx.strokeStyle = T.muted; ctx.lineWidth = 2.5; ctx.beginPath();
    posts.forEach((q, i) => i ? ctx.lineTo(q.x, q.y - 16) : ctx.moveTo(q.x, q.y - 16)); ctx.stroke();
    for (const q of posts){ ctx.fillStyle = T.board; roundRect(q.x - 2.5, q.y - 20, 5, 20, 2.5); ctx.fill(); ctx.beginPath(); ctx.arc(q.x, q.y - 20, 3.5, 0, 7); ctx.fill(); }
  }
  const dq = iso(24, 470), eq = iso(616, 470);
  pill(dq.x, dq.y - 44, 'ARRIVALS', T.board, T.lime, '700 10.5px Inter, sans-serif');
  pill(eq.x + 30, eq.y - 62, 'EXIT', T.board, T.lime, '700 10.5px Inter, sans-serif');

  for (const s of state.seats){
    if (s.tool && s.tool.until && s.tool.status !== 'running' && animT > s.tool.until) s.tool = null;
    const f = up(iso(s.x, 118), 30);
    if (s.approval) pill(f.x, f.y, 'Approve booking?', T.lime, T['on-accent'], '600 11px Inter, sans-serif');
    else if (s.tool && s.tool.name){
      const c = s.tool.status === 'error' ? T.fail : s.tool.status === 'ok' ? T.ok : T.lime;
      const mark = s.tool.status === 'running' ? '⟳ ' : s.tool.status === 'ok' ? '✓ ' : '✕ ';
      pill(f.x, f.y, mark + TOOL_ICON(s.tool.name) + ' ' + s.tool.name, T.board, c);
    }
  }
  const drawOrder = state.order.map(id => state.people.get(id))
    .filter(p => p.phase !== 'pending').sort((a, b) => (a.x + a.y) - (b.x + b.y));
  for (const p of drawOrder) drawPerson(p);
  for (const s of state.seats){
    const q = iso(s.x, 70), cap = `Tin ${s.i + 1}${s.sub ? ' · ' + s.sub : ''}`;
    if (s.bubble) bubble(q.x - 20, q.y - 78, s.bubble.text.length > 64 ? '…' + s.bubble.text.slice(-62) : s.bubble.text, true, cap);
    else { ctx.fillStyle = T.muted; ctx.font = '600 10.5px Inter, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.fillText(cap, q.x, q.y - 76); ctx.textAlign = 'left'; }
  }
  for (const p of drawOrder) if (p.bubble && animT < p.bubble.until){ const q = iso(p.x, p.y); bubble(q.x + 8, q.y + 26, p.bubble.text, false, p.name.split(' ')[0], true); }
  if (state.ended) pill(W / 2, H / 2, 'Batch complete', T.board, T.lime, '600 14px Inter, sans-serif');
}

// --- DOM rendering ---
function renderHeader(){
  const done = state.order.filter(id => state.people.get(id).left).length;
  $('done-count').textContent = `${done}/${state.total}`;
  $('batch-id').textContent = state.batchId || '—';
  $('inflight').textContent = `${state.seats.filter(s => s.busy).length}/${state.seats.length}`;
  $('clock').textContent = mmss(state.tMs / 1000);
  const c5 = Math.max(0, Math.min(1, state.q5)), c7 = Math.max(0, Math.min(1, state.q7));
  $('quota-5h').style.transform = `scaleX(${c5})`; $('quota-5h-pct').textContent = (c5 * 100).toFixed(0) + '%';
  $('quota-7d').style.transform = `scaleX(${c7})`; $('quota-7d-pct').textContent = (c7 * 100).toFixed(0) + '%';
}
function renderPanel(){
  const p = person(selected);
  const card = $('card');
  if (!p){ card.innerHTML = '<p class="empty">Waiting for the batch to start.</p>'; $('transcript').innerHTML = ''; $('events').innerHTML = ''; return; }
  const score = p.grade && typeof p.grade.score === 'number' ? p.grade.score.toFixed(1) : null;
  card.innerHTML = `
    <div class="card-head">
      <span class="avatar">${avatarSVG(p)}</span>
      <div><h2>${esc(p.name)}</h2><p>${esc(p.cc)} · ${esc(p.lang)} · sim-${esc(p.id)}</p></div>
      <span class="pill label s-${esc(p.status)}">${esc(statusLabel(p.status))}</span>
    </div>
    <dl class="facts">
      <dt>Turns</dt><dd>${p.turns}</dd>
      <dt>Seat</dt><dd>${p.seatIdx != null ? 'Tin ' + (p.seatIdx + 1) : '—'}</dd>
      <dt>Score</dt><dd>${score != null ? score + '/5' : '—'}</dd>
    </dl>`;
  const tr = $('transcript');
  tr.innerHTML = p.transcript.length ? p.transcript.map(m => {
    if (m.who === 'grade') return `<li class="m-grade"><strong>Graded ${esc(m.verdict || '')}${typeof m.score === 'number' ? ' · ' + m.score.toFixed(1) + '/5' : ''}.</strong> ${esc(m.text || '')}</li>`;
    return `<li class="m-${m.who}">${esc(m.text)}</li>`;
  }).join('') : `<li class="empty">${p.phase === 'pending' ? 'This traveller has not arrived yet.' : 'Waiting in the queue for a free seat.'}</li>`;
  if (tab === 't') tr.scrollTop = tr.scrollHeight;
  const ev = $('events');
  ev.innerHTML = state.events.slice(-80).reverse().map(e => {
    const { t, type, persona_id, ...rest } = e;
    return `<li><em>${((t || 0) / 1000).toFixed(1)}</em> <b>${esc(type)}</b> ${persona_id != null ? esc(persona_id) : '·'} ${esc(JSON.stringify(rest))}</li>`;
  }).join('');
}
function renderRoster(){
  $('roster').innerHTML = state.order.map(id => {
    const p = state.people.get(id);
    const graded = p.grade && typeof p.grade.score === 'number';
    return `<tr data-id="${esc(p.id)}" aria-selected="${p.id === selected}" tabindex="0">
      <td><span class="who"><span class="avatar">${avatarSVG(p)}</span>${esc(p.name)}</span></td>
      <td>${esc(p.cc)}</td><td>${esc(p.lang)}</td>
      <td class="num">${p.turns}</td>
      <td><span class="pill label s-${esc(p.status)}">${esc(statusLabel(p.status))}</span></td>
      <td class="num">${graded ? p.grade.score.toFixed(1) : '—'}</td>
    </tr>`;
  }).join('');
}
function syncDOM(){ renderHeader(); renderRoster(); renderPanel(); }

function select(id){ if (!state.people.has(id)) return; selected = id; renderRoster(); renderPanel(); }

// --- listeners ---
$('roster').addEventListener('click', e => { const tr = e.target.closest('tr'); if (tr) select(tr.dataset.id); });
$('roster').addEventListener('keydown', e => { if (e.key === 'Enter'){ const tr = e.target.closest('tr'); if (tr) select(tr.dataset.id); } });
if (canvas) canvas.addEventListener('click', e => {
  const r = canvas.getBoundingClientRect(), x = (e.clientX - r.left) * W / r.width, y = (e.clientY - r.top) * H / r.height;
  const hit = state.order.map(id => state.people.get(id))
    .filter(p => p.phase !== 'pending')
    .find(p => { const q = iso(p.x, p.y); return Math.abs(q.x - x) < 15 && y > q.y - 46 && y < q.y + 8; });
  if (hit) select(hit.id);
});
$('tab-t').addEventListener('click', () => setTab('t'));
$('tab-e').addEventListener('click', () => setTab('e'));
function setTab(t){
  tab = t; $('tab-t').setAttribute('aria-selected', t === 't'); $('tab-e').setAttribute('aria-selected', t === 'e');
  $('transcript').hidden = t !== 't'; $('events').hidden = t !== 'e'; renderPanel();
}

function resize(){
  if (!ctx) return;
  const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1, w = canvas.clientWidth || W;
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(w * H / W * dpr);
  ctx.setTransform(canvas.width / W, 0, 0, canvas.height / H, 0, 0);
}
if (typeof window !== 'undefined') window.addEventListener('resize', resize);
if (reduceMedia && reduceMedia.addEventListener) reduceMedia.addEventListener('change', () => {});
const retheme = () => readTokens();
const darkMedia = mm('(prefers-color-scheme: dark)');
if (darkMedia && darkMedia.addEventListener) darkMedia.addEventListener('change', retheme);
if (typeof MutationObserver !== 'undefined')
  new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

// --- WebSocket transport with auto-reconnect (bus replays history on connect) ---
function setConn(cls, text){
  const el = $('conn'); if (!el) return;
  el.className = 'conn is-' + cls; $('conn-text').textContent = text;
}
let reconnectDelay = 800;
function connect(){
  if (typeof WebSocket === 'undefined'){ setConn('off', 'No WebSocket'); return; }
  const host = (typeof location !== 'undefined' && location.host) || 'localhost:8765';
  const url = `ws://${host}/ws`;
  const urlEl = $('conn-url'); if (urlEl) urlEl.textContent = url;
  setConn('connecting', 'Connecting…');
  let ws;
  try { ws = new WebSocket(url); }
  catch (e){ setConn('off', 'Reconnecting…'); scheduleReconnect(); return; }
  ws.onopen = () => { reconnectDelay = 800; setConn('live', 'Live'); };
  ws.onmessage = e => {
    let data; try { data = JSON.parse(e.data); } catch (err){ return; }
    if (Array.isArray(data)) data.forEach(handle); else handle(data);
    syncDOM();
  };
  ws.onerror = () => { try { ws.close(); } catch (e){} };
  ws.onclose = () => { setConn('off', 'Reconnecting…'); scheduleReconnect(); };
}
function scheduleReconnect(){
  setTimeout(connect, reconnectDelay);
  reconnectDelay = Math.min(8000, reconnectDelay * 1.6);
}

// --- boot ---
readTokens(); resize(); syncDOM();
const raf = (typeof requestAnimationFrame !== 'undefined') ? requestAnimationFrame : cb => setTimeout(() => cb(now()), 16);
let last = now(), acc = 0;
function frame(t){
  const dt = Math.min(.05, (t - last) / 1000); last = t;
  update(dt);
  draw();
  acc += dt;
  if (acc > .2){ acc = 0; renderHeader(); }
  raf(frame);
}
raf(frame);
connect();
