/* Local UI-only helpers. No changes to chess rules, training, or stored games. */
(function(root){
'use strict';
const files='abcdefgh';
const pieces='KQRBNPkqrbnp';
function parseFen(fen){
 if(typeof fen!=='string')throw Error('FEN отсутствует');
 const fields=fen.trim().split(/\s+/), ranks=fields[0].split('/');
 if(ranks.length!==8||!['w','b'].includes(fields[1]))throw Error('Некорректный FEN');
 return ranks.map(rank=>{const row=[];for(const ch of rank){if(/[1-8]/.test(ch))row.push(...Array(Number(ch)).fill('.'));else if(pieces.includes(ch))row.push(ch);else throw Error('Некорректная фигура FEN')}if(row.length!==8)throw Error('Некорректная длина ряда FEN');return row});
}
function squares(fen,flipped=false,move=''){
 const board=parseFen(fen),out=[];
 for(let i=0;i<8;i++)for(let k=0;k<8;k++){const r=flipped?7-i:i,f=flipped?7-k:k,square=files[f]+(8-r);out.push({square,piece:board[r][f],light:(r+f)%2===0,last:square===move.slice(0,2)||square===move.slice(2,4),file:i===7?files[f]:'',rank:k===0?String(8-r):''})}
 return out;
}
function validateTraining(p){
 const errors=[];
 if(p.parallel>p.games_per_iteration)errors.push(['c-parallel','Параллельных партий не должно быть больше числа партий за итерацию.']);
 if(p.arena_games%2!==0)errors.push(['c-arena','Для парной проверки требуется чётное число партий.']);
 return errors;
}
function filterCommands(commands,query){const terms=query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);return commands.filter(c=>terms.every(term=>(c.label+' '+(c.keywords||'')).toLocaleLowerCase().includes(term)))}
function stepIndex(index,delta,length){return Math.max(0,Math.min(length,index+delta))}
const api={parseFen,squares,validateTraining,filterCommands,stepIndex};
if(typeof module==='object'&&module.exports)module.exports=api;else root.LabUX=api;
})(typeof globalThis==='object'?globalThis:this);
