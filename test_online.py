import asyncio, importlib.util, os, time
from pathlib import Path
spec=importlib.util.spec_from_file_location('game',str(Path(__file__).parent/'server.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class WS:
 closed=False
 async def send_str(self,*args): pass
async def main():
 r=g.Room('123456');r.clients={0:{'ws':WS(),'cat':0,'ready':True},1:{'ws':WS(),'cat':2,'ready':True}};r.start()
 assert r.event==0 and r.stage==1 and r.phase=='play'
 a,b=r.entities[0],r.entities[2]
 a['progress']=90;a['y']=1;a['face']=1
 b['progress']=95;b['y']=1;b['stun']=1.1
 r.apply(0,'grab')
 assert a['carrying']==2 and b['carried_by']==0, (a,b)
 await r.tick(.05)
 r.apply(0,'grab')
 assert a['carrying'] is None and b['carried_by'] is None and b['throw_flight']>.6
 print('grab/throw: OK',b['hp'],b['throw_flight'])
 # Racing to stage 5
 for stage in range(1,6):
  r.elapsed=1
  for e in r.entities.values():e['progress']=760
  await r.tick(.05)
  if stage<5:assert r.stage==stage+1
 assert r.phase=='results' and r.event==0
 print('race 5 stages: OK')
 r.next_event();assert r.event==1
 # Combat knockback and countdown
 for e in r.entities.values():e['x']=830;e['y']=320;e['inv']=0
 r.entities[0]['x']=420;r.entities[2]['x']=485
 r.entities[0]['face']=1;r.battle_attack(0)
 assert r.entities[2]['hp']<100
 print('combat hit: OK',r.entities[2]['hp'])
 r.elapsed=59.99;await r.tick(.05);assert r.phase=='results'
 r.next_event();assert r.event==2 and r.round==1
 # Simulate semifinals/final
 r.elapsed=34.99;await r.tick(.05);assert r.round==2
 r.elapsed=34.99;await r.tick(.05);assert r.phase=='results'
 r.next_event();assert r.phase=='final' and len(r.history)==3
 print('tug bracket & final: OK',r.result_order,'scores',r.scores)
asyncio.run(main())
