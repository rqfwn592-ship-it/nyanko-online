import asyncio, json, os, random, secrets, time, math
from pathlib import Path
from aiohttp import web, WSMsgType
BASE=Path(__file__).parent
NAMES=['まるねこ','でぶねこ','ダックス','もふねこ']
POINTS=[10,6,3,1]
rooms={}
class Room:
 def __init__(self,code):
  self.code=code;self.clients={};self.phase='lobby';self.event=0;self.stage=1;self.elapsed=0;self.scores=[0]*4;self.history=[];self.players=[];self.cpu_ids=[];self.entities={};self.inputs={};self.announced=0;self.round=1;self.duel=[];self.tug_games=[];self.tug_progress=0;self.cpu_tug_winner=None;self.cpu_tug_loser=None;self.race_times={i:[] for i in range(4)};self.result_order=[];self.end_time=0;self.last_action={};self.items=[];self.obstacles=[];self.stage_seed=0;self.fx=[];self.race_finish={};self.projectiles=[];self.race_hits={};self.current_misses={};self.race_starts={};self.race_attacks={};self.tug_notes=[];self.tug_judged={};self.tug_last_hit={};self.tug_combo={}
 def state(self):
  return dict(type='state',code=self.code,phase=self.phase,event=self.event,stage=self.stage,elapsed=round(self.elapsed,1),round=self.round,
   peers=[{'slot':i,'cat':p['cat'],'ready':p['ready'],'connected':not p['ws'].closed} for i,p in self.clients.items()],
   names=NAMES,entities=self.entities,scores=(self.scores if self.phase=='final' else None),history=(self.history if self.phase=='final' else []),
   order=self.result_order if self.phase in ('results','final') else [],duel=self.duel,tug_games=self.tug_games,tug_progress=self.tug_progress,
   messages=self.announced,items=self.items,obstacles=self.obstacles,fx=self.fx[-12:],projectiles=self.projectiles,race_hits=self.race_hits,race_attacks=self.race_attacks,race_times=self.race_times if self.phase=='results' and self.event==0 else None,tug_notes=(self.tug_notes if self.phase=='play' and self.event==2 else []),tug_combo=self.tug_combo)
 async def broadcast(self,obj=None):
  if obj is None:obj=self.state()
  raw=json.dumps(obj,ensure_ascii=False)
  for peer in list(self.clients.values()):
   try:await peer['ws'].send_str(raw)
   except:pass
 def make_tug_chart(self):
  # Server-owned schedule: both phones display the same beats and cannot judge one note twice.
  rng=random.Random(f'{self.code}:{self.round}:tug')
  notes=[];at=2.0;nid=0
  while at<35:
   notes.append({'id':nid,'at':round(at,3)})
   nid+=1;at+=.89*rng.choice([.78,.88,1.,1.,1.05,1.1,1.17])
  self.tug_notes=notes
  self.tug_judged={i:set() for i in self.duel}
  self.tug_last_hit={}
  self.tug_combo={i:0 for i in self.duel}
 def in_arena(self,e):
  # Coordinates in the 1000x560 game screen. Lower/upper trapezoid boundaries follow the visible platform.
  y=e['y']+75
  if not 165<=y<=468:return False
  fraction=(y-165)/(468-165)
  lo=235+(80-235)*fraction;hi=765+(920-765)*fraction
  return lo<=e['x']<=hi
 def battle_drop(self,cat,attacker=None,is_ko=False):
  e=self.entities[cat]
  if e['respawn']>0:return
  if is_ko:
   e['pts']-=3;e['ko']+=1;kind='ko'
  else:
   e['outs']+=1;kind='out'
   if attacker is not None and attacker!=cat:
    self.entities[attacker]['pts']+=3
  self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':kind})
  e.update(respawn=1.9,hp=100,stun=0,inv=2,weapon=None,shield=0,jump=0,vx=0,vy=0,hit_by=None)
 def battle_attack(self,cat,special=False,source='human'):
  e=self.entities[cat]
  if e['respawn']>0 or e['stun']>0 or e['special']>0:return False
  now=time.monotonic();key=(cat,'special' if special else 'punch');delay=1.8 if special else .27
  if now-self.last_action.get(key,0)<delay:return False
  if special and e['charge']<100:return False
  self.last_action[key]=now
  if special:
   e['charge']=0;e['special']=[.72,.85,.74,3.2][cat]
   self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':['headbutt','slaps','whirl','feign'][cat]})
   if cat==3:e['inv']=3.4;e['shield']=3.4;return True
  else:self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':'punch'})
  # All targets are checked in front of the actor. Dachshund spin hits every direction.
  reach=([122,157,147,0][cat] if special else 82)
  targets=[]
  for t in self.entities.values():
   if t['id']==cat or t['respawn']>0 or t['inv']>0 or t['shield']>0:continue
   dx=t['x']-e['x'];dy=abs(t['y']-e['y'])
   facing=abs(dx)<reach if special and cat==2 else (-25<dx*e['face']<reach)
   if facing and dy<(100 if special else 67):targets.append(t)
  for t in targets[:(4 if special else 1)]:
   damage=([36,40,30,0][cat] if special else 13)*([1.08,1.30,1.10,.85][cat])
   force=([650,940,715,0][cat] if special else 310)
   direction=(1 if t['x']>=e['x'] else -1) if special and cat==2 else e['face']
   t['hp']-=damage;t['stun']=.30;t['inv']=.43
   t['vx']=direction*force;t['vy']=(1 if t['y']>=e['y'] else -1)*(235 if special else 100)
   t['hit_by']=cat
   self.fx.append({'t':round(self.elapsed,2),'id':t['id'],'kind':'hit','damage':round(damage,1),'from':cat})
   if t['hp']<=0:self.battle_drop(t['id'],cat,True)
  return True
 def reset_entities(self):
  self.elapsed=0;self.inputs={};self.entities={};self.last_action={};self.fx=[];self.race_finish={}
  for i in range(4):
   self.entities[i]=dict(id=i,x=350+(i%2)*300,y=165+(i//2)*135,hp=100,pts=0,ko=0,outs=0,charge=75,stun=0,inv=0,face=1,respawn=0,progress=0,energy=0,notes=0,skate=0,score=0,weapon=None,z=0,jump=0,shield=0,race_inv=0,banana_slow=0,race_down=0,special=0,vx=0,vy=0,hit_by=None)
  self.items=[];self.obstacles=[];self.projectiles=[];self.race_hits={};self.race_attacks={}
  if self.event==0:
   for i in range(4):self.entities[i]['y']=i
   rng=random.Random(self.code+'-'+str(self.stage));self.obstacles=[{'x':x,'lane':rng.randrange(4),'kind':rng.choice(['box','cone','banana','hurdle','puddle'])} for x in range(85,750,43 if self.stage==5 else 95)]
   if self.stage<5:self.items=[{'x':rng.randrange(165,440),'lane':rng.randrange(4),'kind':'skate','taken':False}]
   for j in range(3):
    self.items.append({'x':rng.randrange(115,670),'lane':rng.randrange(4),'kind':rng.choice(['pan','fish']),'taken':False})
  if self.event==1:
   rng=random.Random(self.code+'battle');self.items=[{'x':rng.randrange(250,750),'y':rng.randrange(165,405),'kind':rng.choice(['fish','bomb']),'taken':False} for _ in range(7)]
 def start(self):
  self.players=[p['cat'] for p in self.clients.values() if p['cat'] is not None]
  self.cpu_ids=[i for i in range(4) if i not in self.players]
  self.phase='play';self.event=0;self.stage=1;self.round=1;self.scores=[0]*4;self.history=[];self.race_times={i:[] for i in range(4)}
  self.reset_entities()
 def next_event(self):
  if self.event>=2:self.phase='final';self.result_order=sorted(range(4),key=lambda i:(-self.scores[i],i));return
  self.event+=1;self.stage=1;self.round=1;self.reset_entities();self.phase='play'
  if self.event==2:
   a,b=[p['cat'] for p in self.clients.values()];self.duel=[a,b];self.tug_games=[];self.tug_progress=0;self.cpu_tug_winner=None;self.cpu_tug_loser=None;self.make_tug_chart()
 def finish_event(self,order):
  self.result_order=order[:]
  for i,cat in enumerate(order):self.scores[cat]+=POINTS[i]
  self.history.append(dict(event=self.event,order=order[:]))
  self.phase='results';self.end_time=time.monotonic()
 def apply(self,slot,kind,detail=None):
  if self.phase!='play':return
  cat=self.clients[slot]['cat'];e=self.entities[cat]
  if kind=='move':
   if not isinstance(detail,dict):return
   self.inputs[cat]={'x':max(-1,min(1,float(detail.get('x',0)))),'y':max(-1,min(1,float(detail.get('y',0))))}
  if self.event==0:
   if kind=='dash' and e['race_down']<=0 and e['energy']>=20 and e['stun']<=0:e['progress']+=22;e['energy']-=20;e['shield']=max(e['shield'],.25);self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':'dash'})
   if kind=='punch' and e['race_down']<=0 and e['stun']<=0:
    now=time.monotonic()
    if now-self.last_action.get((cat,'race_punch'),0)>=.34:
     self.last_action[(cat,'race_punch')]=now;self.race_attacks[cat]=round(self.elapsed,2);self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':'punch'})
     for target in self.entities.values():
      if target['id']!=cat and target['stun']<=0 and target['shield']<=0 and -10<(target['progress']-e['progress'])*e['face']<58 and abs(target['y']-e['y'])<.65 and target['race_inv']<=0 and target['race_down']<=0:
       target['stun']=.48;target['race_inv']=.52;target['progress']=max(0,target['progress']+e['face']*11);target['hp']=max(0,target['hp']-8);self.fx.append({'t':round(self.elapsed,2),'id':target['id'],'kind':'hit'});break
   if kind=='throw' and e['race_down']<=0 and e['weapon']=='pan':
    e['weapon']=None;self.projectiles.append({'owner':cat,'x':round(e['progress'],1),'y':round(e['y'],2),'vx':390*e['face'],'life':.9,'kind':'pan'});self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':'throw'})
   if kind=='jump' and e['race_down']<=0 and e['jump']<=0 and e['stun']<=0:e['jump']=.90;e['energy']=min(100,e['energy']+5);self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':'jump'})
   if kind=='dash' and e['energy']<20 and e['skate']<=0:pass
  elif self.event==1:
   if kind in ('punch','special'):self.battle_attack(cat,kind=='special')
   if kind=='jump':e['jump']=.65;e['inv']=max(e['inv'],.22)
   if kind=='throw' and e['weapon']=='bomb':
    e['weapon']=None;self.fx.append({'t':round(self.elapsed,1),'id':cat,'kind':'bomb'})
    for target in self.entities.values():
     if target['id']!=cat and target['respawn']<=0 and abs(target['x']-e['x'])<215 and abs(target['y']-e['y'])<115:
      target['hp']-=26;target['vx']=(1 if target['x']>=e['x'] else -1)*570;target['vy']=(1 if target['y']>=e['y'] else -1)*160;target['hit_by']=cat;target['stun']=.4;target['inv']=.6
      if target['hp']<=0:self.battle_drop(target['id'],cat,True)
      # Knockback is now resolved each server tick at the actual arena edge.
  elif self.event==2 and cat in self.duel:
   if kind=='mash':
    now=time.monotonic();key=(cat,'mash')
    if now-self.last_action.get(key,0)>=.065:
     e['energy']=min(100,e['energy']+4.4);self.last_action[key]=now
   if kind=='rhythm':
    now=time.monotonic();key=(cat,'rhythm')
    if now-self.last_action.get(key,0)<.15:return
    self.last_action[key]=now
    # Use the actual shared note times rather than accepting arbitrary taps on an infinite metronome.
    pending=[n for n in self.tug_notes if n['id'] not in self.tug_judged.setdefault(cat,set()) and n['at']>=self.elapsed-.23]
    nearest=min(pending,key=lambda n:abs(n['at']-self.elapsed)) if pending else None
    delta=abs(nearest['at']-self.elapsed) if nearest else 999
    if delta<=.22:
     self.tug_judged[cat].add(nearest['id'])
     if delta<=.115:
      e['notes']=min(100,e['notes']+16);self.tug_combo[cat]=self.tug_combo.get(cat,0)+1;result='perfect'
     else:
      e['notes']=min(100,e['notes']+10);self.tug_combo[cat]=self.tug_combo.get(cat,0)+1;result='good'
    else:
     e['notes']=max(0,e['notes']-8);self.tug_combo[cat]=0;result='miss'
    self.fx.append({'t':round(self.elapsed,2),'id':cat,'kind':result})
 async def tick(self,dt):
  if self.phase!='play':return
  self.elapsed+=dt
  if self.event==0:
   self.race_attacks={k:t for k,t in self.race_attacks.items() if self.elapsed-t<.5}
   for i,e in self.entities.items():
    if i in self.race_finish:continue
    e['jump']=max(0,e['jump']-dt);e['shield']=max(0,e['shield']-dt);e['stun']=max(0,e['stun']-dt);e['race_inv']=max(0,e['race_inv']-dt);e['banana_slow']=max(0,e['banana_slow']-dt)
    if e['race_down']>0:
     e['race_down']=max(0,e['race_down']-dt)
     if e['race_down']==0:
      e['hp']=65;e['race_inv']=2.2;e['stun']=0
      self.fx.append({'t':round(self.elapsed,2),'id':i,'kind':'recover'})
     continue
    inp=self.inputs.get(i,{});
    if i in self.cpu_ids:
     speed=[40,33,47,37][i]*(random.random()*.16+.94)
     target_lane=int((i+self.stage)%4)
     nearby=[it for it in self.items if not it['taken'] and 0<it['x']-e['progress']<65 and it['kind'] in ('skate','fish')]
     if nearby:target_lane=nearby[0]['lane']
     e['y']+=max(-dt*1.25,min(dt*1.25,target_lane-e['y']))
    else:
     speed=max(0,inp.get('x',0))*[45,35,51,41][i]
     if inp.get('x',0)<-.15:e['face']=-1
     elif inp.get('x',0)>.15:e['face']=1
     if abs(inp.get('y',0))>.18:e['y']=max(0,min(3,e['y']+inp['y']*dt*2.8))
     lane=int(max(0,min(3,e['y'])))
    if i in self.cpu_ids:
     upcoming=next((ob for ob in self.obstacles if 0<ob['x']-e['progress']<38 and abs(ob['lane']-e['y'])<.48),None)
     if upcoming and e['jump']<=0 and e['stun']<=0:
      e['jump']=.90 if upcoming['kind']!='puddle' else .72
    if i in self.cpu_ids and e['stun']<=0 and e['race_down']<=0:
     rival=next((z for z in self.entities.values() if z['id']!=i and z['race_down']<=0 and 0<z['progress']-e['progress']<54 and abs(z['y']-e['y'])<.55 and z['race_inv']<=0),None)
     if rival and self.elapsed-self.last_action.get((i,'cpu_race_punch'),-100)>1.85:
      self.last_action[(i,'cpu_race_punch')]=self.elapsed
      self.race_attacks[i]=round(self.elapsed,2)
      rival['hp']=max(0,rival['hp']-6);rival['stun']=.35;rival['race_inv']=.6
      rival['progress']+=8
      self.fx.append({'t':round(self.elapsed,2),'id':i,'kind':'punch'})
      self.fx.append({'t':round(self.elapsed,2),'id':rival['id'],'kind':'hit'})
    if self.stage==5:speed*=.83
    if e['banana_slow']>0:speed*=.63
    if e['skate']>0:speed*=1.85;e['skate']=max(0,e['skate']-dt)
    if e['stun']>0:speed*=.28
    prev=e['progress'];e['progress']+=speed*dt
    for ob in self.obstacles:
     if prev<ob['x']<=e['progress'] and abs(ob['lane']-e['y'])<.40 and e['jump']<.12 and e['skate']<=0 and e['shield']<=0 and e['race_inv']<=0:
      hazard=ob['kind'];e['race_inv']=1.3
      if hazard=='banana':e['stun']=.22;e['banana_slow']=1.8;damage=5
      elif hazard=='puddle':e['stun']=.20;e['banana_slow']=1.2;damage=4
      elif hazard=='hurdle':e['stun']=.95;damage=12
      elif hazard=='box':e['stun']=.85;damage=11
      else:e['stun']=.6;damage=8
      e['hp']=max(0,e['hp']-damage)
      self.fx.append({'t':round(self.elapsed,2),'id':i,'kind':'obstacle','hazard':hazard,'damage':damage})
    for item in self.items:
     if not item['taken'] and prev<item['x']<=e['progress'] and abs(item['lane']-e['y'])<.48:
      item['taken']=True
      if item['kind']=='skate':e['skate']=8.4;e['shield']=max(e['shield'],8.4)
      elif item['kind']=='fish':e['hp']=min(100,e['hp']+30)
      else:e['weapon']='pan'
      self.fx.append({'t':round(self.elapsed,1),'id':i,'kind':item['kind']})
    if e['hp']<=0 and e['race_down']<=0:
     e['race_down']=2.4;e['stun']=2.4;e['skate']=0;e['weapon']=None
     self.fx.append({'t':round(self.elapsed,2),'id':i,'kind':'down'})
    if e['progress']>=760:self.race_finish[i]=self.elapsed
    e['energy']=min(100,e['energy']+dt*5)
   # Projectiles are server-controlled so both phones see the same flight.
   for proj in list(self.projectiles):
    proj['x']+=proj['vx']*dt;proj['life']-=dt
    for j,tgt in self.entities.items():
     if j==proj['owner'] or tgt['race_inv']>0 or tgt['race_down']>0 or tgt['shield']>0 or j in self.race_finish:continue
     if abs(proj['x']-tgt['progress'])<20 and abs(proj['y']-tgt['y'])<.65:
      tgt['stun']=1.05;tgt['race_inv']=.9;tgt['hp']=max(0,tgt['hp']-16);proj['life']=0;self.fx.append({'t':round(self.elapsed,2),'id':j,'kind':'throw-hit'});break
    if proj['life']<=0:self.projectiles.remove(proj)
   if len(self.race_finish)==4 or self.elapsed>=45:
    for i,e in self.entities.items():
     metric=self.race_finish.get(i,self.elapsed+max(0,760-e['progress'])/max(10,[45,35,51,41][i]));self.race_times[i].append(round(metric,2))
    if self.stage>=5:
     self.finish_event(sorted(range(4),key=lambda i:sum(self.race_times[i])))
    else:
     self.stage+=1;self.reset_entities()
  elif self.event==1:
   for i,e in self.entities.items():
    e['charge']=min(100,e['charge']+dt*20);e['special']=max(0,e['special']-dt);e['shield']=max(0,e['shield']-dt);e['jump']=max(0,e['jump']-dt)
    e['stun']=max(0,e['stun']-dt);e['inv']=max(0,e['inv']-dt)
    if e['respawn']>0:
     e['respawn']=max(0,e['respawn']-dt)
     if not e['respawn']:e['x']=350+(i%2)*300;e['y']=165+(i//2)*135;e['inv']=2;e['hit_by']=None;e['vx']=0;e['vy']=0
     continue
    inp=self.inputs.get(i,{'x':0,'y':0})
    if i in self.cpu_ids:
     opponents=[t for t in self.entities.values() if t['id']!=i and t['respawn']<=0]
     if opponents:
      nearest=min(opponents,key=lambda t:abs(t['x']-e['x'])+abs(t['y']-e['y'])*1.5)
      inp={'x':max(-1,min(1,(nearest['x']-e['x'])/80)),'y':max(-1,min(1,(nearest['y']-e['y'])/75))}
     if e['x']<160:inp['x']=max(inp['x'],.7)
     if e['x']>840:inp['x']=min(inp['x'],-.7)
     if e['y']<160:inp['y']=max(inp['y'],.7)
     if e['y']>410:inp['y']=min(inp['y'],-.7)
    # Server-authoritative velocity-based knockback; the edge test uses the feet.
    e['x']+=e['vx']*dt;e['y']+=e['vy']*dt
    e['vx']*=math.exp(-5.7*dt);e['vy']*=math.exp(-6.8*dt)
    if abs(e['vx'])<1:e['vx']=0
    if abs(e['vy'])<1:e['vy']=0
    if e['stun']<=0 and e['special']<=0:
     e['x']+=inp.get('x',0)*[130,100,150,115][i]*dt;e['y']+=inp.get('y',0)*85*dt
    e['face']=1 if inp.get('x',0)>0.1 else (-1 if inp.get('x',0)<-0.1 else e['face'])
    for item in self.items:
     if not item['taken'] and abs(e['x']-item['x'])<46 and abs(e['y']-item['y'])<46:
      item['taken']=True
      if item['kind']=='fish':e['hp']=min(100,e['hp']+36)
      else:e['weapon']='bomb'
      self.fx.append({'t':round(self.elapsed,1),'id':i,'kind':item['kind']})
    if not self.in_arena(e):
     self.battle_drop(i,e.get('hit_by'),False)
     continue
    if i in self.cpu_ids and random.random()<dt*2.8:
     opponents=[t for t in self.entities.values() if t['id']!=i and t['respawn']<=0]
     if opponents:
      target=min(opponents,key=lambda t:abs(t['x']-e['x'])+abs(t['y']-e['y']))
      e['face']=1 if target['x']>=e['x'] else -1
      self.battle_attack(i,e['charge']>=100 and random.random()<.42,source='cpu')
   if self.elapsed>=60:self.finish_event(sorted(range(4),key=lambda i:(-self.entities[i]['pts'],self.entities[i]['outs'])))
  else:
   # Duel bracket: head-to-head players, then winner vs CPU; other CPU for 3/4
   a,b=self.duel
   for i,e in self.entities.items():
    if i in self.cpu_ids:e['energy']=72+10*math.sin(self.elapsed/3+i)
    else:e['energy']=max(0,e['energy']-dt*13);e['notes']=max(0,e['notes']-dt*9)
   for cat in self.duel:
    for note in self.tug_notes:
     if note['at']<self.elapsed-.23 and note['id'] not in self.tug_judged.setdefault(cat,set()):
      self.tug_judged[cat].add(note['id'])
      self.entities[cat]['notes']=max(0,self.entities[cat]['notes']-2.2)
      self.tug_combo[cat]=0
   va=self.entities[a]['energy']*.87+self.entities[a]['notes']*.65
   vb=self.entities[b]['energy']*.87+self.entities[b]['notes']*.65
   self.tug_progress+= (va-vb)*dt*.55
   if self.elapsed>=35 or abs(self.tug_progress)>240:
    winner=a if self.tug_progress>=0 else b;loser=b if winner==a else a
    cpuA,cpuB=self.cpu_ids
    # CPU 3rd/4th classification
    if self.round==1:
     self.tug_games=[winner,loser]
     # The other semi is CPU vs CPU and is resolved server-side.
     cpu_strength=[88,105,110,80]
     cpuA,cpuB=sorted(self.cpu_ids,key=lambda i:-cpu_strength[i]);self.cpu_tug_winner=cpuA;self.cpu_tug_loser=cpuB
     self.duel=[winner,cpuA];self.round=2;self.tug_progress=0;self.elapsed=0;self.make_tug_chart()
     for e in self.entities.values():e['energy']=0;e['notes']=0
     self.fx.append({'t':0,'id':winner,'kind':'semi-win'})
    else:
     win2=self.duel[0] if self.tug_progress>=0 else self.duel[1]
     lose2=self.duel[1] if win2==self.duel[0] else self.duel[0]
     remaining=[i for i in range(4) if i not in (win2,lose2)]
     # Third-place rank is decided by semifinal performance, tie by character power.
     self.finish_event([win2,lose2]+remaining)
async def websocket(request):
 ws=web.WebSocketResponse(heartbeat=20);await ws.prepare(request)
 slot=None;room=None
 try:
  async for msg in ws:
   if msg.type!=WSMsgType.TEXT:continue
   try:d=json.loads(msg.data)
   except:continue
   action=d.get('action')
   if action in ('create','join') and room is None:
    if action=='create':
     code=''.join(str(secrets.randbelow(10)) for _ in range(6))
     while code in rooms:code=''.join(str(secrets.randbelow(10)) for _ in range(6))
     room=rooms[code]=Room(code)
    else:room=rooms.get(str(d.get('code','')).strip())
    if not room or len(room.clients)>=2 or room.phase!='lobby':await ws.send_json({'type':'error','message':'部屋が見つからないか、参加できません'});room=None;continue
    slot=next(i for i in (0,1) if i not in room.clients);room.clients[slot]={'ws':ws,'cat':None,'ready':False}
    await ws.send_json({'type':'joined','slot':slot,'code':room.code});await room.broadcast()
   elif room and action=='select' and room.phase=='lobby':
    cat=d.get('cat')
    if type(cat)==int and 0<=cat<=3 and not any(i!=slot and p['cat']==cat for i,p in room.clients.items()):
     room.clients[slot]['cat']=cat;room.clients[slot]['ready']=False;await room.broadcast()
   elif room and action=='ready' and room.phase=='lobby':
    if room.clients[slot]['cat'] is not None:room.clients[slot]['ready']=bool(d.get('ready',True))
    if len(room.clients)==2 and all(p['ready'] for p in room.clients.values()):room.start()
    await room.broadcast()
   elif room and action=='input':
    room.apply(slot,d.get('kind'),d.get('detail'))
   elif room and action=='next' and room.phase=='results':
    room.clients[slot]['advance']=True
    if all(p.get('advance',False) for p in room.clients.values()):
     for p in room.clients.values():p['advance']=False
     room.next_event()
    await room.broadcast()
 except Exception as exc:print('websocket exception',exc)
 finally:
  if room is not None and slot is not None:
   room.clients.pop(slot,None)
   if room.phase=='lobby':
    for p in room.clients.values():p['ready']=False
   if not room.clients:rooms.pop(room.code,None)
   else:await room.broadcast()
 return ws
async def ticker(app):
 while True:
  await asyncio.sleep(.05)
  for room in list(rooms.values()):
   await room.tick(.05)
   await room.broadcast()
async def startapp(app):app['ticker']=asyncio.create_task(ticker(app))
async def stopapp(app):app['ticker'].cancel()
async def version(request):return web.json_response({'version':'0.12','name':'ニャンコ大運動会・レース障害物と飛び道具同期改善'})
app=web.Application();app.router.add_get('/version',version);app.router.add_get('/ws',websocket);app.router.add_static('/assets/',BASE/'static'/'assets',show_index=False);app.router.add_get('/',lambda r:web.FileResponse(BASE/'static'/'index.html'));app.on_startup.append(startapp);app.on_cleanup.append(stopapp)
if __name__=='__main__':web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')))
