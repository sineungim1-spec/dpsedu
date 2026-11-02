/* Stage 3 demo adapter. Replace the internals of these functions with Supabase in Stage 4.
   This file NEVER stores passwords and its client-side roles are NOT secure authorization. */
(function(){
 const SESSION_KEY='dpsedu_demo_session_v1', PROFILE_KEY='dpsedu_demo_profile_v1', ACTIVITY_KEY='dpsedu_demo_activities_v1', CONTENT_KEY='dpsedu_demo_contents_v1';
 const DEMO={user:{id:'demo-student',email:'student@dpsedu.local',displayName:'체험 학생',role:'user'},admin:{id:'demo-admin',email:'admin@dpsedu.local',displayName:'체험 관리자',role:'admin'}};
 const read=(k,fallback)=>{try{return JSON.parse(localStorage.getItem(k))??fallback}catch{return fallback}};
 const write=(k,v)=>localStorage.setItem(k,JSON.stringify(v));
 function getCurrentUser(){try{return JSON.parse(sessionStorage.getItem(SESSION_KEY))}catch{return null}}
 function getUserRole(){return getCurrentUser()?.role||'guest'}
 function getUserProfile(){return getCurrentUser()}
 async function signUpUser({displayName,email}) {
   const profile={id:'trial-'+Date.now(),email,displayName,role:'user',demo:true};
   sessionStorage.setItem(SESSION_KEY,JSON.stringify(profile));
   sessionStorage.setItem(PROFILE_KEY,JSON.stringify(profile));
   return {user:profile,mode:'demo'};
 }
 async function signInUser({email}) {
   const key=email.toLowerCase()==='admin@dpsedu.local'?'admin':email.toLowerCase()==='student@dpsedu.local'?'user':null;
   if(!key) throw new Error('체험 계정 이메일을 사용하거나 회원가입 체험을 진행해 주세요.');
   const user={...DEMO[key],demo:true};
   sessionStorage.setItem(SESSION_KEY,JSON.stringify(user));
   return {user,mode:'demo'};
 }
 async function signOutUser(){sessionStorage.removeItem(SESSION_KEY);sessionStorage.removeItem(PROFILE_KEY);return true}
 async function getActivityRecords(){const u=getCurrentUser();return read(ACTIVITY_KEY,[]).filter(x=>u?.role==='admin'||x.userId===u?.id)}
 async function saveActivityRecord(record){
   const u=getCurrentUser();if(!u)return null;
   const list=read(ACTIVITY_KEY,[]);
   const item={id:'act-'+Date.now()+'-'+Math.random().toString(16).slice(2,7),userId:u.id,email:u.email,displayName:u.displayName,createdAt:new Date().toISOString(),...record};
   list.unshift(item);write(ACTIVITY_KEY,list);return item;
 }
 async function updateActivityRecord(id,patch){const list=read(ACTIVITY_KEY,[]).map(x=>x.id===id?{...x,...patch}:x);write(ACTIVITY_KEY,list);return list.find(x=>x.id===id)||null}
 async function deleteActivityRecord(id){write(ACTIVITY_KEY,read(ACTIVITY_KEY,[]).filter(x=>x.id!==id));return true}
 async function getDashboardData(){
   const records=read(ACTIVITY_KEY,[]);
   return {userCount:3,activityCount:records.length,contents:read(CONTENT_KEY,[{id:'sim-01',title:'동력전달장치 가상 조립',type:'기계요소설계',status:'사용 중'},{id:'sim-02',title:'끼워맞춤 비교 실습',type:'기계요소설계',status:'준비 중'}]),users:[{id:'demo-admin',name:'체험 관리자',email:'admin@dpsedu.local',role:'관리자',status:'체험 계정'},{id:'demo-student',name:'체험 학생',email:'student@dpsedu.local',role:'일반 사용자',status:'체험 계정'},{id:'trial-example',name:'예시 학습자',email:'example@dpsedu.local',role:'일반 사용자',status:'샘플 데이터'}],records};
 }
 async function updateProfile({displayName}){const u=getCurrentUser();if(!u)throw new Error('로그인이 필요합니다.');const next={...u,displayName};sessionStorage.setItem(SESSION_KEY,JSON.stringify(next));sessionStorage.setItem(PROFILE_KEY,JSON.stringify(next));return next}
 function requireLogin(){const u=getCurrentUser();if(!u){location.href='login.html?next='+encodeURIComponent(location.pathname.split('/').pop()||'index.html');return null}return u}
 function requireAdmin(){const u=requireLogin();if(u&&u.role!=='admin'){alert('관리자 체험 계정으로 로그인해야 볼 수 있는 화면입니다.');location.href='index.html';return null}return u}
 window.DpsAuth={mode:'demo',signUpUser,signInUser,signOutUser,getCurrentUser,getUserRole,getUserProfile,getDashboardData,getActivityRecords,saveActivityRecord,updateActivityRecord,deleteActivityRecord,updateProfile,requireLogin,requireAdmin};
 document.addEventListener('DOMContentLoaded',()=>{
   const u=getCurrentUser();
   document.querySelectorAll('[data-user-label]').forEach(e=>e.textContent=u?u.displayName+' · '+(u.role==='admin'?'관리자 체험':'일반 사용자 체험'):'체험 모드');
   document.querySelectorAll('[data-admin-link]').forEach(e=>e.hidden=u?.role!=='admin');
   document.querySelectorAll('[data-logout]').forEach(e=>e.addEventListener('click',async()=>{await signOutUser();location.href='login.html'}));
 });
})();