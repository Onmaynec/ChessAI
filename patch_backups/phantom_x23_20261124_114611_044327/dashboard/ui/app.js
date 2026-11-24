'use strict';
const $ = id => document.getElementById(id);
const qsa = s => Array.from(document.querySelectorAll(s));
const fmt = n => Number(n||0).toLocaleString('ru-RU');
const num = (n, precision=2) => n == null || !Number.isFinite(+n) ? '—' : Number(n).toLocaleString('ru-RU',{maximumFractionDigits:precision});
const esc = x => String(x??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusNames = {running:'ОБУЧЕНИЕ ИДЁТ',completed:'ЗАВЕРШЕНО',stopped:'ОСТАНОВЛЕНО',failed:'ОШИБКА',unknown:'НЕИЗВЕСТНО'};
const resultNames = {'1-0':'Победа белых','0-1':'Победа чёрных','1/2-1/2':'Ничья','*':'Не завершена'};
const reasonNames = {checkmate:'Шах и мат',stalemate:'Пат',insufficient_material:'Недостаточно материала',threefold_repetition_claimed:'Троекратное повторение',fivefold_repetition:'Пятикратное повторение', '50_move_rule_claimed':'Правило 50 ходов','75_move_rule':'Правило 75 ходов',max_plies_unfinished:'Достигнут лимит полуходов',ongoing:'Продолжается'};
const application = {selected:null, screen:'overview', metric:'value', overview:null, replay:null, replayStep:0, inFlight:false, overlayOpen:false};
const api = async (url, opts) => {const res=await fetch(url,{cache:'no-store',...opts});let data={};try{data=await res.json()}catch(_){throw Error('Неверный ответ сервера')}if(!res.ok)throw Error(data.detail||data.message||('HTTP '+res.status));return data};
function toast(text){const el=$('toast');el.textContent=text;el.classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.add('hidden'),4800)}
function navigate(screen){application.screen=screen;qsa('.screen').forEach(e=>e.classList.toggle('hidden',e.id!=='screen-'+screen));qsa('.nav-item').forEach(e=>e.classList.toggle('selected',e.dataset.screen===screen));$('breadcrumb').textContent={overview:'Обзор обучения',games:'Партии и анализ',analysis:'Диагностика модели',runs:'История запусков',guide:'Справка'}[screen];if(screen==='games')loadGames();if(screen==='runs')renderRuns();if(screen==='analysis')loadAnalysis()}
function classResult(result){return result==='1-0'||result==='0-1'?'win':result==='1/2-1/2'?'draw':'pending'}
function graph(container, values, {accent='#a8eb7c',height=245,unit='',ymin=null}={}){
  const vals=values.map(Number).filter(Number.isFinite);
  if(!vals.length){container.innerHTML='<div class="empty-chart"><span>⌁</span>Для графика пока недостаточно данных.</div>';return}
  const w=780,h=height,l=59,r=18,t=20,b=35;
  let lo=ymin!==null?ymin:Math.min(...vals),hi=Math.max(...vals);if(lo===hi){lo-=Math.max(.05,Math.abs(lo)*.15);hi+=Math.max(.05,Math.abs(hi)*.15)}else{const d=(hi-lo)*.16;hi+=d;if(ymin===null)lo-=d}
  if(hi<=lo)hi=lo+1;
  const fx=i=>l+(w-l-r)*(vals.length===1?.5:i/(vals.length-1));
  const fy=v=>t+(h-t-b)*(1-(v-lo)/(hi-lo));
  let paths='',labels='';
  for(let i=0;i<=4;i++){const y=t+(h-t-b)*i/4;const v=hi-(hi-lo)*i/4;paths+=`<line x1="${l}" y1="${y}" x2="${w-r}" y2="${y}" stroke="#2d3a4b" stroke-dasharray="4 6"/>`;labels+=`<text x="${l-12}" y="${y+4}" text-anchor="end" fill="#708398" font-size="13">${num(v,3)}</text>`}
  const pts=vals.map((v,i)=>`${fx(i)},${fy(v)}`).join(' ');
  const area=`M ${fx(0)},${fy(vals[0])} ${vals.slice(1).map((v,i)=>`L ${fx(i+1)},${fy(v)}`).join(' ')} L ${fx(vals.length-1)},${h-b} L ${fx(0)},${h-b} Z`;
  let circles=vals.map((v,i)=>`<circle cx="${fx(i)}" cy="${fy(v)}" r="${vals.length<25?4:2}" fill="${accent}"/>`).join('');
  let axes=`<text x="${l}" y="${h-9}" fill="#708398" font-size="13">1</text><text x="${w-r}" y="${h-9}" text-anchor="end" fill="#708398" font-size="13">${vals.length} итераций</text>`;
  container.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="График изменения метрики"><defs><linearGradient id="shade-${container.id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${accent}" stop-opacity=".22"/><stop offset="100%" stop-color="${accent}" stop-opacity="0"/></linearGradient></defs>${paths}${labels}${axes}<path d="${area}" fill="url(#shade-${container.id})"/><polyline points="${pts}" fill="none" stroke="${accent}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>${circles}</svg>`;
}
function renderOverview(d){
  application.overview=d;
  const picker=$('run-picker');
  const old=picker.value;
  picker.innerHTML=d.runs.length ? d.runs.map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('') : '<option value="">Нет запусков</option>';
  application.selected=d.selected||null; picker.value=d.selected||'';
  const st=d.state||{},c=st.counters||{},meta=d.metadata||{},cfg=meta.config||{};
  const state=st.status||'unknown';
  const isRunning=d.process?.active && d.process.run===d.selected;
  const interrupted=state==='running' && !isRunning;
  $('run-title').textContent=d.selected ? d.selected : 'Обучение ещё не запускалось';
  $('run-detail').textContent=d.selected ? `Итерация ${st.iteration||0} · ${st.phase||'ожидание'} · ${st.device||'неизвестно'} · ${fmt(meta.parameters)} параметров` : 'Создайте первый эксперимент, чтобы увидеть реальные показатели.';
  $('status-badge').textContent=d.selected ? (interrupted?'ПРЕРВАНО':statusNames[state]||state) : 'НЕ ЗАПУЩЕНО';$('status-badge').className='status-badge '+(d.selected?state:'');
  $('banner-symbol').textContent=state==='completed'?'✓':state==='failed'?'!':isRunning?'◈':'◎';
  $('stop-btn').classList.toggle('hidden',!isRunning);
  $('resume-btn').classList.toggle('hidden',!d.selected || isRunning || !['stopped','completed','failed','running'].includes(state));
  const accessWarnings=d.file_warnings||[];
  $('sync-label').textContent = accessWarnings.length
    ? `⚠ Файлы временно недоступны (${accessWarnings.length}); использованы последние данные`
    : (isRunning ? 'Live · обновление 2,5 сек.' : 'Локальные данные');
  $('sync-label').title = accessWarnings.map(w=>`${w.file}: ${w.message}`).join('\n');
  const m=d.metrics||[];
  const completed=m.length?m[m.length-1].iteration:0;
  const target=st.target_iteration||cfg.iterations||0;
  const pct=target>0?Math.max(0,Math.min(100,completed/target*100)):0;
  $('progress-fill').style.width=pct+'%';$('progress-text').textContent=`${fmt(completed)} / ${fmt(target)} итераций`;$('progress-pct').textContent=`${num(pct,0)}%`;
  $('phase-label').textContent=isRunning?`Текущая фаза: ${ {selfplay:'самоигра',optimization:'обновление сети',arena:'проверочные матчи',ready:'завершение итерации'}[st.phase]||st.phase||'запуск'} · партий в итерации ${st.iteration_games||0} / ${st.iteration_target||cfg.games_per_iteration||0}` : 'Итерации сохраняются с checkpoint после каждого завершённого обновления';
  $('m-games').textContent=fmt(c.games);$('m-finished').textContent=fmt(c.finished);$('m-plies').textContent=fmt(c.plies);$('m-samples').textContent=fmt(c.samples);
  $('m-games-extra').textContent=`${fmt(c.unfinished)} достигли лимита / не завершены`;
  $('m-finished-extra').textContent=c.games ? `${num(100*(c.finished||0)/c.games,1)}% всех партий` : 'Мат, пат, ничья по правилам';
  $('m-plies-extra').textContent=c.games ? `${num((c.plies||0)/c.games,1)} в среднем / партия` : 'Полуход — одно действие игрока';
  $('m-samples-extra').textContent='Использованы для обучения PPO';
  $('result-count').textContent=fmt(c.games)+' партий';$('donut-total').innerHTML=fmt(c.finished||0)+'<small>завершено</small>';
  const count=c.games||0;
  let a=0;const colors=[['white_wins','#a8eb7c'],['black_wins','#73c3d5'],['draws','#b9a7fc'],['unfinished','#586677']];
  let segments=colors.map(([name,color])=>{const next=a+(count?100*(c[name]||0)/count:0);let v=`${color} ${a}% ${next}%`;a=next;return v});
  $('result-donut').style.background=count?`conic-gradient(${segments.join(',')})`:'var(--line)';
  $('r-white').textContent=fmt(c.white_wins);$('r-black').textContent=fmt(c.black_wins);$('r-draw').textContent=fmt(c.draws);$('r-unfinished').textContent=fmt(c.unfinished);
  const metricName={value:'Value MSE',policy:'Policy loss',entropy:'Entropy'};
  const metricKey={value:'value_mse',policy:'policy_loss',entropy:'entropy'}[application.metric];
  const values=m.map(x=>x.train?.[metricKey]).filter(x=>x!=null);
  graph($('main-chart'),values,{accent:application.metric==='policy'?'#73c3d5':application.metric==='entropy'?'#b9a7fc':'#a8eb7c'});
  $('graph-name').textContent=metricName[application.metric];
  $('graph-note').textContent=application.metric==='value'?'MSE на исходах самоигры, не рейтинг силы':application.metric==='policy'?'Знак и значение PPO loss зависят от преимуществ':'Энтропия политики в текущих позициях';
  graph($('speed-chart'),m.map(x=>x.plies_per_s),{accent:'#73c3d5',height:130,ymin:0});
  const last=m.at(-1);
  $('s-gps').textContent=num(last?.games_per_s,3);$('s-pps').textContent=num(last?.plies_per_s,1);
  const arenaRuns=m.filter(x=>x.arena?.completed>0);
  let aw=0,al=0,ad=0,ap=0;
  for(const row of m){aw+=row.arena?.wins||0;al+=row.arena?.losses||0;ad+=row.arena?.draws||0;ap+=row.arena?.played||0}
  const ac=aw+al+ad;
  $('arena-score').textContent=ac?num(100*(aw+.5*ad)/ac,1)+'%':'—';
  $('arena-hint').textContent=ac?`Счёт по завершённым партиям, n = ${fmt(ac)}`:'Нет завершённых проверочных партий';
  $('arena-wld').textContent=`В: ${fmt(aw)} · Н: ${fmt(ad)} · П: ${fmt(al)}`;
  $('arena-size').textContent=`${fmt(ap)} проведено · ${fmt(ap-ac)} не окончено`;
  $('arena-caption').textContent='vs. frozen v0.2';
  $('recent-games').innerHTML=d.games.length?d.games.slice(0,6).map(g=>`<tr><td>#${g.game_id} <small> / ${g.iteration}</small></td><td><span class="result-pill ${classResult(g.result)}">${esc(resultNames[g.result]||g.result)}</span></td><td>${esc(reasonNames[g.reason]||g.reason)}</td><td>${fmt(g.plies)}</td><td><button class="table-button view-game" data-id="${g.game_id}" data-kind="selfplay">Просмотр →</button></td></tr>`).join(''):'<tr><td colspan="5" class="table-empty">Партии пока отсутствуют</td></tr>';
  if(application.screen==='runs')renderRuns();
}
function renderRuns(){const d=application.overview;if(!d)return;
  $('run-list').innerHTML=d.runs.length?d.runs.map(r=>`<article class="run-card ${r.id===d.selected?'current':''}" data-run="${esc(r.id)}"><span class="status-badge ${esc(r.status)}">${esc(statusNames[r.status]||r.status)}</span><h2>${esc(r.name)}</h2><p>${esc(r.created_at?.replace('T',' ').replace('+00:00',' UTC')||'Дата неизвестна')}</p><div class="run-totals"><span><b>${fmt(r.iteration)}</b> итераций</span><span><b>${fmt(r.games)}</b> партий</span></div></article>`).join(''):'<div class="panel empty-panel">Пока нет экспериментов. Нажмите «Создать запуск».</div>';
  $('console-output').textContent=d.log?.join('\n')||'Журнал пуст.\n';
}

