
(async()=>{
  let config={};
  try{const res=await fetch('/site-config.json',{cache:'no-store'});if(res.ok)config=await res.json();}catch(e){console.info('온라인 연결 설정은 배포 후 적용됩니다.');}
  const setText=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=value;};
  const urlMap={'colab-link':config.colab_url,'streamlit-link':config.streamlit_url,'video-link':config.session02_video_url,'github-link':config.github_repository};
  if(config.github_repository && !config.colab_url && /^https:\/\/github\.com\/[^/]+\/[^/]+\/?$/.test(config.github_repository)){
    const clean=config.github_repository.replace(/\/$/,'');
    config.colab_url=`https://colab.research.google.com/github/${clean.slice('https://github.com/'.length)}/blob/main/colab/04_COLAB_연결용_안내.ipynb`;
    // Generated notebook is an instruction-only placeholder, not the original lesson 04 notebook.
    urlMap['colab-link']=config.colab_url;
  }
  for(const [id,url] of Object.entries(urlMap)){
    const el=document.getElementById(id);
    if(!el)continue;
    if(typeof url==='string'&& /^https:\/\//.test(url)){
      el.href=url;el.target='_blank';el.rel='noopener noreferrer';el.classList.remove('disabled');
      if(id==='github-link')setText('github-status','연결됨');
      if(id==='streamlit-link')setText('streamlit-status','외부 앱 열기');
      if(id==='colab-link')setText('colab-status',config.colab_url.includes('/04_COLAB_연결용_안내.ipynb')?'연결용 안내 노트북 열기':'원본 노트북 열기');
    }else{
      el.removeAttribute('href');el.setAttribute('aria-disabled','true');el.classList.add('disabled');
    }
  }
  if(typeof config.github_repository==='string' && /^https:\/\/github\.com\/[^/]+\/[^/]+\/?$/.test(config.github_repository)){
    const github=config.github_repository.replace(/\/$/,'');
    document.querySelectorAll('[data-repo-path]').forEach(el=>{
      el.href=github+'/tree/main/'+el.dataset.repoPath;
      el.target='_blank';el.rel='noopener noreferrer';
      el.classList.remove('disabled');el.removeAttribute('aria-disabled');
    });
  }
  const base=`${location.origin}`;
  for(const id of ['02','03','04','05'])setText(`link-${id}`,`${base}/${id}/`);
  const allLinks=document.getElementById('all-lesson-links');
  if(allLinks)allLinks.textContent=['02','03','04','05'].map(id=>`${id}차시: ${base}/${id}/`).join('\n');
  const buttons=document.querySelectorAll('[data-inspection-filter]');
  if(buttons.length){
    const segments={total:[20,38,54],good:[20,24,4],bad:[0,14,50]};
    const names={total:'전체 112건',good:'정상 GOOD 48건',bad:'결함 BAD 64건'};
    function redraw(key){const vals=segments[key],total=vals.reduce((a,b)=>a+b,0);
      setText('breakdown-label',names[key]);
      ['ok','review','ng'].forEach((id,i)=>{setText(`value-${id}`,String(vals[i]));const node=document.getElementById(`bar-${id}`);if(node){node.style.width=(100*vals[i]/total)+'%';node.title=`${id.toUpperCase()} ${vals[i]}건`;}});
      buttons.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.inspectionFilter===key)));
    }
    buttons.forEach(b=>b.addEventListener('click',()=>redraw(b.dataset.inspectionFilter)));
    redraw('total');
  }
})();
