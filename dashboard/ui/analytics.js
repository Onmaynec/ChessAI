/* Pure data transforms: no I/O, no inferred Elo, no synthetic production data. */
(function(root){
'use strict';
const numeric=v=>typeof v==='number'&&Number.isFinite(v)?v:null;
function rows(values,iterations){return values.map((v,i)=>({x:iterations==null?i+1:numeric(iterations[i]),y:numeric(v)})).filter(r=>r.x!==null)}
function windowRows(data,size,anchor){
 if(!data.length)return [];
 const end=anchor==null?data.length:Math.max(0,data.findLastIndex(x=>x.x<=anchor)+1);
 return data.slice(Math.max(0,end-size),end);
}
function smooth(data,period){
 const queue=[];let sum=0,last=null;
 return data.map(row=>{if(row.y===null||last!==null&&row.x!==last+1){queue.length=0;sum=0}
 last=row.x;if(row.y===null)return {x:row.x,y:null};queue.push(row.y);sum+=row.y;if(queue.length>period)sum-=queue.shift();
 return {x:row.x,y:queue.length===period?sum/period:null}});
}
function aligned(main,reference){const byIteration=new Map(reference.map(r=>[r.x,r.y]));return main.map(r=>({x:r.x,y:byIteration.get(r.x)??null}))}
function extent(series,floor=null){
 let lo=Infinity,hi=-Infinity;for(const data of series)for(const r of data)if(r.y!==null){lo=Math.min(lo,r.y);hi=Math.max(hi,r.y)}
 if(!Number.isFinite(lo))return null;
 if(floor!==null)lo=Math.min(floor,lo);
 const spread=Math.max((hi-lo)*.1,Math.abs(hi)*.015,.000001);
 return {lo:floor===null?lo-spread:lo,hi:hi+spread};
}
function outcome(stats){
 const keys=['wins','draws','losses','unfinished'], vals=keys.map(k=>numeric(stats?.[k]));
 if(vals.some(v=>v===null||v<0||!Number.isInteger(v)))return null;
 const [w,d,l,u]=vals,n=w+d+l,total=n+u;
 return {w,d,l,u,n,total,score:n?(w+.5*d)/n:null,parts:vals.map(v=>total?100*v/total:0)};
}
function conditions(a,b){const keys=['reference','suite','seed','opening_plies','max_plies','games_requested'];return keys.map(key=>({key,a:a?.[key]??null,b:b?.[key]??null,state:a?.[key]==null||b?.[key]==null?'unknown':a[key]===b[key]?'same':'different'}))}
function csv(data){return ['iteration,raw,rolling_mean,reference',...data.map(r=>[r.x,r.y??'',r.smooth??'',r.reference??''].join(','))].join('\n')+'\n'}
const api={numeric,rows,windowRows,smooth,aligned,extent,outcome,conditions,csv};
if(typeof module==='object'&&module.exports)module.exports=api;else root.LabAnalytics=api;
})(typeof globalThis==='object'?globalThis:this);
