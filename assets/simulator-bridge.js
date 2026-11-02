document.addEventListener('DOMContentLoaded',()=>{
 if(!window.DpsAuth?.getCurrentUser()){
   location.href='login.html?next=simulator.html';
   return;
 }
 window.addEventListener('dps:activity-record',async e=>{
   if(!window.DpsAuth?.getCurrentUser())return;
   await window.DpsAuth.saveActivityRecord(e.detail);
 });
});