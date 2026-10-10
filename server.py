import asyncio, json, os, random, secrets, time, math
from pathlib import Path
from aiohttp import web, WSMsgType
BASE=Path(__file__).parent
NAMES=['まるねこ','でぶねこ','ダックス','もふねこ']
POINTS=[10,6,3,1]
rooms={}
class Room:
 def __init__(self,code):
  self.code=code;self.clients={};self.phase='lobby';self.event=0;self.stage=1;self.elapsed=0;self.scores=[0]*4;self.history=[];self.players=[];self.cpu_ids=[];self.entities={};self.inputs={};self.announced=0;self.round=1;self.duel=[];self.tug_games=[];self.tug_progress=0;self.race_times={i:[] for i in range(4)};self.result_order=[];self.end_time=0;self.last_action={};self.items=[];self.obstacles=[];self.stage_seed=0;self.fx=[];self.race_finish={}
 def state(self):
  return dict(type='state',code=self.code,phase=self.phase,event=self.event,stage=self.stage,elapsed=round(self.elapsed,1),round=self.round,
   peers=[{'slot':i,'cat':p['cat'],'ready':p['ready'],'connected':not p['ws'].closed} for i,p in self.clients.items()],
   names=NAMES,entities=self.entities,scores=(self.scores if self.phase=='final' else None),history=(self.history if self.phase=='final' else []),
   order=self.result_order if self.phase in ('results','final') else [],duel=self.duel,tug_games=self.tug_games,tug_progress=self.tug_progress,
   messages=self.announced,items=self.items,obstacles=self.obstacles,fx=self.fx[-12:],race_times=self.race_times if self.phase=='results' and self.event==0 else None)
 async def broadcast(self,obj=None):
  if obj is None:obj=self.state()
  raw=json.dumps(obj,ensure_ascii=False)
  for peer in list(self.clients.values()):
   try:await peer['ws'].send_str(raw)
   except:pass
 def reset_entities(self):
  self.elapsed=0;self.inputs={};self.entities={};self.last_action={};self.fx=[];self.race_finish={}
  for i in range(4):
   self.entities[i]=dict(id=i,x=155+i*205,y=200+(i%2)*115,hp=100,pts=0,ko=0,outs=0,charge=75,stun=0,inv=0,face=1,respawn=0,progress=0,energy=0,notes=0,skate=0,score=0,weapon=None,z=0,jump=0,shield=0,special=0)
  self.items=[];self.obstacles=[]
  if self.event==0:
   for i in range(4):self.entities[i]['y']=i
   rng=random.Random(self.code+'-'+str(self.stage));self.obstacles=[{'x':x,'lane':rng.randrange(4),'kind':rng.choice(['box','cone','banana','hurdle'])} for x in range(85,750,48 if self.stage==5 else 110)]
   if self.stage<5:self.items=[{'x':rng.randrange(165,440),'lane':rng.randrange(4),'kind':'skate','taken':False}]
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
   a,b=[p['cat'] for p in self.clients.values()];self.duel=[a,b];self.tug_games=[];self.tug_progress=0
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
   if kind=='dash' and e['energy']>=20:e['progress']+=13;e['energy']-=20
   if kind=='jump' and e['jump']<=0:e['jump']=.72;e['energy']=min(100,e['energy']+5)
  elif self.event==1:
   if kind in ('punch','special') and e['respawn']<=0 and e['stun']<=0:
    now=time.monotonic();key=(cat,kind);delay=.24 if kind=='punch' else .55
    if now-self.last_action.get(key,0)<delay:return
    if kind=='special' and e['charge']<100:return
    self.last_action[key]=now
    if kind=='special':
     e['charge']=0;e['special']=.9;self.fx.append({'t':round(self.elapsed,1),'id':cat,'kind':['headbutt','slaps','whirl','feign'][cat]})
     if cat==3:e['inv']=3.2;e['shield']=3.2;return
    reach=(185 if cat in (1,2) else 165) if kind=='special' else 76
    damage=([35,42,29,0][cat] if kind=='special' else 13)
    near=[t for t in self.entities.values() if t['id']!=cat and t['respawn']<=0 and t['inv']<=0 and abs(t['x']-e['x'])<reach and abs(t['y']-e['y'])<75]
    if near:
     target=min(near,key=lambda t:abs(t['x']-e['x']))
     target['hp']-=damage;target['stun']=.32;target['inv']=.45
     target['x']+= (1 if target['x']>=e['x'] else -1)*(([165,210,175,0][cat]) if kind=='special' else 34);self.fx.append({'t':round(self.elapsed,1),'id':target['id'],'kind':'hit'})
     if target['hp']<=0:target['pts']-=3;target['ko']+=1;target['respawn']=1.5;target['hp']=100
     elif target['x']<35 or target['x']>965:
      e['pts']+=3;target['outs']+=1;target['respawn']=1.5;target['hp']=100
   if kind=='jump':e['jump']=.65;e['inv']=max(e['inv'],.22)
   if kind=='throw' and e['weapon']=='bomb':
    e['weapon']=None;self.fx.append({'t':round(self.elapsed,1),'id':cat,'kind':'bomb'})
    for target in self.entities.values():
     if target['id']!=cat and target['respawn']<=0 and abs(target['x']-e['x'])<215 and abs(target['y']-e['y'])<115:
      target['hp']-=26;target['x']+=(1 if target['x']>=e['x'] else -1)*120;target['inv']=.6
      if target['hp']<=0:target['pts']-=3;target['ko']+=1;target['respawn']=1.5;target['hp']=100
  elif self.event==2 and cat in self.duel:
   if kind=='mash':
    now=time.monotonic();key=(cat,'mash')
    if now-self.last_action.get(key,0)>=.065:
     e['energy']=min(100,e['energy']+4.5);self.last_action[key]=now
   if kind=='rhythm':
    now=time.monotonic();key=(cat,'rhythm')
    if now-self.last_action.get(key,0)<.15:return
    self.last_action[key]=now
    beat=(self.elapsed-1.5)/.9
    if abs(beat-round(beat))<.19:e['notes']=min(100,e['notes']+15)
    else:e['notes']=max(0,e['notes']-8)
 async def tick(self,dt):
  if self.phase!='play':return
  self.elapsed+=dt
  if self.event==0:
   for i,e in self.entities.items():
    if i in self.race_finish:continue
    e['jump']=max(0,e['jump']-dt);e['shield']=max(0,e['shield']-dt);e['stun']=max(0,e['stun']-dt)
    inp=self.inputs.get(i,{});
    if i in self.cpu_ids:
     speed=[40,33,47,37][i]*(random.random()*.16+.94)
     lane=int((i+self.stage)%4)
    else:
     speed=max(0,inp.get('x',0))*[45,35,51,41][i]
     if abs(inp.get('y',0))>.35:e['y']=max(0,min(3,round((e['y'] if e['y']<=3 else i)+inp['y']*dt*3)))
     lane=int(max(0,min(3,e['y'])))
    if self.stage==5:speed*=.83
    if e['skate']>0:speed*=1.7;e['skate']=max(0,e['skate']-dt)
    if e['stun']>0:speed*=.28
    prev=e['progress'];e['progress']+=speed*dt
    for ob in self.obstacles:
     if prev<ob['x']<=e['progress'] and ob['lane']==lane and not e['jump'] and not e['skate'] and e['shield']<=0:
      e['stun']=.75;e['progress']=ob['x'];e['hp']=max(0,e['hp']-9);self.fx.append({'t':round(self.elapsed,1),'id':i,'kind':'hit'})
    for item in self.items:
     if not item['taken'] and prev<item['x']<=e['progress'] and item['lane']==lane:
      item['taken']=True;e['skate']=7.0;self.fx.append({'t':round(self.elapsed,1),'id':i,'kind':'skate'})
    if e['progress']>=760:self.race_finish[i]=self.elapsed
    e['energy']=min(100,e['energy']+dt*5)
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
     if not e['respawn']:e['x']=220+170*i;e['y']=240+i%2*100;e['inv']=2
     continue
    inp=self.inputs.get(i,{'x':random.uniform(-1,1),'y':random.uniform(-1,1)}) if i not in self.cpu_ids else {'x':random.uniform(-.8,.8),'y':random.uniform(-.8,.8)}
    if e['stun']<=0:
     e['x']+=inp.get('x',0)*[130,100,150,115][i]*dt;e['y']+=inp.get('y',0)*85*dt
    e['y']=max(110,min(460,e['y']))
    for item in self.items:
     if not item['taken'] and abs(e['x']-item['x'])<46 and abs(e['y']-item['y'])<46:
      item['taken']=True
      if item['kind']=='fish':e['hp']=min(100,e['hp']+36)
      else:e['weapon']='bomb'
      self.fx.append({'t':round(self.elapsed,1),'id':i,'kind':item['kind']})
    if e['x']<35 or e['x']>965:e['outs']+=1;e['respawn']=1.5;e['hp']=100
    if i in self.cpu_ids and random.random()<dt*.8:
     target=min([t for t in self.entities.values() if t['id']!=i],key=lambda t:abs(t['x']-e['x'])+abs(t['y']-e['y']))
     if abs(target['x']-e['x'])<75 and abs(target['y']-e['y'])<80 and target['inv']<=0:
      target['hp']-=9;target['inv']=.6
      if target['hp']<=0:target['hp']=100;target['pts']-=3;target['ko']+=1;target['respawn']=1.5
   if self.elapsed>=60:self.finish_event(sorted(range(4),key=lambda i:(-self.entities[i]['pts'],self.entities[i]['outs'])))
  else:
   # Duel bracket: head-to-head players, then winner vs CPU; other CPU for 3/4
   a,b=self.duel
   for i,e in self.entities.items():
    if i in self.cpu_ids:e['energy']=72+10*math.sin(self.elapsed/3+i)
    else:e['energy']=max(0,e['energy']-dt*13);e['notes']=max(0,e['notes']-dt*9)
   va=self.entities[a]['energy']*.87+self.entities[a]['notes']*.65
   vb=self.entities[b]['energy']*.87+self.entities[b]['notes']*.65
   self.tug_progress+= (va-vb)*dt*.55
   if self.elapsed>=35 or abs(self.tug_progress)>240:
    winner=a if self.tug_progress>=0 else b;loser=b if winner==a else a
    cpuA,cpuB=self.cpu_ids
    # CPU 3rd/4th classification
    if self.round==1:
     self.tug_games=[winner,loser];self.duel=[winner,cpuA];self.round=2;self.tug_progress=0;self.elapsed=0
     for e in self.entities.values():e['energy']=0;e['notes']=0
    else:
     win2=self.duel[0] if self.tug_progress>=0 else self.duel[1]
     lose2=self.duel[1] if win2==self.duel[0] else self.duel[0]
     self.finish_event([win2,lose2,self.tug_games[1],cpuB])
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
app=web.Application();app.router.add_get('/ws',websocket);app.router.add_static('/assets/',BASE/'static'/'assets',show_index=False);app.router.add_get('/',lambda r:web.FileResponse(BASE/'static'/'index.html'));app.on_startup.append(startapp);app.on_cleanup.append(stopapp)
if __name__=='__main__':web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')))
