/* Synthetic DOM smoke test for the embedded offline editor; no browser/network. */
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2],'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
let downloaded=null;
class Element {
  constructor(tag) {this.tag=tag;this.children=[];this.listeners={};this.value='';this.disabled=false;this.hidden=false;this.textContent='';this.className='';this.type='';}
  append(...nodes){this.children.push(...nodes);}
  addEventListener(name,cb){this.listeners[name]=cb;}
  click(){if(this.tag==='a') downloaded=this.href;else this.listeners.click?.();}
  remove(){}
}
const ids=Object.fromEntries(['tasks','error','summary','table-filter','export'].map(id=>[id,new Element(id==='export'?'button':'div')]));
ids['table-filter'].value='all';
const doc={getElementById:id=>ids[id],createElement:tag=>new Element(tag),body:new Element('body')};
let exported=null;
const url={createObjectURL(blob){exported=blob;return 'blob:synthetic';},revokeObjectURL(){}};
vm.runInNewContext(script,{document:doc,structuredClone,URL:url,Blob,setTimeout:()=>{},console},{timeout:5000});
assert.equal(ids.tasks.children.length,24);
const card=ids.tasks.children[0];
const selects=card.children.filter(e=>e.tag==='label').map(e=>e.children[1]);
assert.equal(selects.length,4);
const [status,reviewer,notes,confidence]=selects;
status.value='uncertain';status.listeners.input();
reviewer.value='Teste sintético';reviewer.listeners.input();
notes.value='Quadro sintético inconclusivo';notes.listeners.input();
confidence.value='0.4';confidence.listeners.input();
ids.export.click();
assert.equal(downloaded,'blob:synthetic');
assert.ok(exported);
exported.text().then(s=>{
  const data=JSON.parse(s);
  assert.equal(data.rows.length,24);
  assert.equal(data.rows[0].verdict,'uncertain');
  assert.equal(data.rows[0].visual_confidence,0.4);
  assert.equal(data.rows[1].verdict,'unreviewable');
  assert.equal(data.ready_for_equity_or_ev,false);
  if(process.argv[3]) fs.writeFileSync(process.argv[3],s);
  console.log('Node synthetic DOM: 24 rows, edited JSON valid structure, no math authority');
}).catch(e=>{console.error(e);process.exitCode=1});