async function loadAnalysis(){
  if(!application.selected){$('analysis-warnings').textContent='Выберите или создайте эксперимент.';return}
  const run=application.selected;
  try{
    const data=await api('/api/analysis?run='+encodeURIComponent(run));
    await loadAgentLab(run);
    try {
      const storage=await api('/api/storage/'+encodeURIComponent(run));
      const sp=storage.space||{};
      const mb=x=>num((x||0)/1048576,1)+' МБ';
      $('storage-status').innerHTML=`<div class="diagnostic-item"><strong>На диске: ${mb(sp.total_bytes)}</strong><p>Несжатые журналы: ${mb(sp.journals_bytes)} · Сжатые архивы: ${mb(sp.archives_bytes)} · Checkpoint: ${mb(sp.checkpoint_bytes)} · Прочее: ${mb(sp.other_bytes)}</p></div>`;
    } catch(error) { $('storage-status').textContent='Место на диске: '+error.message; }
    const perf=(data.series||[]).filter(m=>m.performance?.mode).at(-1)?.performance;
    $('performance-status').innerHTML=perf?`<div class="diagnostic-item"><strong>Непрерывные партии · ${fmt(perf.concurrent_games)} слотов · ${fmt(perf.bridge_workers)} C++ workers</strong><p>Открытия: ${num(perf.opening_s,2)} с · ходы C++: ${num(perf.bridge_steps_s,2)} с · инференс: ${num(perf.neural_inference_s,2)} с · PPO: ${num(perf.ppo_s,2)} с · средний GPU-пакет: ${num(perf.average_inference_batch,1)} позиций</p></div>`:'<div class="diagnostic-item"><strong>Профиль пока не записан</strong><p>Появится после итерации на v0.7.0.</p></div>';
    if(application.selected!==run)return;
    const t=data.totals||{}, a=data.arena||{}, c=data.checkpoint||{};
    $('a-finished').textContent=fmt(t.finished);
    $('a-finished-note').textContent=`${num(100*(data.completion_rate||0),1)}% завершённых · ${fmt(t.unfinished)} незавершённых`;
    $('a-samples').textContent=fmt(t.samples);
    $('a-score').textContent=a.score==null?'—':num(100*a.score,1)+'%';
    $('a-score-note').textContent=a.completed?`Описательный счёт, n=${fmt(a.completed)}. Старые матчи повторяли одни и те же партии.`:'Нет завершённых матчей';
    $('a-checkpoint').textContent=c.exists?'Найден':'Нет';
    $('a-checkpoint-note').textContent=c.exists?`${num((c.size_bytes||0)/1024,0)} КБ · сохранён в runs/`:'Продолжение недоступно';
    graph($('completion-chart'),(data.series||[]).map(x=>x.finish_rate),{accent:'#a8eb7c',ymin:0});
    graph($('analysis-value-chart'),(data.series||[]).map(x=>x.value_mse).filter(x=>x!=null),{accent:'#73c3d5',ymin:0});
    $('analysis-warnings').innerHTML=data.warnings?.length?data.warnings.map(w=>`<div class="diagnostic-item"><strong>${w.level==='warning'?'Внимание':'Замечание'}</strong><p>${esc(w.text)}</p></div>`).join(''):'<div class="diagnostic-item"><strong>Данных пока недостаточно</strong><p>Начните обучение, чтобы увидеть рекомендации.</p></div>';
    const evals=data.evaluations||[];
    $('evaluation-history').innerHTML=evals.length?evals.map(x=>{const v=x.statistics||{};return `<div class="diagnostic-item"><strong>${esc(x.created_at||x.filename)} · ${v.score==null?'—':num(100*v.score,1)+'%'} score</strong><p>${fmt(v.wins)} побед · ${fmt(v.draws)} ничьих · ${fmt(v.losses)} поражений · ${fmt(v.unfinished)} незавершённых · ${fmt(v.completed)} учтённых · ${fmt(v.unique_sequences??'?')} уникальных партий · ${fmt(v.unique_opening_positions??'?')} стартовых позиций · набор: ${esc(x.suite||'legacy')}${v.unique_sequences===2 && v.completed>=20?' · ⚠ Повторяющиеся матчи':''}</p></div>`}).join(''):'<div class="diagnostic-item"><strong>Нет дополнительных проверок</strong><p>Запустите scripts/EVALUATE_RUN_WINDOWS.bat для независимой серии матчей. Существующие контрольные матчи показаны в разделе «Обзор».</p></div>';
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
  }catch(error){toast('Диагностика: '+error.message)}
}

