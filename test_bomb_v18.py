from server import Room
import asyncio
async def main():
 r=Room('123456');r.event=1;r.phase='play';r.reset_entities();r.entities[0].update(x=500,y=260,weapon='bomb');r.entities[1].update(x=755,y=260,inv=0,hp=100);r.clients={0:{'cat':0},1:{'cat':1}}
 r.apply(0,'throw');assert len(r.bombs)==1
 assert r.entities[1]['hp']==100,'bomb must not hit immediately'
 for _ in range(24):await r.tick(.05)
 assert len(r.bombs)==0,'bomb should explode'
 assert any(f['kind']=='explosion' for f in r.fx)
 print('bomb flight/fuse/explosion:',round(r.entities[1]['hp'],2), 'FX',len(r.fx))
asyncio.run(main())
