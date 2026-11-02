/* DPS EDU browser account adapter. Local-only; replace with server Auth + RLS for production. */
(function(){
'use strict';
const K={users:'dpsedu_users_v3',session:'dpsedu_session_v3',records:'dpsedu_records_v3',contents:'dpsedu_contents_v3',settings:'dpsedu_settings_v3'};
const read=(k,d=[])=>{try{return JSON.parse(localStorage.getItem(k))??d}catch{return d}};
const write=(k,v)=>localStorage.setItem(k,JSON.stringify(v));
const hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
const bytes=s=>new TextEncoder().encode(s);
async function derive(password,salt){if(!crypto?.subtle)throw Error('이 브라우저에서는 안전한 비밀번호 처리를 지원하지 않습니다. HTTPS 또는 localhost에서 접속해 주세요.');const key=await crypto.subtle.importKey('raw',bytes(password),'PBKDF2',false,['deriveBits']);return hex(await crypto.subtle.deriveBits({name:'PBKDF2',salt:Uint8Array.from(salt.match(/../g),x=>parseInt(x,16)),iterations:150000,hash:'SHA-256'},key,256))}
const salt=()=>hex(crypto.getRandomValues(new Uint8Array(16)));
function session(){try{return JSON.parse(sessionStorage.getItem(K.session))}catch{return null}}
function current(){const s=session();return s?read(K.users,[]).find(u=>u.id===s.userId)||null:null}
let readyPromise;function ready(){if(readyPromise)return readyPromise;readyPromise=(async()=>{let users=read(K.users,[]);if(!users.some(u=>u.username==='admin')){const s=salt();users.push({id:'admin-'+crypto.randomUUID(),username:'admin',name:'관리자',role:'admin',salt:s,passwordHash:await derive('1234',s),createdAt:new Date().toISOString()});write(K.users,users)}if(!localStorage.getItem(K.contents))write(K.contents,[{id:'simulator-main',title:'동력전달장치 가상 조립',subject:'기계요소설계',objective:'동력전달장치의 구성 부품과 조립 순서를 이해한다.',description:'부품 배치, 축 정렬, 끼워맞춤 및 조립 상태를 확인하는 실습입니다.',url:'simulator.html',visible:true,createdAt:new Date().toISOString()}]);})();return readyPromise;}
async function signUp({username,name,password}={}){await ready();username=String(username||'').trim().toLowerCase();name=String(name||'').trim();if(!/^[a-zA-Z0-9._-]{3,24}$/.test(username))throw Error('아이디는 영문·숫자 3~24자로 입력해 주세요.');if(!name)throw Error('이름을 입력해 주세요.');if(String(password||'').length<8)throw Error('비밀번호는 8자 이상이어야 합니다.');const users=read(K.users,[]);if(users.some(u=>u.username===username))throw Error('이미 사용 중인 아이디입니다.');const s=salt(),u={id:'user-'+crypto.randomUUID(),username,name,role:'user',salt:s,passwordHash:await derive(password,s),createdAt:new Date().toISOString()};users.push(u);write(K.users,users);return {id:u.id,username:u.username,name:u.name};}
async function signIn({username,password}={}){await ready();const u=read(K.users,[]).find(x=>x.username===String(username||'').trim().toLowerCase());if(!u||await derive(String(password||''),u.salt)!==u.passwordHash)throw Error('아이디 또는 비밀번호를 확인해 주세요.');sessionStorage.setItem(K.session,JSON.stringify({userId:u.id,at:Date.now()}));return publicUser(u)}
function publicUser(u){return u?{id:u.id,username:u.username,name:u.name,displayName:u.name,role:u.role,createdAt:u.createdAt}:null}
async function signOut(){sessionStorage.removeItem(K.session);return true}
function requireLogin(){const u=current();if(!u){location.href='login.html?next='+encodeURIComponent(location.pathname.split('/').pop()||'index.html');return null}return publicUser(u)}
function requireAdmin(){const u=current();if(!u||u.role!=='admin'){location.href='login.html?next=admin.html';return null}return publicUser(u)}
async function changePassword({currentPassword,newPassword}={}){const u=current();if(!u)throw Error('로그인이 필요합니다.');if(await derive(String(currentPassword||''),u.salt)!==u.passwordHash)throw Error('현재 비밀번호가 올바르지 않습니다.');if(String(newPassword||'').length<8)throw Error('새 비밀번호는 8자 이상이어야 합니다.');const s=salt();u.salt=s;u.passwordHash=await derive(newPassword,s);write(K.users,read(K.users,[]).map(x=>x.id===u.id?u:x));return true}
async function updateProfile({name}={}){const u=current();if(!u)throw Error('로그인이 필요합니다.');if(!String(name||'').trim())throw Error('이름을 입력해 주세요.');u.name=String(name).trim();write(K.users,read(K.users,[]).map(x=>x.id===u.id?u:x));return publicUser(u)}
async function getUsers(){return read(K.users,[]).map(publicUser)}
async function updateUser(id,patch){const u=read(K.users,[]),target=u.find(x=>x.id===id);if(!target)throw Error('회원을 찾을 수 없습니다.');if(target.role==='admin'&&patch.role!=='admin')throw Error('관리자 권한은 이 화면에서 변경할 수 없습니다.');if(patch.name)target.name=String(patch.name).trim();write(K.users,u);return publicUser(target)}
async function deleteUsers(ids){const me=current();const list=read(K.users,[]);if(ids.includes(me?.id))throw Error('현재 로그인한 계정은 삭제할 수 없습니다.');write(K.users,list.filter(u=>!ids.includes(u.id)||u.role==='admin'));const removed=ids.filter(id=>list.some(u=>u.id===id&&u.role!=='admin'));write(K.records,read(K.records,[]).filter(r=>!removed.includes(r.userId)));return removed.length}
async function getRecords(){const u=current(),rows=read(K.records,[]);return u?.role==='admin'?rows:rows.filter(r=>r.userId===u?.id)}
async function saveRecord(record){const u=current();if(!u)return null;const item={id:'record-'+crypto.randomUUID(),userId:u.id,username:u.username,displayName:u.name,createdAt:new Date().toISOString(),...record};const rows=read(K.records,[]);rows.unshift(item);write(K.records,rows);return item}
async function updateRecord(id,patch){const rows=read(K.records,[]).map(r=>r.id===id?{...r,...patch}:r);write(K.records,rows);return rows.find(r=>r.id===id)||null}
async function deleteRecord(id){write(K.records,read(K.records,[]).filter(r=>r.id!==id));return true}
async function deleteRecords(ids){write(K.records,read(K.records,[]).filter(r=>!ids.includes(r.id)));return true}
async function getContents(){return read(K.contents,[])}
async function saveContent(c){const a=read(K.contents,[]),i=a.findIndex(x=>x.id===c.id);if(i<0)a.push({...c,id:c.id||'content-'+crypto.randomUUID(),createdAt:new Date().toISOString()});else a[i]={...a[i],...c};write(K.contents,a);return a}
async function deleteContents(ids){write(K.contents,read(K.contents,[]).filter(c=>!ids.includes(c.id)));return true}
async function getDashboardData(){const [users,records,contents]=await Promise.all([getUsers(),getRecords(),getContents()]);return {userCount:users.length,activityCount:records.length,contentCount:contents.length,users,records,contents}}
async function updateSettings(patch){write(K.settings,{...read(K.settings,{}),...patch});return read(K.settings,{})}
function getSettings(){return read(K.settings,{programName:'DPS EDU',homePage:'index.html'})}
document.addEventListener('DOMContentLoaded',()=>{const u=publicUser(current());document.querySelectorAll('[data-user-label]').forEach(e=>e.textContent=u?u.name+' · '+u.username:'');document.querySelectorAll('[data-logout]').forEach(e=>e.addEventListener('click',async()=>{await signOut();location.href='login.html'}));});
window.DpsAuth={ready,signUp,signIn,signOut,getCurrentUser:()=>publicUser(current()),getUserRole:()=>current()?.role||'guest',getUserProfile:async()=>publicUser(current()),requireLogin,requireAdmin,changePassword,updateProfile,getUsers,updateUser,deleteUsers,getRecords,saveRecord,updateRecord,deleteRecord,deleteRecords,getContents,saveContent,deleteContents,getDashboardData,getSettings,updateSettings,saveActivityRecord:saveRecord,getActivityRecords:getRecords,deleteActivityRecord:deleteRecord};
ready().catch(e=>console.error(e));
})();