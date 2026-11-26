'use strict';
const $ = id => document.getElementById(id);
const qsa = s => Array.from(document.querySelectorAll(s));
const fmt = n => n == null || n === '' || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString('ru-RU');
const num = (n, precision=2) => n == null || !Number.isFinite(+n) ? '—' : Number(n).toLocaleString('ru-RU',{maximumFractionDigits:precision});
const esc = x => String(x??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusNames = {running:'ОБУЧЕНИЕ ИДЁТ',completed:'ЗАВЕРШЕНО',stopped:'ОСТАНОВЛЕНО',failed:'ОШИБКА',unknown:'НЕИЗВЕСТНО'};
const resultNames = {'1-0':'Победа белых','0-1':'Победа чёрных','1/2-1/2':'Ничья','*':'Не завершена'};
const reasonNames = {checkmate:'Шах и мат',stalemate:'Пат',insufficient_material:'Недостаточно материала',threefold_repetition_claimed:'Троекратное повторение',fivefold_repetition:'Пятикратное повторение', '50_move_rule_claimed':'Правило 50 ходов','75_move_rule':'Правило 75 ходов',max_plies_unfinished:'Достигнут лимит полуходов',ongoing:'Продолжается'};
const application = {selected:null, screen:'overview', metric:'value', overview:null, replay:null, replayStep:0, inFlight:false, overlayOpen:false};
const api = async (url, opts) => {const res=await fetch(url,{cache:'no-store',...opts});let data={};try{data=await res.json()}catch(_){throw Error('Неверный ответ сервера')}if(!res.ok)throw Error(data.detail||data.message||('HTTP '+res.status));return data};
function toast(text){const el=$('toast');el.textContent=text;el.classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.add('hidden'),4800)}
const researchScreens = new Set(['analysis','evaluation','models','agents','system']);
function navigate(screen){if(!$('screen-'+screen))return;application.screen=screen;qsa('.screen').forEach(e=>e.classList.toggle('hidden',e.id!=='screen-'+screen));qsa('.nav-item').forEach(e=>{const active=e.dataset.screen===screen;e.classList.toggle('selected',active);if(active)e.setAttribute('aria-current','page');else e.removeAttribute('aria-current')});$('breadcrumb').textContent={overview:'Обзор обучения',games:'Партии и анализ',analysis:'Диагностика модели',runs:'Эксперименты',guide:'Методика',evaluation:'Evaluation',models:'Модели и checkpoint',agents:'Agent Lab',system:'Ресурсы и данные'}[screen];if(screen==='games')loadGames();if(screen==='runs')renderRuns();if(researchScreens.has(screen))loadAnalysis()}
function classResult(result){return result==='1-0'||result==='0-1'?'win':result==='1/2-1/2'?'draw':'pending'}
const graphState = new WeakMap();
const LA=globalThis.LabAnalytics;
let chartAnchor=null,chartRun=null,referenceSnapshot=null,referenceRequest=0,reportRun=null,reportList=[],profileRows=[];
let chartExport=[];
function graph(container, values, {accent='#fff',height=245,unit='',ymin=null,iterations=null,overlay=[],overlayName='',smoothPeriod=0}={}){
 const rows=LA.rows(values,iterations), rolling=smoothPeriod?LA.smooth(rows,smoothPeriod):[];
 const ref=overlay.length?LA.aligned(rows,overlay):[];
 const series=[{rows,stroke:accent,label:'Исходные',dash:''}];
 if(rolling.length)series.push({rows:rolling,stroke:'#86d5a2',label:'Среднее '+smoothPeriod,dash:'6 3'});
 if(ref.length)series.push({rows:ref,stroke:'#a7c9ee',label:overlayName||'Сравнение',dash:'2 4'});
 const w=Math.max(240,container.clientWidth||780),h=Math.max(100,container.clientHeight||height);
 const signature=JSON.stringify([series,w,h,ymin,unit]);
 if(graphState.get(container)?.signature===signature)return;
 const previous=graphState.get(container);
 const state={signature,values,options:{accent,height,unit,ymin,iterations,overlay,overlayName,smoothPeriod},cursor:previous?.cursor};
 graphState.set(container,state);
 const bounds=LA.extent(series.map(s=>s.rows),ymin);
 if(!bounds||!rows.length){container.innerHTML='<div class="empty-chart">Нет измерений в выбранном диапазоне.</div>';container.removeAttribute('tabindex');container.removeAttribute('aria-label');container.onfocus=container.onblur=container.onkeydown=null;return}
 const l=w<400?52:67,r=15,t=22,b=30,lo=bounds.lo,hi=bounds.hi;
 const xmin=rows[0].x,xmax=rows.at(-1).x;
 const fx=x=>l+(w-l-r)*(xmax===xmin?.5:(x-xmin)/(xmax-xmin));
 const fy=y=>t+(h-t-b)*(1-(y-lo)/(hi-lo));
 let axes='';
 for(let i=0;i<=4;i++){const y=t+(h-t-b)*i/4,v=hi-(hi-lo)*i/4;axes+='<line x1="'+l+'" y1="'+y+'" x2="'+(w-r)+'" y2="'+y+'" stroke="#292929" stroke-dasharray="3 5"/><text x="'+(l-8)+'" y="'+(y+4)+'" text-anchor="end" fill="#b3b3b3" font-size="11">'+esc(num(v,5))+'</text>'}
 const paths=series.map(s=>{let path='',last=null;for(const row of s.rows){if(row.y===null){last=null;continue}path+=(last!==null&&row.x===last+1?' L ':' M ')+fx(row.x)+' '+fy(row.y);last=row.x}
 const points=s.rows.filter((r,i)=>r.y!==null&&(s.rows.length<=25||((i===0||s.rows[i-1].y===null||s.rows[i-1].x!==r.x-1)&&(i===s.rows.length-1||s.rows[i+1].y===null||s.rows[i+1].x!==r.x+1)))).map(row=>'<circle cx="'+fx(row.x)+'" cy="'+fy(row.y)+'" r="2.5" fill="'+s.stroke+'"/>').join('');
 return '<path d="'+path+'" fill="none" stroke="'+s.stroke+'" stroke-width="1.6" stroke-dasharray="'+s.dash+'" vector-effect="non-scaling-stroke"/>'+points}).join('');
 let xLabels='';const ticks=Math.min(w<400?3:5,rows.length);for(let i=0;i<ticks;i++){const x=rows[Math.round(i*(rows.length-1)/Math.max(1,ticks-1))].x;xLabels+='<text x="'+fx(x)+'" y="'+(h-8)+'" text-anchor="middle" fill="#b3b3b3" font-size="11">'+esc(x)+'</text>'}
 container.innerHTML='<div class="chart-readout hidden"></div><svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="Метрика по итерациям"><title>Пропуски не интерполируются. Горизонтальная ось: итерация.</title>'+axes+paths+xLabels+'<line class="crosshair" visibility="hidden" y1="'+t+'" y2="'+(h-b)+'" stroke="#aaa" stroke-dasharray="3 3"/></svg>';
 container.tabIndex=0;container.setAttribute('aria-label','График: стрелки влево и вправо для просмотра измерений');
 const svg=container.querySelector('svg'),readout=container.querySelector('.chart-readout'),cross=container.querySelector('.crosshair');
 let index=Math.max(0,rows.findIndex(r=>r.x===state.cursor));if(state.cursor==null)index=rows.length-1;
 function show(i){index=Math.max(0,Math.min(rows.length-1,i));const row=rows[index];state.cursor=row.x;readout.textContent='Итерация '+row.x+' · '+series.map(s=>s.label+': '+num(s.rows[index]?.y,6)+(unit?' '+unit:'')).join(' · ');readout.classList.remove('hidden');cross.setAttribute('x1',fx(row.x));cross.setAttribute('x2',fx(row.x));cross.setAttribute('visibility','visible')}
 function hide(){readout.classList.add('hidden');cross.setAttribute('visibility','hidden')}
 svg.onpointermove=e=>{const rect=svg.getBoundingClientRect(),x=(e.clientX-rect.left)*w/rect.width;let closest=0;for(let i=1;i<rows.length;i++)if(Math.abs(fx(rows[i].x)-x)<Math.abs(fx(rows[closest].x)-x))closest=i;show(closest)};
 svg.onpointerleave=()=>{if(document.activeElement!==container)hide()};container.onfocus=()=>show(index);container.onblur=hide;container.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();show(index+(e.key==='ArrowRight'?1:-1))}};
 if(document.activeElement===container)show(index);
}
function updateReferenceOptions(d){
 const el=$('chart-reference'),old=el.value,opts='<option value="">Без сравнения</option>'+d.runs.filter(r=>r.id!==d.selected).map(r=>'<option value="'+esc(r.id)+'">'+esc(r.name||r.id)+'</option>').join('');
 if(el.dataset.options!==opts){el.innerHTML=opts;el.dataset.options=opts;el.value=old===d.selected?'':old}
 if(referenceSnapshot&&(!el.value||referenceSnapshot.id!==el.value)){referenceSnapshot=null;referenceRequest++;$('chart-reference-note').textContent='Снимок по запросу, без автообновления.'}
 $('chart-reference-load').disabled=!el.value;
}
const metricKeys={value:'value_mse',policy:'policy_loss',entropy:'entropy'};
function renderMainChart(d){
 const m=d.metrics||[],key=metricKeys[application.metric];
 if(chartRun!==d.selected){chartRun=d.selected;chartAnchor=null;referenceSnapshot=null;referenceRequest++;$('chart-reference-note').textContent='Снимок по запросу, без автообновления.'}
 updateReferenceOptions(d);
 const all=LA.rows(m.map(r=>r.train?.[key]),m.map(r=>r.iteration));
 const size=$('chart-range').value==='all'?all.length:Number($('chart-range').value);
 const pan=$('chart-pan'),max=Math.max(0,all.length-1);
 if(chartAnchor!==null&&all.length&&chartAnchor<all[0].x){chartAnchor=all[0].x}
 const end=chartAnchor===null?all.length:Math.max(1,all.findLastIndex(r=>r.x<=chartAnchor)+1);
 pan.max=String(max);pan.value=String(Math.max(0,end-1));pan.disabled=!all.length||size>=all.length;
 const window=LA.windowRows(all,size,pan.disabled?null:chartAnchor);
 const rolling=$('chart-smooth').checked?LA.smooth(window,10):[];
 const overlay=referenceSnapshot?LA.rows(referenceSnapshot.metrics.map(r=>r.train?.[key]),referenceSnapshot.metrics.map(r=>r.iteration)):[];
 const aligned=LA.aligned(window,overlay);
 graph($('main-chart'),window.map(r=>r.y),{iterations:window.map(r=>r.x),smoothPeriod:$('chart-smooth').checked?10:0,overlay,overlayName:'Снимок'});
 chartExport=window.map((r,i)=>({...r,smooth:rolling[i]?.y,reference:aligned[i]?.y}));
 $('chart-download').disabled=!window.length;
 $('chart-window').textContent=window.length?'#'+window[0].x+'–'+window.at(-1).x+' · '+window.length+' / '+all.length+' записей':'Нет истории';
 $('chart-series-note').textContent=[$('chart-smooth').checked?'— — Среднее 10':'',referenceSnapshot?'··· Снимок другого запуска':''].filter(Boolean).join('  ');
}
async function fetchReference(){
 const id=$('chart-reference').value,run=application.selected,token=++referenceRequest;
 if(!id||id===run)return;
 referenceSnapshot=null;$('chart-reference-note').textContent='Загрузка снимка…';$('chart-reference-load').disabled=true;
 try{const d=await api('/api/overview?run='+encodeURIComponent(id));if(token!==referenceRequest||run!==application.selected||$('chart-reference').value!==id)return;
 if(d.selected!==id)throw Error('Другой эксперимент в ответе');
 referenceSnapshot={id,metrics:d.metrics||[]};$('chart-reference-note').textContent='Снимок '+new Date().toLocaleTimeString('ru-RU')+' · совпадающие номера итераций; условия могут различаться.'+(d.file_warnings?.length?' Файлы временно недоступны, возможен кэш.':'');
 if(application.overview)renderMainChart(application.overview);
 }catch(e){if(token===referenceRequest)$('chart-reference-note').textContent='Не удалось загрузить: '+e.message}
 finally{if(token===referenceRequest)$('chart-reference-load').disabled=!$('chart-reference').value}
}
function renderPerformance(rows){profileRows=rows.slice(-600);const key=$('performance-metric').value;graph($('performance-chart'),profileRows.map(r=>r.performance?.[key]),{iterations:profileRows.map(r=>r.iteration),ymin:0,unit:'с'});graph($('batch-chart'),profileRows.map(r=>r.performance?.average_inference_batch),{iterations:profileRows.map(r=>r.iteration),ymin:0,unit:'поз.'})}
function renderEvaluationDetail(){
 const report=reportList.find(r=>r.filename===$('evaluation-select').value),el=$('evaluation-detail');
 if(!report){el.textContent='Нет сохранённого отчёта.';return}
 const v=report.statistics||{},o=LA.outcome(v);
 const props=[['Candidate',report.candidate],['Reference',report.reference],['Набор',report.suite],['Seed',report.seed],['Дебютных полуходов',report.opening_plies],['Лимит полуходов',report.max_plies],['Запрошено партий',report.games_requested],['Завершённых пар',v.completed_pairs],['Уникальных стартов',v.unique_opening_positions],['Уникальных партий',v.unique_sequences],['Score полных пар',v.paired_score==null?'—':num(100*v.paired_score,1)+'%']];
 const bar=o&&o.total?'<div class="eval-result-bar" aria-hidden="true">'+o.parts.map((x,i)=>'<span class="outcome-'+i+'" style="width:'+x+'%"></span>').join('')+'</div>':'';
 el.innerHTML='<div class="eval-score"><small>Score завершённых партий</small><strong>'+(o?.score!=null?num(o.score*100,1)+'%':'—')+'</strong><span>n = '+fmt(o?.n)+'</span></div>'+bar+(o?'<div class="eval-result-labels"><span>В '+fmt(o.w)+'</span><span>Н '+fmt(o.d)+'</span><span>П '+fmt(o.l)+'</span><span>Не завершено '+fmt(o.u)+'</span></div>':'<p class="analysis-help">Исходы неполные или отсутствуют.</p>')+'<dl class="property-list">'+props.map(([k,val])=>'<div><dt>'+esc(k)+'</dt><dd>'+esc(val??'—')+'</dd></div>').join('')+'</dl><p class="analysis-help">Парные и детерминированные партии могут быть зависимы. Калиброванный интервал и Elo не рассчитаны. Имена файлов не доказывают идентичность весов.</p>';
}
function updateEvaluationReports(list,run){
 if(reportRun!==run){reportRun=run;reportList=[];$('evaluation-select').dataset.options=''}
 reportList=list;const el=$('evaluation-select'),old=el.value,options=list.length?list.map(r=>'<option value="'+esc(r.filename)+'">'+esc(r.created_at||r.filename)+' · '+esc(r.suite||'legacy')+'</option>').join(''):'<option value="">Нет отчётов</option>';
 if(el.dataset.options!==options){el.innerHTML=options;el.dataset.options=options;if(list.some(r=>r.filename===old))el.value=old}
 renderEvaluationDetail();
}
function renderOverview(d){
  application.overview=d;
  const picker=$('run-picker');
  const old=picker.value;
  const options=d.runs.length ? d.runs.map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('') : '<option value="">Нет запусков</option>';
  if(picker.dataset.options!==options){picker.innerHTML=options;picker.dataset.options=options;}
  application.selected=d.selected||null; if(picker.value!==(d.selected||''))picker.value=d.selected||'';$('global-run').textContent=d.selected||'Эксперимент не выбран';$('global-run').title=d.selected||'Эксперимент не выбран';
  const st=d.state||{},c=st.counters||{},meta=d.metadata||{},cfg=meta.config||{};
  const state=st.status||'unknown';
  $('overview-device').textContent=st.device||'—';$('overview-iteration').textContent=fmt(st.iteration);$('overview-best').textContent=d.best?.best_iteration!=null?'#'+d.best.best_iteration:(d.best?.origin||'—');$('overview-process').textContent=d.process?.active?(d.process.run||'Запущен'):'Нет активного';$('open-config').disabled=!!d.process?.active;$('runs-new').disabled=!!d.process?.active;
  const isRunning=d.process?.active && d.process.run===d.selected;
  const interrupted=state==='running' && !isRunning;
  $('run-title').textContent=d.selected ? d.selected : 'Обучение ещё не запускалось';
  $('run-detail').textContent=d.selected ? `Итерация ${st.iteration||0} · ${st.phase||'ожидание'} · ${st.device||'неизвестно'} · ${fmt(meta.parameters)} параметров` : 'Создайте первый эксперимент, чтобы увидеть реальные показатели.';
  $('status-badge').textContent=d.selected ? (interrupted?'ПРЕРВАНО':statusNames[state]||state) : 'НЕ ЗАПУЩЕНО';$('status-badge').className='status-badge '+(d.selected?(interrupted?'interrupted':state):'');
  $('banner-symbol').textContent=state==='completed'?'✓':state==='failed'?'!':isRunning?'◈':'◎';
  $('stop-btn').classList.toggle('hidden',!isRunning);
  $('resume-btn').classList.toggle('hidden',!d.selected || d.process?.active || !['stopped','completed','failed','running'].includes(state));
  const accessWarnings=d.file_warnings||[];
  $('sync-label').textContent = accessWarnings.length
    ? `⚠ Файлы временно недоступны (${accessWarnings.length}); использованы последние данные`
    : (isRunning ? 'Live · обновление 2,5 сек.' : 'Локальные данные');
  $('sync-label').title = accessWarnings.map(w=>`${w.file}: ${w.message}`).join('\n');
  const m=d.metrics||[];
  const completed=m.length?m[m.length-1].iteration:null;
  const target=st.target_iteration??cfg.iterations??null;
  const pct=target>0&&completed!=null?Math.max(0,Math.min(100,completed/target*100)):null;
  $('progress-fill').style.width=(pct??0)+'%';const progress=$('progress-fill').parentElement;if(pct==null)progress.removeAttribute('aria-valuenow');else progress.setAttribute('aria-valuenow',String(Math.round(pct)));$('progress-text').textContent=`${fmt(completed)} / ${fmt(target)} итераций`;$('progress-pct').textContent=pct==null?'—':num(pct,0)+'%';
  $('phase-label').textContent=isRunning?`Текущая фаза: ${ {selfplay:'самоигра',optimization:'обновление сети',arena:'проверочные матчи',ready:'завершение итерации'}[st.phase]||st.phase||'запуск'} · партий в итерации ${st.iteration_games||0} / ${st.iteration_target||cfg.games_per_iteration||0}` : 'Итерации сохраняются с checkpoint после каждого завершённого обновления';
  $('m-games').textContent=fmt(c.games);$('m-finished').textContent=fmt(c.finished);$('m-plies').textContent=fmt(c.plies);$('m-samples').textContent=fmt(c.samples);
  $('m-games-extra').textContent=`${fmt(c.unfinished)} достигли лимита / не завершены`;
  $('m-finished-extra').textContent=c.games ? `${num(100*(c.finished||0)/c.games,1)}% всех партий` : 'Мат, пат, ничья по правилам';
  $('m-plies-extra').textContent=c.games ? `${num((c.plies||0)/c.games,1)} в среднем / партия` : 'Полуход — одно действие игрока';
  $('m-samples-extra').textContent='Использованы для обучения PPO';
  $('result-count').textContent=fmt(c.games)+' партий';$('donut-total').innerHTML=fmt(c.finished)+'<small>завершено</small>';
  const count=c.games||0;
  let a=0;const colors=[['white_wins','#e7e7e7'],['black_wins','#737373'],['draws','#a7c9ee'],['unfinished','#484848']];
  let segments=colors.map(([name,color])=>{const next=a+(count?100*(c[name]||0)/count:0);let v=`${color} ${a}% ${next}%`;a=next;return v});
  $('result-donut').style.background=count?`conic-gradient(${segments.join(',')})`:'var(--line)';
  $('r-white').textContent=fmt(c.white_wins);$('r-black').textContent=fmt(c.black_wins);$('r-draw').textContent=fmt(c.draws);$('r-unfinished').textContent=fmt(c.unfinished);
  const metricName={value:'Value MSE',policy:'Policy loss',entropy:'Entropy'};
  renderMainChart(d);
  $('graph-name').textContent=metricName[application.metric];
  $('graph-note').textContent=application.metric==='value'?'MSE на исходах самоигры, не рейтинг силы':application.metric==='policy'?'Знак и значение PPO loss зависят от преимуществ':'Энтропия политики в текущих позициях';
  graph($('speed-chart'),m.map(x=>x.plies_per_s),{accent:'#fff',height:130,ymin:0,iterations:m.map(x=>x.iteration)});
  const last=m.at(-1);
  $('s-gps').textContent=num(last?.games_per_s,3);$('s-pps').textContent=num(last?.plies_per_s,1);
  const arenaRuns=m.filter(x=>x.arena?.completed>0);
  let aw=0,al=0,ad=0,ap=0;
  for(const row of m){aw+=row.arena?.wins||0;al+=row.arena?.losses||0;ad+=row.arena?.draws||0;ap+=row.arena?.played||0}
  const ac=aw+al+ad;
  $('arena-score').textContent=ac?num(100*(aw+.5*ad)/ac,1)+'%':'—';
  $('arena-hint').textContent=ac?`Счёт по завершённым партиям, n = ${fmt(ac)}`:'Нет завершённых проверочных партий';
  $('arena-wld').textContent=m.length?`В: ${fmt(aw)} · Н: ${fmt(ad)} · П: ${fmt(al)}`:'В: — · Н: — · П: —';
  $('arena-size').textContent=m.length?`${fmt(ap)} проведено · ${fmt(ap-ac)} не окончено`:'Нет данных';
  $('arena-caption').textContent='vs. frozen v0.2';
  $('recent-games').innerHTML=d.games.length?d.games.slice(0,6).map(g=>`<tr><td>#${g.game_id} <small> / ${g.iteration}</small></td><td><span class="result-pill ${classResult(g.result)}">${esc(resultNames[g.result]||g.result)}</span></td><td>${esc(reasonNames[g.reason]||g.reason)}</td><td>${fmt(g.plies)}</td><td><button class="table-button view-game" data-id="${g.game_id}" data-kind="selfplay">Просмотр →</button></td></tr>`).join(''):'<tr><td colspan="5" class="table-empty">Партии пока отсутствуют</td></tr>';
  if(application.screen==='runs')renderRuns();
  const sync=$('sync-label').parentElement;sync.classList.toggle('stale',accessWarnings.length>0);sync.classList.remove('disconnected','pending');
}
function renderRuns(){const d=application.overview;if(!d)return;
  $('run-list').innerHTML=d.runs.length?d.runs.map(r=>`<article class="run-card ${r.id===d.selected?'current':''}" data-run="${esc(r.id)}"><span class="status-badge ${esc(r.status)}">${esc(statusNames[r.status]||r.status)}</span><h2>${esc(r.name)}</h2><p>${esc(r.created_at?.replace('T',' ').replace('+00:00',' UTC')||'Дата неизвестна')}</p><div class="run-totals"><span><b>${fmt(r.iteration)}</b> итераций</span><span><b>${fmt(r.games)}</b> партий</span></div></article>`).join(''):'<div class="panel empty-panel">Пока нет экспериментов. Нажмите «Создать запуск».</div>';
  renderLog(d);
}

