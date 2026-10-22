(()=>{
 const windowEl=document.querySelector('.review-window');
 const track=document.querySelector('.review-track');
 const group=document.querySelector('.review-group');
 const control=document.querySelector('#review-motion-toggle');
 if(!windowEl||!track||!group||!control)return;
 const copy=group.cloneNode(true);copy.setAttribute('aria-hidden','true');copy.inert=true;track.appendChild(copy);
 const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
 let paused=false,hover=false,focused=false,visible=false,holdUntil=0,last=0,loopWidth=0,frame=0,offset=0;
 const measure=()=>{loopWidth=group.getBoundingClientRect().width;};
 const resize=new ResizeObserver(measure);resize.observe(group);measure();
 const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;},{threshold:.05});observer.observe(windowEl);
 control.addEventListener('click',()=>{paused=!paused;control.setAttribute('aria-pressed',String(paused));control.textContent=paused?'Resume motion':'Pause motion';});
 windowEl.addEventListener('mouseenter',()=>{hover=true;});windowEl.addEventListener('mouseleave',()=>{hover=false;});
 windowEl.addEventListener('focusin',()=>{focused=true;});windowEl.addEventListener('focusout',()=>{focused=false;});
 const hold=()=>{holdUntil=performance.now()+3500;};
 windowEl.addEventListener('pointerdown',hold,{passive:true});windowEl.addEventListener('pointerup',hold,{passive:true});windowEl.addEventListener('touchmove',hold,{passive:true});windowEl.addEventListener('wheel',hold,{passive:true});
 function animate(now){const delta=last?Math.min(now-last,50):0;last=now;
  if(!reduced.matches&&!paused&&!hover&&!focused&&visible&&!document.hidden&&now>holdUntil&&loopWidth>0){
   offset+=delta*.024;if(offset>=loopWidth)offset-=loopWidth;windowEl.scrollLeft=offset;
  }else{offset=windowEl.scrollLeft;}
  frame=requestAnimationFrame(animate);
 }
 frame=requestAnimationFrame(animate);
 window.addEventListener('pagehide',()=>{cancelAnimationFrame(frame);resize.disconnect();observer.disconnect();},{once:true});
})();
