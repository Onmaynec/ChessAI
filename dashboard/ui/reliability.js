(function(root){
'use strict';
function delay(failures,active,hidden,modal){return hidden?15000:failures?Math.min(30000,2500*2**Math.min(failures,4)):modal?5000:active?2500:5000}
function gate(){let n=0;return {next:()=>++n,current:x=>x===n}}
function due(last,now,interval){return last==null||now-last>=interval}
const api={delay,gate,due};if(typeof module==='object'&&module.exports)module.exports=api;else root.LabReliability=api;
})(globalThis);
