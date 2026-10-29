/* Browser-only educational PixelAD baseline. NOT EfficientAD. */
(function(){
'use strict';
const SIDE=64, N=SIDE*SIDE, STORE='ai_vision_pixelad_v2';
const isValid=m=>m && m.engine==='PixelAD-v2' && Array.isArray(m.mean) && m.mean.length===N && Array.isArray(m.std) && m.std.length===N && Number.isFinite(m.review) && Number.isFinite(m.ng);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
function getCanvasFeatures(img){
 let c=document.createElement('canvas');c.width=SIDE;c.height=SIDE;const x=c.getContext('2d',{willReadFrequently:true});x.fillStyle='#fff';x.fillRect(0,0,SIDE,SIDE);x.drawImage(img,0,0,SIDE,SIDE);
 const data=x.getImageData(0,0,SIDE,SIDE).data, val=new Float32Array(N);for(let i=0;i<N;i++){const j=i*4;val[i]=(data[j]*.2126+data[j+1]*.7152+data[j+2]*.0722)/255}return val;
}
async function loadImage(src){return await new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(new Error('이미지 로드 실패: '+String(src).slice(0,80)));im.src=src})}
function train(features){if(!Array.isArray(features)||features.length<2)throw new Error('학습하려면 정상 이미지 2장 이상이 필요합니다.');
 const mean=new Float64Array(N),std=new Float64Array(N),num=features.length;
 for(const arr of features){if(arr.length!==N)throw new Error('잘못된 학습 입력입니다.');for(let i=0;i<N;i++)mean[i]+=arr[i]/num}
 for(const arr of features)for(let i=0;i<N;i++){const d=arr[i]-mean[i];std[i]+=d*d/num}
 const model={engine:'PixelAD-v2',size:SIDE,mean:Array.from(mean,x=>+x.toFixed(6)),std:Array.from(std,x=>+Math.sqrt(x).toFixed(6)),review:11,ng:23,samples:num,trainedAt:new Date().toISOString()};
 // Calibrate against normal training inputs only. Add a robust safety offset for controlled experiments.
 const scores=features.map(f=>infer(model,f).score).sort((a,b)=>a-b);
 const p95=scores[Math.min(num-1,Math.floor(num*.95))]||0;
 model.review=Math.round(clamp(p95*1.6+4,5,65));model.ng=Math.round(clamp(Math.max(model.review+9,p95*2.2+13),model.review+2,95));
 model.averageError=+(scores.reduce((a,b)=>a+b,0)/num).toFixed(2);return model;
}
function infer(model,feat){if(!isValid(model))throw new Error('유효한 학습 모델이 아닙니다.');if(feat.length!==N)throw new Error('이미지 크기 변환 오류');
 const map=new Float32Array(N),absDiff=new Float32Array(N),weighted=[];
 for(let i=0;i<N;i++){
   const reference=model.mean[i];const std=model.std[i];const dist=Math.abs(feat[i]-reference);
   const residual=Math.max(0,dist-(.016+Math.min(.045,std*1.2)));
   const weight=reference<.88?1:.2;
   const v=clamp(residual/.35,0,1)*weight;
   map[i]=v;absDiff[i]=dist;
   if(weight>.3)weighted.push(v);
 }
 weighted.sort((a,b)=>b-a);
 const n=Math.max(1,Math.floor(weighted.length*.065));let s=0;for(let i=0;i<n;i++)s+=weighted[i];
 const score=+(100*s/n).toFixed(2);
 return {engine:model.engine,score,verdict:score<model.review?'OK':score<model.ng?'REVIEW':'NG',map,review:model.review,ng:model.ng,meanDiff:+(absDiff.reduce((a,b)=>a+b,0)/N*100).toFixed(2)};
}
function readSaved(){try{const m=JSON.parse(localStorage.getItem(STORE)||'null');return isValid(m)?m:null}catch(_){return null}}
function save(m){if(!isValid(m))throw new Error('학습 모델의 필수 필드가 없습니다.');try{localStorage.setItem(STORE,JSON.stringify(m))}catch(e){console.warn('Storage failed:',e)}}
function scoreToHTML(v){return String(Number(v).toFixed(1))}
window.PixelAD={SIDE,N,isValid,loadImage,getCanvasFeatures,train,infer,readSaved,save,scoreToHTML,STORE};
})();
