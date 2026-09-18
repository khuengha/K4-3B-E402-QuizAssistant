/* Shared live-room UI for the teacher workspace and the account-free player page. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const playerPage = document.body.dataset.livePlayer === 'true';
  const root = document.createElement('section');
  root.id = 'live-root'; root.hidden = true; root.setAttribute('aria-label', 'Live Quiz');
  document.body.append(root);
  let session = null, state = null, pollTimer = null, tickTimer = null, busy = false;
  let resumeButton = null;
  let clockOffset = 0, lastView = '', snapshot = [], returnFocus = null, remaining = 0;
  const read = (storage, key) => { try { return JSON.parse(storage.getItem(key)); } catch { return null; } };
  const write = (storage, key, value) => { try { value ? storage.setItem(key, JSON.stringify(value)) : storage.removeItem(key); } catch {} };
  const icons = {book:'<path d="M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1v14"/>',play:'<path d="m8 5 11 7-11 7Z"/>',cup:'<path d="M7 4h10v6a5 5 0 0 1-10 0V4Zm5 11v5m-4 0h8M7 6H3v3a4 4 0 0 0 4 4m10-7h4v3a4 4 0 0 1-4 4"/>'};
  const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name]}</svg>`;
  const btn = (action, label, variant = '', disabled = false) => `<button type="button" class="live-btn ${variant}" data-live="${action}" ${disabled?'disabled':''}>${label}</button>`;
  function frame(body, label = 'CÙNG CHƠI · CÙNG HIỂU') {
    root.innerHTML = `<div class="live-shell"><header class="live-header"><div class="live-brand"><span>${icon('book')}</span>lessonleaf <b>LIVE</b></div><div class="live-header-right"><span class="live-online" id="live-connection">Đang kết nối</span>${btn('exit', playerPage?'Rời màn hình':'Về bộ quiz','quiet')}</div></header><main class="live-main"><div class="live-eyebrow">${label}</div><div id="live-error" role="alert" hidden></div>${body}</main><footer class="live-footer"><span>Học cùng nhau, tiến bộ cùng nhau.</span><span>Đúng +1.000 điểm · Không tính tốc độ</span></footer></div>`;
  }
  function open() {
    returnFocus = document.activeElement; root.hidden = false; document.body.classList.add('live-open');
    if (!playerPage) { root.setAttribute('role','dialog'); root.setAttribute('aria-modal','true'); }
    for (const node of document.body.children) if (node !== root && !['SCRIPT','SVG'].includes(node.tagName)) node.inert = true;
  }
  function message(text) { const el = $('#live-error'); if (el) { el.textContent = text; el.hidden = !text; } }
  function connection(text, offline = false) { const el=$('#live-connection'); if(el){el.textContent=text;el.classList.toggle('offline',offline);} }
  function stop() { clearTimeout(pollTimer); clearInterval(tickTimer); }
  function exit() {
    if(session?.role==='host'&&state?.phase==='closed'){write(sessionStorage,'lessonleaf-host',null);session=null;}
    if(resumeButton){resumeButton.hidden=!session;resumeButton.textContent=session?'Mở phòng '+session.pin:'Mở phòng';}
    stop(); root.hidden=true; document.body.classList.remove('live-open');
    for (const node of document.body.children) node.inert=false;
    if (playerPage) { location.href = 'live.html'; return; }
    returnFocus?.focus();
  }
  async function api(path, data, authenticated=true) {
    const controller=new AbortController(); const timeout=setTimeout(()=>controller.abort(),8000);
    try {
      const response=await fetch('/api/rooms'+path,{method:data===undefined?'GET':'POST',signal:controller.signal,
        headers:{'Content-Type':'application/json',...(authenticated&&session?{Authorization:'Bearer '+session.token}:{})},
        ...(data===undefined?{}:{body:JSON.stringify(data)})});
      const result=await response.json().catch(()=>({error:'Server Live Quiz chưa chạy. Khởi động bằng python server.py.'}));
      if(!response.ok){const e=new Error(result.error||result.detail||'Không thể kết nối phòng.');e.status=response.status;throw e;}
      return result;
    } catch(e) { if(e.name==='AbortError'||e instanceof TypeError)throw new Error('Mất kết nối server. Kiểm tra mạng rồi thử lại; phòng vẫn giữ dữ liệu trên server.'); throw e; }
    finally { clearTimeout(timeout); }
  }
  function saveSession() { write(session.role==='host'?sessionStorage:localStorage,session.role==='host'?'lessonleaf-host':'lessonleaf-player-'+session.pin,session); }
  function accept(data) { if(state&&(data.round<state.round||(data.round===state.round&&(data.seq<state.seq||(data.seq===state.seq&&data.answerCount<state.answerCount)))))return;state=data;clockOffset=data.serverTime-Date.now();const signature=JSON.stringify({...data,serverTime:0});if(signature!==lastView){lastView=signature;renderRoom();}updateClock();connection('Đã đồng bộ'); }
  async function poll() {
    clearTimeout(pollTimer);
    if(root.hidden||!session)return;
    try { accept(await api('/'+session.pin)); }
    catch(e) { connection('Đang kết nối lại…',true);message(e.message);if(e.status===401||e.status===404){stop();message(e.message+' Dùng nút rời màn hình để tham gia lại.');write(session.role==='host'?sessionStorage:localStorage,session.role==='host'?'lessonleaf-host':'lessonleaf-player-'+session.pin,null);return;} }
    if(!root.hidden)pollTimer=setTimeout(poll,1000);
  }
  function startSession(credentials) {
    stop();session=credentials;state=null;lastView='';saveSession();
    frame('<div class="live-empty"><div class="live-spinner"></div><h1>Đang vào phòng…</h1></div>');
    poll();tickTimer=setInterval(updateClock,200);
  }
  function setup() {
    open();
    const saved=read(sessionStorage,'lessonleaf-host');
    if(saved?.role==='host'&&saved.pin&&saved.token){startSession(saved);return;}
    if(location.protocol==='file:'){
      frame(`<div class="live-empty">${icon('play')}<h1>Sẵn sàng mở lớp học trực tiếp</h1><p>Live Quiz cần server để đồng bộ nhiều người chơi.</p><code>python server.py</code><p>Sau đó mở <strong>http://localhost:8000</strong>, tạo và duyệt bộ quiz.</p></div>`);connection('Chưa kết nối server',true);return;
    }
    snapshot=typeof getApprovedLiveQuiz==='function'?getApprovedLiveQuiz():[];
    frame(`<div class="live-setup"><div class="live-sticker">LET’S PLAY</div><h1>Một bộ quiz.<br>Cả lớp cùng khám phá.</h1><p>Chỉ <strong>${snapshot.length} câu đã duyệt</strong> sẽ được đưa vào phòng.<br>Đáp án và nguồn được giữ nguyên từ bộ quiz của bạn.</p><form id="live-create-form"><label for="live-duration">Thời gian cho mỗi câu</label><select id="live-duration"><option value="15">15 giây</option><option value="20">20 giây</option><option value="30" selected>30 giây</option><option value="45">45 giây</option><option value="60">60 giây</option><option value="90">90 giây</option></select><label for="live-capacity">Số người tham gia tối đa</label><input id="live-capacity" type="number" min="1" max="100" step="1" value="30" required aria-describedby="live-capacity-help"><p id="live-capacity-help" class="live-small">Từ 1–100 người, không tính giảng viên. Phòng sẽ ngừng nhận người mới khi đủ chỗ.</p><button class="live-btn purple" type="submit" ${snapshot.length?'':'disabled'}>Tạo phòng chơi ${icon('play')}</button></form><div class="live-rules"><span>Không cần tài khoản</span><span>1.000 điểm / câu đúng</span><span>Giảng viên điều khiển</span></div></div>`);
    connection('Thiết lập phòng');$('#live-duration')?.focus();
  }
  function joinScreen(pin='') {
    frame(`<div class="live-join"><div class="live-sticker mint">YOUR NEXT CHALLENGE</div><h1>Kiến thức lên sóng.<br>Bạn đã sẵn sàng?</h1><p>Nhập mã phòng và tên để cùng lớp tham gia.</p><form id="live-join-form"><label for="live-pin">Mã phòng / PIN</label><input id="live-pin" name="pin" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" minlength="6" placeholder="000 000" value="${escape(pin)}" required autocomplete="off"><label for="live-name">Tên hiển thị</label><input id="live-name" name="name" placeholder="Tên của bạn" maxlength="30" required autocomplete="nickname"><button type="submit" class="live-btn purple">Tham gia phòng →</button></form><p class="live-small">Không cần tài khoản · Tên hiển thị với cả lớp</p></div>`,'PLAY QUIZ · THAM GIA');connection('Chưa vào phòng');(pin?$('#live-name'):$('#live-pin'))?.focus();
  }
  function ranking(rows, final=false) {
    return `<section class="live-ranking"><div class="live-section-heading"><h2>${icon('cup')} ${final?'Bảng xếp hạng cuối cùng':'Leaderboard tạm thời'}</h2><span>Cùng điểm, cùng hạng</span></div><div class="live-table-wrap"><table><thead><tr><th>Hạng</th><th>Người chơi</th><th>Điểm</th><th>Đúng</th><th>Sai</th><th>Bỏ lỡ</th></tr></thead><tbody>${rows.map(p=>`<tr class="${p.id===state.me?.id?'is-me':''}"><td><span class="live-rank rank-${p.rank}">${p.rank}</span></td><td>${escape(p.name)}${p.id===state.me?.id?' <small>(Bạn)</small>':''}</td><td><strong>${p.score.toLocaleString('vi-VN')}</strong></td><td>${p.correct}</td><td>${p.wrong}</td><td>${p.skipped}</td></tr>`).join('')}</tbody></table></div></section>`;
  }
  function topicReport(topics, personal=false) {
    const wrong=topics.filter(t=>t.wrong>0);
    return `<section class="live-topic-report"><h2>${personal?'Chủ đề bạn cần ôn lại':'Chủ đề cả lớp trả lời sai nhiều nhất'}</h2>${wrong.length?wrong.map(t=>`<div class="live-topic-row"><strong>${escape(t.topic)}</strong><div class="live-topic-track"><i style="width:${Math.max(8,Math.round(t.wrong/Math.max(...wrong.map(x=>x.wrong))*100))}%"></i></div><span>${t.wrong} ${personal?'câu sai':'lượt sai'}</span></div>`).join(''):'<p>Chưa ghi nhận câu trả lời sai.</p>'}<p class="live-small">Câu bỏ lỡ được thống kê riêng, không tính là trả lời sai.</p></section>`;
  }
  function hostButtons() {
    if(state.role!=='host')return '';
    let main='';
    if(state.phase==='lobby')main=btn('start','Start Quiz '+icon('play'),'purple',state.players.length===0);
    if(state.phase==='question')main=btn('reveal','Kết thúc câu & xem đáp án','yellow');
    if(state.phase==='reveal')main=btn('next',state.current.index+1===state.questionCount?'Xem kết quả cuối →':'Câu tiếp theo →','purple');
    if(state.phase==='finished')main=btn('restart','Chơi lại cùng bộ quiz','purple');
    return `<div class="live-host-controls">${main}${['question','reveal'].includes(state.phase)?btn('restart','Restart quiz','quiet'):''}${state.phase!=='closed'?btn('close','Kết thúc phòng','danger'):btn('new','Về bộ quiz','quiet')}</div>`;
  }
  function roomHeader() { return `<div class="live-room-heading"><div><h1>${escape(state.title)}</h1><p>${state.questionCount} câu đã duyệt <span>·</span> Lượt ${state.round} <span>·</span> ${state.duration} giây/câu</p></div><div class="live-pin-small">PIN <b>${state.pin}</b><span>${state.role==='host'?'GIẢNG VIÊN':escape(state.me?.name)}</span></div></div>`; }
  function renderRoom() {
    if(!state)return;
    const focusKey=root.contains(document.activeElement)?document.activeElement?.dataset.live:null;
    const host=state.role==='host',q=state.current;
    let body=roomHeader();
    if(state.phase==='lobby') {
      const link=new URL('live.html?room='+state.pin,location.href).href;
      body+=`<div class="live-lobby-grid"><section class="live-pin-card"><span class="live-eyebrow">${host?'MỜI CẢ LỚP CÙNG THAM GIA':'BẠN ĐÃ VÀO PHÒNG'}</span><h2>${host?'Một mã phòng, cùng một thử thách.':'Sẵn sàng vào cuộc!'}</h2><div class="live-pin-number">${state.pin.slice(0,3)} ${state.pin.slice(3)}</div><p>${host?'Người học mở link và nhập tên, không cần tài khoản.':'Chờ giảng viên bắt đầu. Hãy giữ màn hình này mở.'}</p>${host?`<label for="live-link">Link tham gia</label><div class="live-copy"><input id="live-link" readonly value="${escape(link)}" aria-label="Link tham gia">${btn('copy','Sao chép')}</div>${['localhost','127.0.0.1','[::1]'].includes(location.hostname)?'<p class="live-small">Để thiết bị khác tham gia: mở trang bằng IP LAN của máy host rồi chia sẻ link đó. Các thiết bị cần cùng mạng Wi-Fi.</p>':''}`:''}<div class="live-rules"><span>Đúng +1.000 điểm</span><span>Không tính tốc độ</span></div></section><section class="live-players-card"><div class="live-section-heading"><h2>Phòng chờ</h2><span class="live-capacity-badge ${state.players.length>=(state.maxPlayers??100)?'is-full':''}">${state.players.length} / ${state.maxPlayers??100} người${state.players.length>=(state.maxPlayers??100)?' · Đã đủ chỗ':''}</span></div>${state.players.length?`<div class="live-player-list">${state.players.map((p,i)=>`<div class="live-player-chip"><span class="live-avatar tone-${i%4}">${escape(p.name.slice(0,2).toUpperCase())}</span>${escape(p.name)}${p.id===state.me?.id?'<small>Bạn</small>':''}</div>`).join('')}</div>`:'<div class="live-empty small">Chưa có người chơi.<br>Chia sẻ link để cả lớp vào phòng.</div>'}<div class="live-wait-note">${host?'Khi mọi người đã sẵn sàng, bấm Start Quiz.':'Giảng viên sẽ bắt đầu khi cả lớp sẵn sàng.'}</div></section></div>`;
    } else if(state.phase==='question'||state.phase==='reveal') {
      const reveal=state.phase==='reveal';
      body+=`<div class="live-question-meta"><span class="live-question-count">CÂU ${q.index+1} / ${state.questionCount}</span><span class="live-topic-tag">${escape(q.topic)}</span><span class="live-topic-tag peach">${escape(q.difficulty)}</span><span class="live-answer-count">${state.answerCount} / ${state.players.length} đã trả lời</span>${!reveal?'<div class="live-timer" role="timer" aria-label="Thời gian còn lại"><strong id="live-seconds">—</strong><span>giây</span></div>':'<span class="live-revealed">Đã chốt đáp án</span>'}</div><section class="live-question-card"><h2>${escape(q.text)}</h2>${!reveal?'<div class="live-time-track"><i id="live-time-fill"></i></div>':''}<div class="live-choices">${q.options.map((a,i)=>`<button type="button" class="live-choice choice-${i} ${reveal?(i===q.correct?'is-correct':state.myAnswer===i?'is-wrong':'is-muted'):state.myAnswer===i?'is-selected':state.myAnswer!==null&&!host?'is-unselected':''}" data-choice="${i}" aria-pressed="${state.myAnswer===i}" ${host||reveal||state.myAnswer!==null?'disabled':''}><span class="live-choice-letter">${'ABCD'[i]}</span><span>${escape(a)}</span>${reveal&&i===q.correct?'<b>✓ Đúng</b>':state.myAnswer===i?'<b class="live-selected-label"><span aria-hidden="true">✓</span> ĐÃ CHỌN</b>':''}</button>`).join('')}</div><p class="live-answer-status" aria-live="polite">${reveal?(host?'Đáp án đúng: '+ 'ABCD'[q.correct]:state.myAnswer===null?'Bạn đã bỏ lỡ câu này.':state.myAnswer===q.correct?'Chính xác! +1.000 điểm':'Chưa đúng. Cùng xem lại lời giải nhé.'):(host?'Câu hỏi đang mở trên thiết bị của người học.':state.myAnswer!==null?'Bạn đã chọn '+ 'ABCD'[state.myAnswer]+'. Đáp án đã được ghi nhận — chờ cả lớp hoàn thành…':'Chọn một đáp án. Bạn chỉ được chốt một lần.')}</p>${reveal?`<div class="live-explanation"><strong>Vì sao ${'ABCD'[q.correct]} là đáp án đúng?</strong><p>${escape(q.explanation)}</p><span>Nguồn: ${q.source.slide ? 'Trang ' + escape(q.source.slide) : 'Đoạn'} · ${escape(q.source.transcript)}</span></div>`:''}</section>`;
      if(reveal)body+=ranking(state.players);
    } else {
      const report=state.report;const correct=state.players.reduce((n,p)=>n+p.correct,0),total=report.scored*state.players.length;
      body+=`<section class="live-finish-banner"><div class="live-trophy">${icon('cup')}</div><div><span class="live-eyebrow">${state.phase==='closed'?'PHÒNG ĐÃ KẾT THÚC':'CHALLENGE COMPLETE'}</span><h2>${state.phase==='closed'?'Hẹn gặp ở thử thách tiếp theo!':'Cả lớp đã hoàn thành thử thách!'}</h2><p>Đã chốt ${report.scored} / ${state.questionCount} câu · Cùng nhìn lại những điều vừa học.</p></div></section><div class="live-stat-grid"><div><span>${host?'Người tham gia':'Điểm của bạn'}</span><strong>${host?state.players.length:state.me?.score.toLocaleString('vi-VN')}</strong></div><div><span>${host?'Tỉ lệ đúng cả lớp':'Số câu đúng'}</span><strong>${host?(total?Math.round(correct/total*100):0)+'%':state.me?.correct}</strong></div><div><span>${host?'Tổng câu trả lời đúng':'Sai / Bỏ lỡ'}</span><strong>${host?correct:state.me?.wrong+' / '+state.me?.skipped}</strong></div></div>`;
      body+=ranking(state.players,true)+topicReport(host?report.topics:state.me?.weakTopics||[],!host);
      if(host)body+=`<section class="live-class-report"><div class="live-section-heading"><h2>Kết quả tổng hợp của lớp</h2>${btn('download','Tải kết quả JSON','quiet')}</div><p class="live-small">Thống kê ${report.scored} câu đã chốt. Điểm không phụ thuộc tốc độ; câu bỏ lỡ nhận 0 điểm.</p>${report.breakdown.map(q=>`<details><summary>Câu ${q.index+1} · ${escape(q.topic)} — ${q.counts[q.correct]}/${q.total} trả lời đúng</summary><p>${escape(q.question)}</p><div class="live-distribution">${q.options.map((a,i)=>`<div><span>${'ABCD'[i]}${i===q.correct?' ✓':''}</span><p>${escape(a)}</p><b>${q.counts[i]} lượt</b></div>`).join('')}</div><p>Bỏ lỡ: ${q.skipped} · ${escape(q.difficulty)} · ${q.source.slide ? 'Trang ' + escape(q.source.slide) : 'Đoạn'} · ${escape(q.source.transcript)}</p></details>`).join('')}</section>`;
    }
    body+=hostButtons();
    frame(body,host?'LIVE QUIZ · KHÔNG GIAN GIẢNG VIÊN':'LIVE QUIZ · KHÔNG GIAN NGƯỜI HỌC');
    root.dataset.busy=String(busy);if(focusKey)root.querySelector('[data-live="'+focusKey+'"]')?.focus();updateClock();
  }
  function updateClock() {
    if(state?.phase!=='question')return;
    remaining=Math.max(0,Math.ceil((state.deadline-Date.now()-clockOffset)/1000));
    if($('#live-seconds'))$('#live-seconds').textContent=remaining;
    if($('#live-time-fill'))$('#live-time-fill').style.width=Math.max(0,Math.min(100,remaining/state.duration*100))+'%';
    $('#live-seconds')?.parentElement.classList.toggle('urgent',remaining<=5);
    if(remaining===0)root.querySelectorAll('[data-choice]').forEach(button=>button.disabled=true);
  }
  async function transact(fn) {
    if(busy)return;busy=true;root.dataset.busy='true';message('');
    try {await fn();} catch(e){message(e.message);} finally {busy=false;root.dataset.busy='false';}
  }
  root.addEventListener('submit',e=>{
    if(!['live-create-form','live-join-form'].includes(e.target.id))return;e.preventDefault();
    if(e.target.id==='live-create-form')transact(async()=>{const capacity=Number($('#live-capacity').value);if(!Number.isInteger(capacity)||capacity<1||capacity>100)throw new Error('Số người tham gia tối đa phải là số nguyên từ 1 đến 100.');const credentials=await api('',{title:'Quiz bài giảng',duration:Number($('#live-duration').value),maxPlayers:capacity,questions:snapshot},false);startSession(credentials);});
    else transact(async()=>{const pin=$('#live-pin').value.trim(),name=$('#live-name').value.trim();if(!/^[0-9]{6}$/.test(pin)||!name)throw new Error('Nhập PIN 6 chữ số và tên của bạn.');const saved=read(localStorage,'lessonleaf-player-'+pin);if(saved?.token){startSession(saved);return;}const credentials=await api('/'+pin+'/join',{name},false);startSession(credentials);});
  });
  root.addEventListener('click',e=>{
    const choice=e.target.closest('[data-choice]');
    if(choice&&!choice.disabled){const question=state.current;transact(async()=>accept(await api('/'+session.pin+'/answer',{choice:Number(choice.dataset.choice),index:question.index,round:state.round})));return;}
    const action=e.target.closest('[data-live]')?.dataset.live;if(!action||busy)return;
    if(action==='exit'){if(session&&state?.phase!=='closed'&&!confirm(state?.role==='host'?'Phòng vẫn tiếp tục. Bạn có thể mở Play Quiz để quay lại. Rời màn hình?':'Rời màn hình? Thời gian trả lời vẫn tiếp tục chạy.'))return;exit();return;}
    if(action==='new'){write(sessionStorage,'lessonleaf-host',null);session=null;exit();return;}
    if(action==='copy'){const input=$('#live-link');if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(input.value).then(()=>message('Đã sao chép link tham gia.')).catch(()=>{input.select();message('Chọn và sao chép link trong ô bên trên.');});else {input.select();message('Link đã được chọn. Nhấn Ctrl+C hoặc chạm giữ để sao chép.');}return;}
    if(action==='download'){const blob=new Blob([JSON.stringify(state.report,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='lessonleaf-'+state.pin+'-luot-'+state.round+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;}
    if(action==='restart'&&!confirm('Bắt đầu lượt mới với cùng người chơi và bộ câu hỏi? Điểm sẽ về 0. Hãy tải kết quả lượt hiện tại trước nếu cần.'))return;
    if(action==='close'&&!confirm('Kết thúc phòng cho tất cả người chơi? Không thể mở lại phòng đã kết thúc.'))return;
    if(action==='reveal'&&state.answerCount<state.players.length&&!confirm('Chốt câu sớm? Người chưa trả lời sẽ được ghi nhận là bỏ lỡ.'))return;
    transact(async()=>accept(await api('/'+session.pin+'/'+action,{seq:state.seq})));
  });
  if(playerPage){open();const pin=new URLSearchParams(location.search).get('room')||'';const saved=/^[0-9]{6}$/.test(pin)?read(localStorage,'lessonleaf-player-'+pin):null;if(saved?.token)startSession(saved);else joinScreen(pin);}
  else {
    $('#play-quiz')?.addEventListener('click',setup);
    resumeButton=document.createElement('button');resumeButton.className='outline';resumeButton.hidden=true;resumeButton.textContent='Mở phòng';resumeButton.addEventListener('click',setup);$('.result-actions')?.append(resumeButton);
    const saved=read(sessionStorage,'lessonleaf-host');if(saved?.pin&&saved?.token){setup();}
  }
})();