async function loadGames(){if(!application.selected)return;
  const kind=$('game-kind').value,result=$('game-result').value;
  try{const data=await api('/api/games?'+new URLSearchParams({run:application.selected,kind,result,limit:'50'}));$('games-count').textContent=`${data.games.length} последних записей`;
  $('games-list').innerHTML=data.games.length?data.games.map(g=>`<tr><td>#${g.game_id}</td><td>${g.iteration}</td><td><span class="result-pill ${classResult(g.result)}">${esc(resultNames[g.result]||g.result)}</span></td><td>${esc(reasonNames[g.reason]||g.reason)}</td><td>${fmt(g.plies)}</td><td><button class="table-button view-game" data-id="${g.game_id}" data-kind="${kind}">Открыть →</button></td></tr>`).join(''):'<tr><td colspan="6" class="table-empty">Записей с таким результатом пока нет</td></tr>';}
  catch(e){toast(e.message)}
}
async function refresh(){if(application.inFlight)return;application.inFlight=true;try{
  const runParam=application.selected?'?run='+encodeURIComponent(application.selected):'';
  const [d,h]=await Promise.all([api('/api/overview'+runParam),api('/api/health')]);
  $('engine-led').className='led '+(h.engine_ready?'ok':'bad');$('engine-text').textContent=h.engine_ready?'Chess Core доступен':'C++ ядро не собрано';
  // If a run was deleted externally, recover to most recent.
  if(!d.selected && application.selected) application.selected=null;
  renderOverview(d);
}catch(e){$('sync-label').textContent='Ошибка связи';toast('Не удалось получить данные: '+e.message)}finally{application.inFlight=false}}
function configModal(open){application.overlayOpen=open;$('config-overlay').classList.toggle('hidden',!open);$('config-overlay').setAttribute('aria-hidden',String(!open));if(open)$('c-iterations').focus()}
const presets={quick:{iterations:2,games:2,parallel:2,plies:140,temp:1.1,arena:0,opening:0},balanced:{iterations:10,games:8,parallel:4,plies:240,temp:1.1,arena:2,opening:6},long:{iterations:100,games:16,parallel:8,plies:300,temp:1.1,arena:4,opening:6}};
function applyPreset(name){const p=presets[name];if(!p)return;qsa('[data-preset]').forEach(b=>b.classList.toggle('chosen',b.dataset.preset===name));for(const k of Object.keys(p))$('c-'+k).value=p[k]}
async function startTraining(){const payload={iterations:+$('c-iterations').value,games_per_iteration:+$('c-games').value,parallel:+$('c-parallel').value,max_plies:+$('c-plies').value,temperature:+$('c-temp').value,arena_games:+$('c-arena').value,opening_plies:+$('c-opening').value,league_fraction:+$('c-league').value/100, repetition_penalty:+$('c-repeat').value, target_kl:+$('c-kl').value,bridge_workers:+$('c-workers').value,batch_size:+$('c-batch').value,archive_every:+$('c-archive').value};
  const btn=$('start-training');btn.disabled=true;$('config-error').textContent='';try{const d=await api('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});application.selected=d.run;configModal(false);navigate('overview');await refresh();toast('Эксперимент запущен: '+d.run)}catch(e){$('config-error').textContent=e.message}finally{btn.disabled=false}}
async function stopTraining(){if(!confirm('Остановить обучение после окончания текущей итерации? Результаты сохранятся.'))return;try{const d=await api('/api/stop',{method:'POST'});toast('Запрос остановки принят. Текущая итерация завершится.')}catch(e){toast(e.message)}}
async function resumeTraining(){if(!application.selected)return;const text=prompt('Сколько ДОПОЛНИТЕЛЬНЫХ итераций выполнить?', '10');if(text===null)return;const iterations=+text;if(!Number.isSafeInteger(iterations)||iterations<1||iterations>100000){toast('Введите целое число от 1 до 100000');return}const prior=application.overview?.metadata?.config?.max_plies||240;const capText=prompt('Лимит полуходов для новых партий (увеличение помогает завершить больше партий; прежние веса сохранятся):',String(prior));if(capText===null)return;const max_plies=+capText;if(!Number.isSafeInteger(max_plies)||max_plies<8||max_plies>1500){toast('Лимит должен быть целым числом от 8 до 1500');return}const before=application.overview?.metadata?.config?.opening_plies??0;
  const openingsText=prompt('Дебютное разнообразие: сколько легальных полуходов разыгрывать перед новой партией? 0 = старый режим, 6 = новый:',String(before));
  if(openingsText===null)return;
  const opening_plies=+openingsText;
  if(!Number.isSafeInteger(opening_plies)||opening_plies<0||opening_plies>16){toast('Введите число 0–16');return}
  const conf=application.overview?.metadata?.config||{};
  const parallelText=prompt('Одновременные партии на GPU (не больше числа партий/итерацию):',String(conf.parallel??8));
  if(parallelText===null)return;
  const parallel=+parallelText;
  if(!Number.isSafeInteger(parallel)||parallel<1||parallel>64){toast('Введите 1–64');return}
  const workersText=prompt('Параллельные CPU-процессы Chess Core (для Ryzen 5600 начни с 2):',String(conf.bridge_workers??2));
  if(workersText===null)return;
  const bridge_workers=+workersText;
  if(!Number.isSafeInteger(bridge_workers)||bridge_workers<1||bridge_workers>8){toast('Введите 1–8');return}
  try{await api('/api/resume/'+encodeURIComponent(application.selected),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({iterations,max_plies,opening_plies,parallel,bridge_workers,archive_every:5})});await refresh();toast('Обучение продолжено')}catch(e){toast(e.message)}}
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
  $('replay-turn').textContent=fen.split(' ')[1]==='w'?'Ход белых':'Ход чёрных';
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
refresh();setInterval(()=>{if(!document.hidden&&!application.overlayOpen){refresh();if(application.screen==='games')loadGames();if(application.screen==='analysis')loadAnalysis()}},2500);

$('compact-storage').onclick=async()=>{if(!application.selected){toast('Выберите эксперимент');return}if(!confirm('Обучение остановлено? Сжать журналы эксперимента без потери истории?'))return;try{const d=await api('/api/storage/'+encodeURIComponent(application.selected)+'/compact',{method:'POST'});toast('Безопасное сжатие выполнено: '+num(d.result.saved_bytes/1048576,1)+' МБ освобождено');await loadAnalysis()}catch(e){toast('Сжатие: '+e.message)}};


async function loadAgentLab(run){
  const area=$('agent-results'),health=$('agent-training-health');if(!area||!health)return;
  try{
    const data=await api('/api/agents/'+encodeURIComponent(run));
    const status=data.process||{};
    let text=['aggressive','defender'].map(name=>{
      const report=data.reports?.[name]||{}, file=name+'.pt';
      return `<div class="diagnostic-item"><strong>${name==='aggressive'?'Aggressive':'Defender'} · ${data.models?.[file]?'Checkpoint создан':'Пока не обучен'}</strong><p>${esc(report.status||'Нет отчёта')} · примеров ${fmt(report.positions||0)} · holdout ${num(report.best?.loss,4)}${report.best?' · teacher top1 '+num(100*report.best.teacher_top1,1)+'%':''}</p></div>`;
    }).join('');
    if(status.active)text+=`<div class="diagnostic-item"><strong>Обучение ${esc(status.profile)} выполняется</strong><p>${(data.log||[]).slice(-6).map(esc).join('<br>')}</p></div>`;
    area.innerHTML=text;
    const h=data.health||{};
    health.innerHTML=`<div class="diagnostic-item"><strong>Контроль PPO · ${fmt(h.iterations)} последних итераций</strong><p>Ничьи: ${h.draw_share!=null?num(100*h.draw_share,1)+'%':'—'} · Остановки по KL: ${h.kl_early_stop_share!=null?num(100*h.kl_early_stop_share,1)+'%':'—'} · arena: ${h.arena_score_mean!=null?num(100*h.arena_score_mean,1)+'%':'—'}</p>${(h.warnings||[]).map(w=>'<p>⚠ '+esc(w)+'</p>').join('')}</div>`;
  }catch(error){area.textContent='Agent Lab: '+error.message}
}

async function trainSpecialist(profile){
  if(!application.selected){toast('Выберите эксперимент');return}
  if(!confirm('Запустить отдельное обучение '+profile+'? Основные веса и PPO не изменятся.'))return;
  try{
    const body={epochs:+$('agent-epochs').value,max_rows:+$('agent-rows').value,batch_size:+$('agent-batch').value,teacher_depth:+$('agent-depth').value};
    await api('/api/agents/'+encodeURIComponent(application.selected)+'/train/'+profile,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    toast('Обучение '+profile+' запущено');await loadAgentLab(application.selected);
  }catch(e){toast('Agent Lab: '+e.message)}
}

document.addEventListener('click',e=>{
  const test=e.target.closest('.agent-evaluate');if(test){
    if(!application.selected){toast('Выберите эксперимент');return}
    if(!confirm('Запустить 40 контрольных партий '+test.dataset.profile+' против SkillBoost II?'))return;
    api('/api/agents/'+encodeURIComponent(application.selected)+'/evaluate/'+test.dataset.profile,{method:'POST'})
      .then(x=>toast('Независимое сравнение запущено: '+x.filename)).catch(e=>toast(e.message));
    return;
  }
  const btn=e.target.closest('.agent-train');if(btn){trainSpecialist(btn.dataset.profile);return}
  if(e.target.id==='agent-stop'&&application.selected){
    if(!confirm('Остановить текущую специализацию? Уже сохранённые модели останутся.'))return;
    api('/api/agents/'+encodeURIComponent(application.selected)+'/stop',{method:'POST'}).then(()=>toast('Запрос остановки отправлен')).catch(e=>toast(e.message));
  }
});