let analysisBusy=false;
async function loadAnalysis(){if(analysisBusy)return;
  if(!application.selected){for(const id of ['analysis-warnings','quality-status','best-status','gpu-info','storage-status','performance-status','evaluation-history','tournament-ranking','agent-results','agent-training-health','color-audit-info','hardware-benchmark-info'])$(id).textContent='Выберите или создайте эксперимент.';for(const id of ['a-finished','a-samples','a-score','a-checkpoint'])$(id).textContent='—';for(const id of ['completion-chart','analysis-value-chart','kl-chart','clip-chart'])graph($(id),[]);renderPerformance([]);updateEvaluationReports([],null);$('eval-live').textContent='Нет выбранного эксперимента';return}
  const run=application.selected;analysisBusy=true;
  try{
    const data=await api('/api/analysis?run='+encodeURIComponent(run));
    if(application.selected!==run)return;
    await loadAgentLab(run);if(application.selected!==run)return;
    try {
      const storage=await api('/api/storage/'+encodeURIComponent(run));
      if(application.selected!==run)return;const sp=storage.space||{};
      const mb=x=>num((x||0)/1048576,1)+' МБ';
      $('storage-status').innerHTML=`<div class="diagnostic-item"><strong>На диске: ${mb(sp.total_bytes)}</strong><p>Несжатые журналы: ${mb(sp.journals_bytes)} · Сжатые архивы: ${mb(sp.archives_bytes)} · Checkpoint: ${mb(sp.checkpoint_bytes)} · Прочее: ${mb(sp.other_bytes)}</p></div>`;
    } catch(error) { $('storage-status').textContent='Место на диске: '+error.message; }
    const perf=(data.series||[]).filter(m=>m.performance?.mode).at(-1)?.performance;
    $('performance-status').innerHTML=perf?`<div class="diagnostic-item"><strong>Непрерывные партии · ${fmt(perf.concurrent_games)} слотов · ${fmt(perf.bridge_workers)} C++ workers</strong><p>Открытия: ${num(perf.opening_s,2)} с · ходы C++: ${num(perf.bridge_steps_s,2)} с · инференс: ${num(perf.neural_inference_s,2)} с · PPO: ${num(perf.ppo_s,2)} с · средний GPU-пакет: ${num(perf.average_inference_batch,1)} позиций</p></div>`:'<div class="diagnostic-item"><strong>Профиль пока не записан</strong><p>Появится после итерации на v0.7.0.</p></div>';
    if(application.selected!==run)return;
    const t=data.totals||{}, a=data.arena||{}, c=data.checkpoint||{};
    $('a-finished').textContent=fmt(t.finished);
    $('a-finished-note').textContent=`${num(data.completion_rate==null?null:100*data.completion_rate,1)}% завершённых · ${fmt(t.unfinished)} незавершённых`;
    $('a-samples').textContent=fmt(t.samples);
    $('a-score').textContent=a.score==null?'—':num(100*a.score,1)+'%';
    $('a-score-note').textContent=a.completed?`Описательный счёт, n=${fmt(a.completed)}. Старые матчи повторяли одни и те же партии.`:'Нет завершённых матчей';
    $('a-checkpoint').textContent=c.exists?'Найден':'Нет';
    $('a-checkpoint-note').textContent=c.exists?`${num((c.size_bytes||0)/1024,0)} КБ · сохранён в runs/`:'Продолжение недоступно';
    const history=(data.series||[]).slice(-600),iterations=history.map(x=>x.iteration);
    graph($('completion-chart'),history.map(x=>x.finish_rate),{accent:'#fff',ymin:0,unit:'%',iterations});
    graph($('analysis-value-chart'),history.map(x=>x.value_mse),{accent:'#fff',ymin:0,iterations});
    graph($('kl-chart'),history.map(x=>x.approx_kl),{iterations});graph($('clip-chart'),history.map(x=>x.clip_fraction),{iterations,ymin:0});renderPerformance(history);
    $('analysis-window-note').textContent='Графики: '+history.length+' из '+(data.series||[]).length+' записей в ответе; серверная сводка ограничена 100 000 строками.';
    $('analysis-warnings').innerHTML=data.warnings?.length?data.warnings.map(w=>`<div class="diagnostic-item"><strong>${w.level==='warning'?'Внимание':'Замечание'}</strong><p>${esc(w.text)}</p></div>`).join(''):'<div class="diagnostic-item"><strong>Данных пока недостаточно</strong><p>Начните обучение, чтобы увидеть рекомендации.</p></div>';
    const evals=data.evaluations||[];updateEvaluationReports(evals,run);
    $('evaluation-history').innerHTML=evals.length?evals.map(x=>{const v=x.statistics||{};return `<div class="diagnostic-item"><strong>${esc(x.created_at||x.filename)} · ${v.score==null?'—':num(100*v.score,1)+'%'} score</strong><p>${fmt(v.wins)} побед · ${fmt(v.draws)} ничьих · ${fmt(v.losses)} поражений · ${fmt(v.unfinished)} незавершённых · ${fmt(v.completed)} учтённых · ${fmt(v.unique_sequences??'?')} уникальных партий · ${fmt(v.unique_opening_positions??'?')} стартовых позиций · набор: ${esc(x.suite||'legacy')} · ${esc(x.candidate||'—')} vs ${esc(x.reference||'—')}${v.unique_sequences===2 && v.completed>=20?' · ⚠ Повторяющиеся матчи':''}</p></div>`}).join(''):'<div class="diagnostic-item"><strong>Нет дополнительных проверок</strong><p>Запустите scripts/EVALUATE_RUN_WINDOWS.bat для независимой серии матчей. Существующие контрольные матчи показаны в разделе «Обзор».</p></div>';
    const tour=data.tournaments||[];
    $('tournament-ranking').innerHTML=tour.length?tour.slice(0,2).map(t=>
      `<div class="diagnostic-item"><strong>${esc(t.filename)} · checkpoint ranking</strong><p>${(t.ranking||[]).slice(0,8).map(x=>`#${x.iteration}: ${x.score==null?'—':num(x.score*100,1)+'%'} (${x.unique_sequences} партий)`).join(' · ')}</p></div>`).join(''):'<div class="diagnostic-item"><strong>Исторических турниров ещё нет</strong><p>Нажмите «Сравнить 8 checkpoint» — тест не меняет веса.</p></div>';
    const quality=data.quality||{}, reason=quality.termination_reasons||{};
    const reasonText=Object.entries(reason).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([k,n])=>`${esc(reasonNames[k]||k)}: ${fmt(n)}`).join(' · ');
    $('quality-status').innerHTML=quality.reason_iterations?`<div class="diagnostic-item"><strong>Причины завершения · ${fmt(quality.reason_iterations)} итераций v0.6</strong><p>${reasonText||'Нет исходов'} · повторения: ${quality.repetition_fraction==null?'—':num(quality.repetition_fraction*100,1)+'%'} · повторные визиты: ${fmt(quality.position_revisits)}</p></div><div class="diagnostic-item"><strong>Ограничение PPO</strong><p>Последний approx KL: ${num(quality.last_approx_kl,5)} · clip fraction: ${num(quality.last_clip_fraction,4)} · градиент: ${num(quality.last_grad_norm,3)} · остановок по KL: ${fmt(quality.kl_early_stops)}</p></div>`:'<div class="diagnostic-item"><strong>Исторический запуск</strong><p>Для этих итераций v0.5 ещё не записывала причины ничьих и KL. При продолжении эксперимента v0.6 добавит новые метрики без пересчёта старых.</p></div>';
    const audit=data.color_audit||{};
    $('color-audit-info').textContent=audit.positions?`Аудит симметрии: ${fmt(audit.positions)} позиций · среднее |Δ value| ${num(audit.mean_abs_value_difference,4)} · это не доказательство ошибки.`:'Аудит симметрии: запусти scripts/AUDIT_COLOR_WINDOWS.bat после обучения. Веса не меняются.';
    const bench=data.hardware_benchmark||{};
    const bcpu=bench.device_results?.cpu?.['32']; const bgpu=bench.device_results?.cuda?.['32'];
    $('hardware-benchmark-info').textContent=bcpu?`Бенчмарк батча 32: CPU forward ${num(bcpu.forward_ms,3)} мс${bgpu?' · CUDA '+num(bgpu.forward_ms,3)+' мс':''} · Core ${fmt(bench.core?.steps_per_second)} шагов/с · тест синтетический, не Games/sec.`:'Запусти scripts/BENCHMARK_HARDWARE_WINDOWS.bat для CPU/CUDA и шахматного ядра.';
    const best=data.best||{}, hw=data.device_diagnostics||{};
    $('best-status').innerHTML=best.at||best.origin?`<div class="diagnostic-item"><strong>${esc(best.origin||best.opponent||'best.pt')} · ${esc(best.status||(best.decision?.promote===true?'promoted':'screening'))}</strong><p>Проверка: ${esc(best.at||best.updated_at||'не выполнялась')} · лучшая итерация: ${fmt(best.best_iteration??0)} · порог: ${esc(best.decision?.threshold??'—')} · ${esc(best.note||best.decision?.note||'')}</p></div>`:'<div class="diagnostic-item"><strong>Best checkpoint ещё не инициализирован</strong><p>Он будет создан при следующем запуске или продолжении обучения, исходный latest.pt не меняется.</p></div>';
    $('gpu-info').textContent=hw.selected?`Вычисления: ${hw.selected} · PyTorch ${hw.torch_version} · CUDA доступна: ${hw.cuda_available?'да':'нет'} ${hw.cuda_device||''}`:'Данные устройства ещё не записаны. Если установлена CPU-сборка PyTorch, обучение работает на CPU.';
    const ev=data.evaluation_process||{};
    $('eval-live').textContent=ev.active?`Работает: ${ev.output||''}`:'Проверка не выполняется';
  }catch(error){toast('Диагностика: '+error.message)}finally{analysisBusy=false}
}

