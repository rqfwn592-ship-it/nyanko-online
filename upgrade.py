from pathlib import Path
p=Path(__file__).parent
s=(p/'server.py').read_text()
# Race grapple and throw: authoritative server implementation.
s=s.replace("race_down=0,special=0,vx=0,vy=0,hit_by=None)","race_down=0,special=0,vx=0,vy=0,hit_by=None,carrying=None,carried_by=None,throw_flight=0)")
s=s.replace("  if self.event==0:\n   if kind=='dash'",'''  if self.event==0:
   if kind=='grab' and e['race_down']<=0 and e['stun']<=0:
    if e.get('carrying') is not None:
     target=self.entities[e['carrying']]
     e['carrying']=None
     target['carried_by']=None
     target['throw_flight']=.72
     target['stun']=1.10
     target['race_inv']=1.5
     target['progress']=max(0,e['progress']+e['face']*48)
     target['y']=e['y']
     target['hp']=max(0,target['hp']-19)
     self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':'grab-throw','target':target['id']})
    else:
     candidates=[t for t in self.entities.values() if t['id']!=cat and t.get('carried_by') is None and
          (t['race_down']>0 or t['stun']>.2) and abs(t['progress']-e['progress'])<36 and abs(t['y']-e['y'])<.65]
     if candidates:
      target=min(candidates,key=lambda t:abs(t['progress']-e['progress']))
      e['carrying']=target['id'];target['carried_by']=cat
      self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':'grab','target':target['id']})
   if kind=='dash' ''').replace("if kind=='dash'  and", "if kind=='dash' and")
s=s.replace("if kind=='jump' and e['race_down']<=0 and e['jump']<=0 and e['stun']<=0", "if kind=='jump' and e['race_down']<=0 and e['jump']<=0 and e['stun']<=0 and e.get('carried_by') is None")
s=s.replace("    if i in self.race_finish:continue\n    e['jump']", "    if i in self.race_finish:continue\n    e['throw_flight']=max(0,e.get('throw_flight',0)-dt)\n    e['jump']")
s=s.replace("    if e['race_down']>0:\n     e['race_down']", "    if e.get('carried_by') is not None:\n     carrier=self.entities[e['carried_by']]\n     e['progress']=carrier['progress']+carrier['face']*13;e['y']=carrier['y'];continue\n    if e['race_down']>0:\n     e['race_down']")
s=s.replace("    prev=e['progress'];e['progress']+=speed*dt", "    prev=e['progress'];e['progress']+=speed*dt\n    if e.get('carrying') is not None:\n     target=self.entities[e['carrying']];target['progress']=e['progress']+e['face']*13;target['y']=e['y']")
s=s.replace("     e['race_down']=2.4;e['stun']=2.4;e['skate']=0;e['weapon']=None", "     e['race_down']=2.4;e['stun']=2.4;e['skate']=0;e['weapon']=None\n     if e.get('carrying') is not None:\n      self.entities[e['carrying']]['carried_by']=None;e['carrying']=None")
# Expose clearer race events and visible notes; reinforce server cpu strength rule consistency.
s=s.replace("async def version(request):return web.json_response({'version':'0.16','name':'ニャンコ大運動会・通信と描画最適化'})","async def version(request):return web.json_response({'version':'0.17','name':'ニャンコ大運動会・通信アクション強化'})")
(p/'server.py').write_text(s)

