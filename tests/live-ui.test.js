// Run: node tests/live-ui.test.js. DOM stubs test rendering, not browser layout.
const source = typeof liveSource !== 'undefined' ? liveSource : require('node:fs').readFileSync(require('node:path').join(__dirname,'../live.js'),'utf8');
const nodes = new Map();
function element(){return {hidden:false,disabled:false,dataset:{},tagName:'SECTION',style:{},textContent:'',innerHTML:'',className:'',
 classList:{add(){},remove(){},toggle(){}},append(){},setAttribute(){},addEventListener(){},focus(){},contains(){return false},
 querySelector(selector){return get(selector)},querySelectorAll(){return []},parentElement:{classList:{toggle(){}}}};}
function get(selector){if(!nodes.has(selector))nodes.set(selector,element());return nodes.get(selector);}
let root;
const body=element();body.dataset={};body.children=[];body.append=node=>{root=node;body.children.push(node)};
const document={body,activeElement:element(),querySelector:get,createElement:element};
const storage={getItem(){return null},setItem(){},removeItem(){}};
const hooks={};
const instrumented=source.replace(/\}\)\(\);\s*$/, 'Object.assign(testHooks,{accept,setup,joinScreen});\n})();');
new Function('document','location','sessionStorage','localStorage','getApprovedLiveQuiz','testHooks','URL',instrumented)(document,
 {protocol:'http:',href:'http://localhost:8000/index1.html',hostname:'localhost'},storage,storage,()=>[{status:'approved'}],hooks,typeof URL!=='undefined'?URL:class {constructor(path){this.href='http://localhost:8000/'+path}});
const assert=(ok,message)=>{if(!ok)throw Error(message)};
hooks.setup();assert(root.innerHTML.includes('1 câu đã duyệt'),'Setup uses approved snapshot');assert(root.innerHTML.includes('id="live-capacity"')&&root.innerHTML.includes('max="100"'),'Capacity setup');
hooks.joinScreen('123456');assert(root.innerHTML.includes('value="123456"')&&root.innerHTML.includes('live-name'),'Join with PIN and name');
const players=[{id:'a',name:'<img src=x>',score:0,correct:0,wrong:0,skipped:0,rank:1,weakTopics:[]}];
const base={pin:'123456',title:'Demo',role:'host',phase:'lobby',seq:0,round:1,duration:30,serverTime:Date.now(),deadline:null,questionCount:1,maxPlayers:1,current:null,players,me:null,myAnswer:null,answerCount:0,report:null};
hooks.accept(base);assert(root.innerHTML.includes('live-link')&&root.innerHTML.includes('Start Quiz'),'Host lobby controls');assert(root.innerHTML.includes('1 / 1 người')&&root.innerHTML.includes('Đã đủ chỗ'),'Full lobby indication');assert(root.innerHTML.includes('&lt;img src=x&gt;')&&!root.innerHTML.includes('<img src=x>'),'Names escaped');
const current={index:0,text:'Token là gì?',options:['Đơn vị văn bản','Tốc độ học','Bộ dữ liệu','Tên mô hình'],topic:'Token',difficulty:'Dễ'};
hooks.accept({...base,phase:'question',seq:1,current,deadline:Date.now()+30000});assert(root.innerHTML.includes('live-seconds')&&!root.innerHTML.includes('live-explanation'),'Question countdown without reveal');
hooks.accept({...base,role:'player',phase:'question',seq:1,current,me:players[0],deadline:Date.now()+30000});assert(!root.innerHTML.includes('data-live="reveal"'),'Player has no host controls');assert(root.innerHTML.includes('data-choice="0"'),'Player answer controls');
hooks.accept({...base,role:'player',phase:'question',seq:1,current,me:players[0],myAnswer:2,answerCount:1,deadline:Date.now()+30000});assert(root.innerHTML.includes('is-selected')&&root.innerHTML.includes('is-unselected')&&root.innerHTML.includes('ĐÃ CHỌN')&&root.innerHTML.includes('aria-pressed="true"'),'Visible selected choice');assert(!root.innerHTML.includes('is-correct')&&!root.innerHTML.includes('live-explanation'),'Selection does not reveal correctness');
const finalPlayers=[{...players[0],score:1000,correct:1}];
const report={scored:1,questionCount:1,players:finalPlayers,topics:[{topic:'Token',wrong:0,skipped:0,total:1}],breakdown:[]};
const revealed={...current,correct:0,explanation:'Một đơn vị văn bản.',source:{slide:12,transcript:'T03-045'}};
hooks.accept({...base,phase:'reveal',seq:2,current:revealed,report,players:finalPlayers,answerCount:1});assert(root.innerHTML.includes('is-correct')&&root.innerHTML.includes('T03-045')&&root.innerHTML.includes('Leaderboard tạm thời'),'Reveal and leaderboard');
hooks.accept({...base,phase:'finished',seq:3,current:revealed,report,players:finalPlayers,answerCount:1});assert(root.innerHTML.includes('Bảng xếp hạng cuối cùng')&&root.innerHTML.includes('Kết quả tổng hợp')&&root.innerHTML.includes('Chơi lại cùng bộ quiz'),'Final report and replay');
const finalHTML=root.innerHTML;
hooks.accept({...base,phase:'question',seq:1,current,deadline:Date.now()+30000});assert(root.innerHTML===finalHTML,'Ignore stale polling response');