let gamesBusy=false;
async function loadGames(){if(!application.selected){$('games-list').innerHTML='<tr><td colspan="6" class="table-empty">Нет выбранного эксперимента</td></tr>';$('games-count').textContent='—';return}if(gamesBusy)return;gamesBusy=true;const run=application.selected;
  const kind=$('game-kind').value,result=$('game-result').value;
  try{const data=await api('/api/games?'+new URLSearchParams({run,kind,result,limit:'50'}));if(application.selected!==run||$('game-kind').value!==kind||$('game-result').value!==result)return;$('games-count').textContent=`${data.games.length} последних записей`;
  $('games-list').innerHTML=data.games.length?data.games.map(g=>`<tr><td>#${g.game_id}</td><td>${g.iteration}</td><td><span class="result-pill ${classResult(g.result)}">${esc(resultNames[g.result]||g.result)}</span></td><td>${esc(reasonNames[g.reason]||g.reason)}</td><td>${fmt(g.plies)}</td><td><button class="table-button view-game" data-id="${g.game_id}" data-kind="${kind}">Открыть →</button></td></tr>`).join(''):'<tr><td colspan="6" class="table-empty">Записей с таким результатом пока нет</td></tr>';}
  catch(e){toast(e.message)}finally{gamesBusy=false}
}
async function refresh(){if(application.inFlight)return;application.inFlight=true;try{
  const requestedRun=application.selected;const runParam=application.selected?'?run='+encodeURIComponent(application.selected):'';
  const [d,h]=await Promise.all([api('/api/overview'+runParam),api('/api/health')]);
  if(application.selected!==requestedRun)return;
  $('engine-led').className='led '+(h.engine_ready?'ok':'bad');$('engine-text').textContent=h.engine_ready?'Chess Core доступен':'C++ ядро не собрано';
  // If a run was deleted externally, recover to most recent.
  if(!d.selected && application.selected) application.selected=null;
  renderOverview(d);$('stop-btn').disabled=false;$('resume-btn').disabled=false;const updated=new Date().toLocaleTimeString('ru-RU');$('sync-label').title+='\nОбновлено: '+updated;$('footer-sync').textContent=(d.file_warnings?.length?'Кэш · ':'Локальные данные · ')+'обновлено '+updated;
}catch(e){$('sync-label').textContent='Нет связи · данные устарели';$('sync-label').parentElement.classList.add('disconnected');$('sync-label').parentElement.classList.remove('pending');$('footer-sync').textContent='Нет связи · показаны последние доступные данные';$('open-config').disabled=true;$('runs-new').disabled=true;$('stop-btn').disabled=true;$('resume-btn').disabled=true;}finally{application.inFlight=false}}
function configModal(open){application.overlayOpen=open;$('config-overlay').classList.toggle('hidden',!open);$('config-overlay').setAttribute('aria-hidden',String(!open));if(open)$('c-iterations').focus()}
const presets={quick:{iterations:2,games:2,parallel:2,plies:140,temp:1.1,arena:0,opening:0},balanced:{iterations:10,games:8,parallel:4,plies:240,temp:1.1,arena:2,opening:6},long:{iterations:100,games:16,parallel:8,plies:300,temp:1.1,arena:4,opening:6}};
function applyPreset(name){const p=presets[name];if(!p)return;qsa('[data-preset]').forEach(b=>b.classList.toggle('chosen',b.dataset.preset===name));for(const k of Object.keys(p))$('c-'+k).value=p[k]}
async function startTraining(){const payload={iterations:+$('c-iterations').value,games_per_iteration:+$('c-games').value,parallel:+$('c-parallel').value,max_plies:+$('c-plies').value,temperature:+$('c-temp').value,arena_games:+$('c-arena').value,opening_plies:+$('c-opening').value,league_fraction:+$('c-league').value/100, repetition_penalty:+$('c-repeat').value, target_kl:+$('c-kl').value,bridge_workers:+$('c-workers').value,batch_size:+$('c-batch').value,archive_every:+$('c-archive').value};
  const btn=$('start-training');if(btn.disabled||application.overview?.process?.active)return;const invalid=qsa('#config-overlay input').find(el=>!el.checkValidity());if(invalid){invalid.closest('details')?.setAttribute('open','');invalid.reportValidity();return}btn.disabled=true;$('config-error').textContent='';try{const d=await api('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});application.selected=d.run;configModal(false);navigate('overview');await refresh();toast('Эксперимент запущен: '+d.run)}catch(e){$('config-error').textContent=e.message}finally{btn.disabled=false}}
async function stopTraining(){if(!application.overview?.process?.active||$('stop-btn').disabled)return;if(!await askConfirm('Остановить обучение после окончания текущей итерации? Результаты сохранятся.'))return;if(!application.overview?.process?.active||application.overview.process.run!==application.selected)return;$('stop-btn').disabled=true;try{await api('/api/stop',{method:'POST'});toast('Запрос остановки принят. Текущая итерация завершится.')}catch(e){toast(e.message)}finally{$('stop-btn').disabled=false}}
let resumeRun=null;
function resumeTraining(){
  if(!application.selected||application.overview?.process?.active||$('resume-btn').disabled)return;
  resumeRun=application.selected;
  const cfg=application.overview?.metadata?.config||{};
  $('resume-context').textContent='Эксперимент: '+resumeRun;
  $('resume-iterations').value=10;$('resume-plies').value=cfg.max_plies??240;
  $('resume-openings').value=cfg.opening_plies??0;$('resume-parallel').value=cfg.parallel??8;
  $('resume-workers').value=cfg.bridge_workers??2;$('resume-error').textContent='';
  $('resume-dialog').showModal();
}
async function submitResume(e){
  e.preventDefault();const btn=$('resume-submit');if(btn.disabled||!resumeRun)return;
  if(resumeRun!==application.selected||application.overview?.process?.active){$('resume-error').textContent='Состояние изменилось. Закройте окно и обновите эксперимент.';return}
  const payload={iterations:+$('resume-iterations').value,max_plies:+$('resume-plies').value,opening_plies:+$('resume-openings').value,parallel:+$('resume-parallel').value,bridge_workers:+$('resume-workers').value,archive_every:5};
  btn.disabled=true;
  try{await api('/api/resume/'+encodeURIComponent(resumeRun),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});$('resume-dialog').close();await refresh();toast('Обучение продолжено')}catch(error){$('resume-error').textContent=error.message}finally{btn.disabled=false}
}
function askConfirm(message){
  const dialog=$('confirm-dialog');
  if(dialog.open)return Promise.resolve(false);
  $('confirm-message').textContent=message;dialog.returnValue='cancel';
  return new Promise(resolve=>{dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true});dialog.showModal()});
}
const pieceGlyph={K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟︎'};
function expandFen(fen){const rows=fen.split(' ')[0].split('/');if(rows.length!==8)throw Error('FEN: неверное число рядов');return rows.map(row=>{let squares=[];for(const c of row){if(/[1-8]/.test(c))squares.push(...Array(+c).fill('.'));else if(pieceGlyph[c])squares.push(c);else throw Error('Неверный символ FEN')}if(squares.length!==8)throw Error('FEN: неверная длина ряда');return squares})}
function replayPosition(step){const game=application.replay;if(!game)return;step=Math.max(0,Math.min(step,game.moves.length));application.replayStep=step;
  const fen=game.fens[step],board=expandFen(fen),lastMove=step?game.moves[step-1]:'';
  let a=lastMove.slice(0,2),b=lastMove.slice(2,4);
  let markup='';for(let r=0;r<8;r++)for(let f=0;f<8;f++){
    const square='abcdefgh'[f]+(8-r),piece=board[r][f],last=step>0 && (square===a||square===b);
    markup+=`<div class="square ${(r+f)%2===0?'light':'dark'} ${last?'last':''}">${piece!=='.'?`<span class="piece ${piece===piece.toUpperCase()?'white':'black'}">${pieceGlyph[piece]}</span>`:''}${r===7||f===0?`<span class="coord">${r===7?'abcdefgh'[f]:8-r}</span>`:''}</div>`;
  }
  $('replay-board').innerHTML=markup;
  $('replay-fen').textContent=fen;$('replay-turn').textContent=fen.split(' ')[1]==='w'?'Ход белых':'Ход чёрных';
  $('replay-step').textContent=`${step} / ${game.moves.length}`;
  $('replay-range').value=step;
  qsa('#replay-moves button').forEach(b=>b.classList.toggle('current',+b.dataset.step===step));
  const selected=$(`replay-move-${step}`);if(selected)selected.scrollIntoView({block:'nearest'});
}
async function showReplay(gameId,kind){if(!application.selected)return;try{
  const game=await api(`/api/game/${gameId}?`+new URLSearchParams({run:application.selected,kind}));
  if(!game.fens||game.fens.length!==game.moves.length+1)throw Error('Неполная история позиций');
  application.replay=game;$('game-modal-title').textContent=`Партия #${game.game_id}`;
  $('replay-result').textContent=resultNames[game.result]||game.result;
  $('replay-metadata').textContent=`${reasonNames[game.reason]||game.reason} · ${game.plies} полуходов · Итерация ${game.iteration||'—'}${kind==='arena'?' · Arena':' · Self-play'}`;
  let html='';for(let i=0;i<game.moves.length;i+=2){html+=`<div class="move-pair"><span class="move-number">${1+i/2}.</span><button data-step="${i+1}" id="replay-move-${i+1}">${esc(game.moves[i])}</button>${game.moves[i+1]?`<button data-step="${i+2}" id="replay-move-${i+2}">${esc(game.moves[i+1])}</button>`:''}</div>`}
  $('replay-moves').innerHTML=html;$('replay-range').max=game.moves.length;$('game-overlay').classList.remove('hidden');$('game-overlay').setAttribute('aria-hidden','false');replayPosition(0);
}catch(e){toast('Не удалось открыть партию: '+e.message)}}
function closeReplay(){$('game-overlay').classList.add('hidden');$('game-overlay').setAttribute('aria-hidden','true');application.replay=null}
document.addEventListener('click',e=>{const nav=e.target.closest('[data-screen]');if(nav){navigate(nav.dataset.screen);return}
  const goto=e.target.closest('[data-goto]');if(goto){navigate(goto.dataset.goto);return}
  const preset=e.target.closest('[data-preset]');if(preset){applyPreset(preset.dataset.preset);return}
  const replay=e.target.closest('.view-game');if(replay){showReplay(+replay.dataset.id,replay.dataset.kind);return}
  const tab=e.target.closest('[data-metric]');if(tab){application.metric=tab.dataset.metric;qsa('[data-metric]').forEach(b=>b.classList.toggle('on',b===tab));if(application.overview)renderOverview(application.overview);return}
  const run=e.target.closest('[data-run]');if(run){application.selected=run.dataset.run;navigate('overview');refresh();return}
  const move=e.target.closest('.move-list button[data-step]');if(move){replayPosition(+move.dataset.step);return}});
async function startEvaluation(){
  if(!application.selected){toast('Выберите эксперимент');return}
  const payload={games:+$('eval-games').value,max_plies:+$('eval-plies').value,
       opening_plies:+$('eval-openings').value,opponent:$('eval-opponent').value,suite:$('eval-suite').value};
  try{const result=await api('/api/evaluation/'+encodeURIComponent(application.selected),
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      toast('Evaluation запущена: '+result.filename);await loadAnalysis()}
  catch(e){toast('Evaluation: '+e.message)}
}
async function startTournament(){
  if(!application.selected){toast('Выберите эксперимент');return}
  try{const result=await api('/api/tournament/'+encodeURIComponent(application.selected),
     {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({games:20,last:8,max_plies:400,opening_plies:8})});
     toast('Турнир запущен: '+result.filename);await loadAnalysis()}
  catch(e){toast('Турнир: '+e.message)}
}
$('start-tournament').onclick=startTournament;
$('start-evaluation').onclick=startEvaluation;
$('analysis-reload').onclick=loadAnalysis;
$('open-config').onclick=()=>configModal(true);$('runs-new').onclick=()=>configModal(true);$('close-config').onclick=()=>configModal(false);$('cancel-config').onclick=()=>configModal(false);
$('start-training').onclick=startTraining;$('stop-btn').onclick=stopTraining;$('resume-btn').onclick=resumeTraining;$('reload').onclick=refresh;
$('export-csv').onclick=()=>{if(!application.selected){toast('Сначала выберите эксперимент');return}window.location.href='/api/export/metrics.csv?run='+encodeURIComponent(application.selected)};
$('close-game').onclick=closeReplay;$('config-overlay').onclick=e=>{if(e.target===$('config-overlay'))configModal(false)};$('game-overlay').onclick=e=>{if(e.target===$('game-overlay'))closeReplay()};
$('run-picker').onchange=e=>{application.selected=e.target.value||null;refresh()};$('game-kind').onchange=loadGames;$('game-result').onchange=loadGames;
$('replay-range').oninput=e=>replayPosition(+e.target.value);
$('replay-first').onclick=()=>replayPosition(0);$('replay-last').onclick=()=>replayPosition(application.replay?.moves.length||0);
$('replay-next').onclick=()=>replayPosition(application.replayStep+1);$('replay-prev').onclick=()=>replayPosition(application.replayStep-1);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeReplay();configModal(false)}if(application.replay&&e.key==='ArrowRight')replayPosition(application.replayStep+1);if(application.replay&&e.key==='ArrowLeft')replayPosition(application.replayStep-1)});
async function poll(){try{if(!document.hidden&&!application.overlayOpen&&!application.replay&&!$('command-dialog').open&&!$('resume-dialog').open&&!$('confirm-dialog').open){await refresh();if(application.screen==='games')await loadGames();if(researchScreens.has(application.screen))await loadAnalysis()}}finally{setTimeout(poll,2500)}}

