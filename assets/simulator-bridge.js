/* The simulator remains usable without an account. Preview activity is saved only when a preview session exists. */
document.addEventListener('DOMContentLoaded',()=>{
 const auth=window.DpsAuth;
 window.addEventListener('dps:activity-record',async e=>{
  if(!auth?.getCurrentUser())return;
  try{await auth.saveActivityRecord(e.detail)}catch(err){console.warn('Preview activity was not saved:',err)}
 });
});