// Run locally with Node: node tests/r3-ui.test.js
const sourceScript = typeof script !== "undefined" ? script : require("node:fs").readFileSync(require("node:path").join(__dirname,"../index1.html"),"utf8").match(/<script>([\s\S]*?)<\/script>/)[1];
// Headless logic checks. Supply browser-like document stubs; not visual browser QA.
const nodes={};
function element(){return {textContent:'',innerHTML:'',value:'',style:{},dataset:{},hidden:false,disabled:false,classList:{toggle(){}},setAttribute(){},addEventListener(){},replaceChildren(){},append(){},showModal(){this.open=true},close(){this.open=false}}}
const document={querySelector:k=>nodes[k]??=element(),querySelectorAll:()=>[],createElement:element};
const assertions=`
const assert=(condition,message)=>{if(!condition)throw Error(message)};
assert(questions.length===0&&!$('#initial-state').hidden&&$('#cards').hidden&&$('#refill-panel').hidden,'Initial screen has no quiz');
$('#generate').onclick();assert(isGenerating&&!$('#loading-state').hidden&&questions.length===0,'Loading before generation');
$('#generate').onclick();assert(queuedCount()===1,'Repeated click does not queue twice');
flush();assert(!isGenerating&&questions.length===6&&$('#initial-state').hidden&&$('#loading-state').hidden,'First generation completes');
assert($('#play-quiz').disabled,'Play disabled without approvals');
questions[0].status='approved';render();const approvedSnapshot=getApprovedLiveQuiz();assert(approvedSnapshot.length===1&&!$('#play-quiz').disabled,'Only approved questions playable');
approvedSnapshot[0].q='Modified room copy';assert(questions[0].q!=='Modified room copy','Room snapshot isolated from editor');questions[0].status='pending';render();
const initial=JSON.stringify(questions);
selectedTopics=new Set(['Evaluation']);$('#generate').onclick();flush();assert($('#path-panel').dataset.kind==='low'&&JSON.stringify(questions)===initial,'Evaluation blocks generation');
selectedTopics=new Set(['Fine-tuning']);$('#generate').onclick();flush();assert($('#path-panel').dataset.kind==='blocked'&&JSON.stringify(questions)===initial,'No source blocks generation');
selectedTopics=new Set(['Tài chính']);$('#generate').onclick();flush();assert($('#path-message').textContent.includes('ngoài phạm vi'),'Scope refusal');
questions[0].status='approved';openEditor(0);$('#edit-option-1').value=$('#edit-option-0').value;$('#edit-form').onsubmit({preventDefault(){}});assert(questions[0].status==='approved'&&$('#edit-error').textContent,'Duplicate options rejected');
openEditor(0);$('#edit-question').value='<img src=x onerror=alert(1)>';$('#edit-form').onsubmit({preventDefault(){}});assert(questions[0].status==='pending'&&questions[0].edited,'Edit revokes approval');assert($('#cards').innerHTML.includes('&lt;img')&&!$('#cards').innerHTML.includes('<img'),'User edits escaped');assert(!refillPool().some(q=>q.q===bank[0].q),'Edited original excluded from refill');
const beforeCancel=JSON.stringify(questions);openEditor(0);$('#edit-question').value='cancelled';closeEditor();assert(JSON.stringify(questions)===beforeCancel,'Cancel preserves data');
questions[0].status='approved';questions[1].status='rejected';questions[2].status='rejected';render();count=1;selectedTopics=new Set(['Token']);$('#refill').onclick();assert(questions.filter(q=>q.status!=='rejected').length===6&&questions[0].status==='approved','Refill keeps original target and approvals');assert($('#path-panel').dataset.kind==='success','Refill recovery banner');
assert($('#cards').innerHTML.includes('Đáp án đúng:'),'Answers visible');
`;
const timers=[];
const schedule=(callback,delay)=>{if(delay===1400)timers.push(callback);return timers.length};
const flush=()=>{while(timers.length)timers.shift()()};
new Function('document','setTimeout','clearTimeout','innerWidth','flush','queuedCount',sourceScript+'\n'+assertions)(document,schedule,()=>{},1200,flush,()=>timers.length);