$('compact-storage').onclick=async()=>{if(!application.selected){toast('Выберите эксперимент');return}if(!await askConfirm('Обучение остановлено? Сжать журналы эксперимента без потери истории?'))return;try{const d=await api('/api/storage/'+encodeURIComponent(application.selected)+'/compact',{method:'POST'});toast('Безопасное сжатие выполнено: '+num(d.result.saved_bytes/1048576,1)+' МБ освобождено');await loadAnalysis()}catch(e){toast('Сжатие: '+e.message)}};


async function loadAgentLab(run){
  const area=$('agent-results'),health=$('agent-training-health');if(!area||!health)return;
  try{
    const data=await api('/api/agents/'+encodeURIComponent(run));
    if(application.selected!==run)return;const status=data.process||{};
    let text=['aggressive','defender','phantom'].map(name=>{
      const report=data.reports?.[name]||{}, file=name+'.pt';
      return `<div class="diagnostic-item"><strong>${name==='aggressive'?'Aggressive':name==='defender'?'Defender':'Фантом-X23'} · ${data.models?.[file]?'Checkpoint создан':'Пока не обучен'}</strong><p>${esc(report.status||'Нет отчёта')} · примеров ${fmt(report.positions||0)} · holdout ${num(report.best?.loss??report.best?.nll,4)}${report.best?' · '+(name==='phantom'?'book top1 ':'teacher top1 ')+num(100*(report.best.teacher_top1??report.best.policy_top1??0),1)+'%':''}</p></div>`;
    }).join('');
    if(status.active)text+=`<div class="diagnostic-item"><strong>Обучение ${esc(status.profile)} выполняется</strong><p>${(data.log||[]).slice(-6).map(esc).join('<br>')}</p></div>`;
    area.innerHTML=text;
    const h=data.health||{};
    health.innerHTML=`<div class="diagnostic-item"><strong>Контроль PPO · ${fmt(h.iterations)} последних итераций</strong><p>Ничьи: ${h.draw_share!=null?num(100*h.draw_share,1)+'%':'—'} · Остановки по KL: ${h.kl_early_stop_share!=null?num(100*h.kl_early_stop_share,1)+'%':'—'} · arena: ${h.arena_score_mean!=null?num(100*h.arena_score_mean,1)+'%':'—'}</p>${(h.warnings||[]).map(w=>'<p>⚠ '+esc(w)+'</p>').join('')}</div>`;
  }catch(error){area.textContent='Agent Lab: '+error.message}
}

