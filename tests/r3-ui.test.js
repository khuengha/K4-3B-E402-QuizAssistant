// UI/API contract checks; no network requests or external AI calls.
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../index1.html'), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const nodes = {};
function element() { return {textContent:'',innerHTML:'',value:'all',children:[],style:{},dataset:{},hidden:false,disabled:false,
  classList:{toggle(){},remove(){}},setAttribute(){},addEventListener(){},replaceChildren(){this.children=[];},
  append(...items){this.children.push(...items);},showModal(){this.open=true;},close(){this.open=false;}}; }
const document = {querySelector:k=>nodes[k]??=element(), querySelectorAll:()=>[], createElement:element};
const calls=[];
let fail=false, nextQuestions=[];
const sample=(id)=>({concept_id:id,graph_id:'original',source_file:'lesson.md',source_doc_id:'doc',
 q:'Question '+id,a:['One','Two','Three','Four'],correct:0,topic:'AI',level:'Dễ',explain:'Evidence',page:null,code:'TXT-001',quote:'Evidence'});
async function fetch(path, options={}) {
 const payload=options.body?JSON.parse(options.body):null; calls.push({path,payload});
 if(path==='/api/docs'||path==='/api/merges')return {ok:true,json:async()=>[]};
 if(path==='/api/quiz')return {ok:!fail,json:async()=>fail?{detail:'AI unavailable'}:{questions:nextQuestions,n_pool:10}};
 throw Error('Unexpected request '+path);
}
const assertions=`
const assert=(ok,message)=>{if(!ok)throw Error(message)};
await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
activeGraphId='original'; count=2; next([sample('c1'),sample('c2')]);
const pending=generateQuiz(); assert(isGenerating,'Loading state'); await generateQuiz(); await pending;
assert(calls.filter(c=>c.path==='/api/quiz').length===1,'No duplicate generation');
assert(questions.length===2 && questions.every(q=>q.status==='pending'),'AI questions require approval');
questions[0].status='approved'; render();
const approved=getApprovedLiveQuiz(); approved[0].q='changed';
assert(questions[0].q!=='changed'&&!$('#play-quiz').disabled,'Approved snapshot isolated');
openEditor(0); $('#edit-option-1').value=$('#edit-option-0').value;
$('#edit-form').onsubmit({preventDefault(){}}); assert(questions[0].status==='approved'&&$('#edit-error').textContent,'Reject duplicate answers');
openEditor(0); $('#edit-question').value='<img src=x onerror=alert(1)>';
$('#edit-form').onsubmit({preventDefault(){}});
assert(questions[0].status==='pending'&&questions[0].edited,'Editing revokes approval');
assert($('#cards').innerHTML.includes('&lt;img')&&!$('#cards').innerHTML.includes('<img'),'Escape user text');
questions[0].status='approved'; questions[1].status='rejected'; activeGraphId='another'; count=8;
next([{...sample('c2'), q:'Another question on c2'}]); await generateQuiz(true);
const request=calls.filter(c=>c.path==='/api/quiz').at(-1).payload;
assert(request.graph_id==='original'&&request.count===1,'Refill preserves generation graph and target');
assert(!request.exclude_concept_ids&&request.existing_questions.length===2,'Refill sends questions, not concept exclusion');
assert(request.existing_questions[1].status==='rejected'&&request.existing_questions[0].original_q==='Question c1','Keep rejected and original text for deduplication');
assert(questions[0].status==='approved'&&questions[2].status==='pending','Keep approvals during refill');
const previous=JSON.stringify(questions); next([]); await generateQuiz();
assert(JSON.stringify(questions)===previous&&$('#path-panel').dataset.kind==='low'&&!isGenerating,'Zero questions preserves quiz and shows warning');
questions[2].status='rejected'; const beforeRefill=JSON.stringify(questions); await generateQuiz(true);
assert(JSON.stringify(questions)===beforeRefill&&$('#path-panel').dataset.kind==='low','Empty refill preserves approvals');
setFail(true); await generateQuiz();
assert(JSON.stringify(questions)===beforeRefill&&!isGenerating,'Failure preserves quiz and clears loading');
assert($('#path-message').textContent.includes('AI unavailable'),'API error is visible');
assert(sourceLabel(questions[0]).includes('TXT-001')&&!sourceLabel(questions[0]).includes('null'),'Transcript source label');
`;
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('document','fetch','setTimeout','clearTimeout','innerWidth','AbortController','calls','sample','next','setFail',source+'\n'+assertions)(
 document,fetch,()=>1,()=>{},1200,AbortController,calls,sample,value=>nextQuestions=value,value=>fail=value
).then(()=>console.log('UI integration checks passed')).catch(e=>{console.error(e);process.exitCode=1;});