h=(p/'static/index.html').read_text()
h=h.replace('ONLINE v0.16 描画・通信軽量版','ONLINE v0.17 操作・同期強化版')
# Keep 3 race actions but context-sensitive third button; long press to grab/throw
h=h.replace("state.entities?.[myCat()]?.weapon==='pan'?'throw':'dash'", "state.entities?.[myCat()]?.weapon==='pan'?'throw':state.entities?.[myCat()]?.carrying!=null?'grab':'dash'")
# Provide dedicated grab operation on long press of the third action in race (dash on regular tap)
needle="for(const [el,n] of [[act1,1],[act2,2],[act3,3]]){el.addEventListener('pointerdown',e=>{e.preventDefault();action(n)});el.addEventListener('contextmenu',e=>e.preventDefault())}"
replace="""let grabHold=null,thirdDownAt=0,thirdHeld=false;
for(const [el,n] of [[act1,1],[act2,2],[act3,3]]){
 el.addEventListener('pointerdown',e=>{
   e.preventDefault();
   if(n===3&&state?.phase==='play'&&state.event===0){
     thirdDownAt=performance.now();thirdHeld=false;
     grabHold=setTimeout(()=>{if(state?.phase==='play'&&state.event===0){thirdHeld=true;send({action:'input',kind:'grab'});sound(310,.12)}},430);
   }else action(n)
 });
 if(n===3){
   const release=()=>{clearTimeout(grabHold);if(state?.phase==='play'&&state.event===0&&!thirdHeld&&thirdDownAt){action(3)}thirdDownAt=0};
   el.addEventListener('pointerup',release);el.addEventListener('pointercancel',()=>{clearTimeout(grabHold);thirdDownAt=0});
 }
 el.addEventListener('contextmenu',e=>e.preventDefault());
}"""
assert needle in h
h=h.replace(needle,replace)
# Mention actions and state visually
h=h.replace("$('action3').textContent='投げる'", "$('action3').textContent='ダッシュ / 長押しつかむ'" )
# Add smooth visual spatial coordinates independent from authoritative state, reset on event/stage and hidden state.
needle="let lastFrameAt=0;function paint(now=0){requestAnimationFrame(paint);if(now-lastFrameAt<33)return;lastFrameAt=now;if(!state||state.phase!=='play'||document.hidden)return;const {event,entities}=state;"
replace="""const visualPositions=new Map();let visualIdentity='',lastVisualNow=0;
function smoothEntities(raw,now){
 const identity=`${state.code}:${state.event}:${state.stage}:${state.round}`;
 if(identity!==visualIdentity){visualIdentity=identity;visualPositions.clear();lastVisualNow=now}
 const dt=Math.min(.08,Math.max(0,(now-lastVisualNow)/1000));lastVisualNow=now;
 const alpha=1-Math.exp(-dt*17);
 const merged={};
 for(const [id,e] of Object.entries(raw)){
  const old=visualPositions.get(id)||{x:e.x,y:e.y,progress:e.progress};
  let cur={};for(const k of ['x','y','progress']){
   let a=Number(old[k]||0),b=Number(e[k]||0);
   // Never interpolate across a respawn or a stage transition.
   cur[k]=Math.abs(a-b)>170?b:a+(b-a)*alpha;
  }
  visualPositions.set(id,cur);merged[id]={...e,...cur};
 }
 return merged;
}
let lastFrameAt=0;function paint(now=0){requestAnimationFrame(paint);if(now-lastFrameAt<16.5)return;lastFrameAt=now;if(!state||state.phase!=='play'||document.hidden)return;const event=state.event,entities=smoothEntities(state.entities,now);"""
assert needle in h
h=h.replace(needle,replace)
# Add racers' grab/throw visuals
needle="if(e.race_down>0){ctx.font='bold 20px system-ui';ctx.fillStyle='#ffe07b';ctx.fillText('DOWN',obj.x,y-jump-w*.97-30)}"
replace="""if(e.race_down>0){ctx.font='bold 20px system-ui';ctx.fillStyle='#ffe07b';ctx.fillText('DOWN',obj.x,y-jump-w*.97-30)}
     if(e.carrying!=null){ctx.font='bold 18px system-ui';ctx.fillStyle='#ffdb70';ctx.fillText('つかみ中！',obj.x,y-jump-w*.97-38)}
     if(e.throw_flight>0){ctx.strokeStyle='#ffdf7c';ctx.lineWidth=6;ctx.beginPath();ctx.arc(obj.x,y-jump-28,42,0,Math.PI*1.7);ctx.stroke()}"""
assert needle in h
h=h.replace(needle,replace)
# Fix race speed animation priorEntities stale if used with smooth interpolation
# Inline labels show status better
(p/'static/index.html').write_text(h)
print('upgraded',len(s),len(h))