async function trainSpecialist(profile){
  if(!application.selected){toast('Выберите эксперимент');return}
  if(!await askConfirm('Запустить отдельное обучение '+profile+'? Основные веса и PPO не изменятся.'))return;
  try{
    const body={epochs:+$('agent-epochs').value,max_rows:+$('agent-rows').value,batch_size:+$('agent-batch').value,teacher_depth:+$('agent-depth').value};
    await api('/api/agents/'+encodeURIComponent(application.selected)+'/train/'+profile,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    toast('Обучение '+profile+' запущено');await loadAgentLab(application.selected);
  }catch(e){toast('Agent Lab: '+e.message)}
}

document.addEventListener('click',async e=>{
  const test=e.target.closest('.agent-evaluate');if(test){
    if(!application.selected){toast('Выберите эксперимент');return}
    if(!await askConfirm('Запустить 40 контрольных партий '+test.dataset.profile+' против SkillBoost II?'))return;
    api('/api/agents/'+encodeURIComponent(application.selected)+'/evaluate/'+test.dataset.profile,{method:'POST'})
      .then(x=>toast('Независимое сравнение запущено: '+x.filename)).catch(e=>toast(e.message));
    return;
  }
  const btn=e.target.closest('.agent-train');if(btn){trainSpecialist(btn.dataset.profile);return}
  if(e.target.id==='agent-stop'&&application.selected){
    if(!await askConfirm('Остановить текущую специализацию? Уже сохранённые модели останутся.'))return;
    api('/api/agents/'+encodeURIComponent(application.selected)+'/stop',{method:'POST'}).then(()=>toast('Запрос остановки отправлен')).catch(e=>toast(e.message));
  }
});


function renderLog(d){const el=$('console-output');if($('log-pause').checked)return;const atBottom=el.scrollHeight-el.scrollTop-el.clientHeight<24;const q=$('log-search').value.toLowerCase();const text=(d.log||[]).filter(x=>String(x).toLowerCase().includes(q)).join('\n')||'Нет строк';if(el.textContent!==text){el.textContent=text;if(atBottom)el.scrollTop=el.scrollHeight}}
$('log-search').oninput=()=>{if(application.overview)renderLog(application.overview)};
$('log-pause').onchange=()=>{if(application.overview)renderLog(application.overview)};
async function copyText(text){try{await navigator.clipboard.writeText(text);toast('Скопировано')}catch(e){toast('Не удалось скопировать: '+e.message)}}
$('log-copy').onclick=()=>copyText($('console-output').textContent);
$('copy-fen').onclick=()=>copyText($('replay-fen').textContent);
$('chart-range').onchange=()=>{chartAnchor=null;if(application.overview)renderMainChart(application.overview)};
$('chart-smooth').onchange=()=>{if(application.overview)renderMainChart(application.overview)};
$('chart-pan').oninput=e=>{const m=application.overview?.metrics||[];const idx=Number(e.target.value);chartAnchor=idx===m.length-1?null:m[idx]?.iteration??null;if(application.overview)renderMainChart(application.overview)};
$('chart-live').onclick=()=>{chartAnchor=null;if(application.overview)renderMainChart(application.overview)};
$('chart-reference').onchange=()=>{referenceSnapshot=null;referenceRequest++;$('chart-reference-note').textContent='Снимок по запросу, без автообновления.';if(application.overview)renderMainChart(application.overview)};
$('chart-reference-load').onclick=fetchReference;
$('chart-download').onclick=()=>{if(!chartExport.length)return;const url=URL.createObjectURL(new Blob([LA.csv(chartExport)],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='chessai-'+application.metric+'-window.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
$('evaluation-select').onchange=renderEvaluationDetail;$('performance-metric').onchange=()=>renderPerformance(profileRows);
const shell=document.querySelector('.shell');
function collapse(value){shell.classList.toggle('collapsed',value);$('sidebar-toggle').setAttribute('aria-expanded',String(!value));$('sidebar-toggle').setAttribute('aria-label',value?'Развернуть навигацию':'Свернуть навигацию');$('sidebar-toggle').innerHTML=value?'›':'‹ <span>Свернуть</span>';try{localStorage.setItem('lab.sidebar',String(value))}catch(_){}}
try{collapse(localStorage.getItem('lab.sidebar')==='true')}catch(_){}
$('sidebar-toggle').onclick=()=>collapse(!shell.classList.contains('collapsed'));
const command=$('command-dialog');
function commandFilter(){const q=$('command-search').value.toLowerCase();const buttons=qsa('.nav-item').filter(b=>b.title.toLowerCase().includes(q));$('command-results').replaceChildren(...buttons.map(b=>{const el=document.createElement('button');el.className='button subtle';el.textContent=b.title;el.onclick=()=>{command.close();navigate(b.dataset.screen)};return el}));if(!buttons.length)$('command-results').textContent='Нет совпадений'}
function openCommand(){if(application.overlayOpen||application.replay||command.open||$('resume-dialog').open||$('confirm-dialog').open)return;command.showModal();$('command-search').value='';commandFilter();$('command-search').focus()}
$('command-open').onclick=openCommand;$('command-close').onclick=()=>command.close();$('command-search').oninput=commandFilter;$('command-search').onkeydown=e=>{if(e.key==='Enter')$('command-results').querySelector('button')?.click()};
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommand()}});
poll();

$('resume-form').onsubmit=submitResume;
for(const id of ['resume-close','resume-cancel'])$(id).onclick=()=>{if(!$('resume-submit').disabled)$('resume-dialog').close()};
$('resume-dialog').addEventListener('cancel',e=>{if($('resume-submit').disabled)e.preventDefault()});

// Geometry-only refresh: no additional API polling on window resizing or screen switches.
if(typeof ResizeObserver==='function'){
  const observer=new ResizeObserver(entries=>{for(const entry of entries){const el=entry.target,state=graphState.get(el);if(!state||!el.clientWidth||!el.clientHeight)continue;graph(el,state.values,state.options)}});
  for(const id of ['main-chart','speed-chart','completion-chart','analysis-value-chart','kl-chart','clip-chart','performance-chart','batch-chart'])observer.observe($(id));
}
