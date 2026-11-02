/* DPS EDU Stage 3 adapter.
   No real authentication is performed in this stage.
   Preview sessions contain profile-only demo data; passwords are never stored.
   Replace these implementations with Supabase Auth + RLS in Stage 4. */
(function(){
 'use strict';
 const PREVIEW_KEY='dpsedu_preview_session_v2';
 const PENDING_KEY='dpsedu_signup_draft_v2';
 const ACTIVITY_KEY='dpsedu_preview_activity_v2';
 const CONTENT_KEY='dpsedu_preview_contents_v2';
 const SAMPLE_CONTENT=[
  {id:'content-simulator',title:'동력전달장치 가상 조립',type:'기계요소설계',status:'사용 중',sample:true},
  {id:'content-fit',title:'끼워맞춤 비교 학습',type:'기계요소설계',status:'준비 중',sample:true}
 ];
 const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback}catch{return fallback}};
 const write=(key,value)=>localStorage.setItem(key,JSON.stringify(value));
 const readSession=()=>{try{return JSON.parse(sessionStorage.getItem(PREVIEW_KEY))}catch{return null}};
 const current=()=>readSession();
 function setPreviewMode(kind,profile){
   const isAdmin=kind==='admin';
   const p=profile||{};
   const user={
    id:isAdmin?'preview-admin':'preview-member',
    email:isAdmin?'':String(p.email||''),
    displayName:isAdmin?'관리자 화면 미리보기':String(p.displayName||'화면 미리보기 사용자'),
    role:isAdmin?'admin-preview':'member-preview',
    preview:true
   };
   sessionStorage.setItem(PREVIEW_KEY,JSON.stringify(user));
   return user;
 }
 function getCurrentUser(){return current()}
 function getUserRole(){return current()?.role||'guest'}
 async function getUserProfile(){return current()}
 async function signUpUser({displayName,email,password}={}){
   // Deliberately no network request and no account creation in Stage 3.
   if(!displayName||!email||!password)throw new Error('이름, 이메일, 비밀번호를 확인해 주세요.');
   return {configured:false,created:false,message:'실제 회원가입은 4단계 Supabase 연결 후 활성화됩니다.'};
 }
 async function signInUser({email,password}={}){
   // Deliberately never authenticates against hard-coded or browser-stored credentials.
   if(!email||!password)throw new Error('이메일과 비밀번호를 입력해 주세요.');
   throw new Error('실제 로그인은 아직 연결되지 않았습니다. 4단계에서 Supabase Auth를 연결한 뒤 사용할 수 있습니다.');
 }
 async function signOutUser(){sessionStorage.removeItem(PREVIEW_KEY);return true}
 async function updateUserProfile({displayName}={}){
   const u=current();if(!u)throw new Error('화면 미리보기 모드가 아닙니다.');
   const next={...u,displayName:String(displayName||u.displayName).trim()};
   sessionStorage.setItem(PREVIEW_KEY,JSON.stringify(next));return next;
 }
 const updateProfile=updateUserProfile;
 async function getUsers(){return []}
 async function getActivityRecords(){
   const u=current();if(!u)return [];
   const rows=read(ACTIVITY_KEY,[]);
   return u.role==='admin-preview'?rows:rows.filter(r=>r.userId===u.id);
 }
 async function saveActivityRecord(record){
   const u=current();if(!u)return null;
   const rows=read(ACTIVITY_KEY,[]);
   const item={id:'preview-'+Date.now()+'-'+Math.random().toString(16).slice(2,7),userId:u.id,email:u.email,displayName:u.displayName,createdAt:new Date().toISOString(),...record,preview:true};
   rows.unshift(item);write(ACTIVITY_KEY,rows);return item;
 }
 async function updateActivityRecord(id,patch){
   const rows=read(ACTIVITY_KEY,[]).map(r=>r.id===id?{...r,...patch}:r);write(ACTIVITY_KEY,rows);return rows.find(r=>r.id===id)||null;
 }
 async function deleteActivityRecord(id){
   write(ACTIVITY_KEY,read(ACTIVITY_KEY,[]).filter(r=>r.id!==id));return true;
 }
 async function getDashboardData(){
   const records=read(ACTIVITY_KEY,[]);
   const contents=read(CONTENT_KEY,SAMPLE_CONTENT);
   return {userCount:0,activityCount:records.length,contents,users:[],records,sampleContent:contents.every(c=>c.sample)};
 }
 function requireLogin(){
   const u=current();
   if(!u){location.href='login.html?next='+encodeURIComponent(location.pathname.split('/').pop()||'index.html');return null}
   return u;
 }
 function requireAdmin(){
   const u=current();
   if(!u||u.role!=='admin-preview'){
     location.href='login.html?next=admin.html&preview=admin';return null;
   }
   return u;
 }
 function getSignupDraft(){try{return JSON.parse(sessionStorage.getItem(PENDING_KEY))}catch{return null}}
 function setSignupDraft(profile){sessionStorage.setItem(PENDING_KEY,JSON.stringify({displayName:String(profile.displayName||''),email:String(profile.email||'')}))}
 function clearSignupDraft(){sessionStorage.removeItem(PENDING_KEY)}
 document.addEventListener('DOMContentLoaded',()=>{
   const u=current();
   document.querySelectorAll('[data-user-label]').forEach(e=>e.textContent=u?u.displayName+' · 화면 미리보기':'인증 미연결');
   document.querySelectorAll('[data-admin-link]').forEach(e=>e.hidden=u?.role!=='admin-preview');
   document.querySelectorAll('[data-logout]').forEach(e=>e.addEventListener('click',async()=>{await signOutUser();location.href='index.html'}));
   const navState=document.getElementById('dpsNavState');
   if(navState)navState.textContent=u?u.displayName+' · 미리보기':'로그인 미연결';
   const navLogout=document.getElementById('dpsNavLogout');
   if(navLogout)navLogout.addEventListener('click',async()=>{await signOutUser();location.href='index.html'});
 });
 window.DpsAuth={
  mode:'preview-only',signUpUser,signInUser,signOutUser,getCurrentUser,getUserRole,getUserProfile,
  getUsers,updateUserProfile,updateProfile,getDashboardData,getActivityRecords,saveActivityRecord,
  updateActivityRecord,deleteActivityRecord,requireLogin,requireAdmin,setPreviewMode,
  getSignupDraft,setSignupDraft,clearSignupDraft
 };
})();