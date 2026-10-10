import asyncio,importlib.util,json
from pathlib import Path
from aiohttp.test_utils import TestServer,TestClient
sp=importlib.util.spec_from_file_location('g',(Path(__file__).parent/'server.py'))
g=importlib.util.module_from_spec(sp);sp.loader.exec_module(g)
async def receive_type(ws,wanted):
 for _ in range(20):
  msg=await asyncio.wait_for(ws.receive(),5)
  if msg.type==1:
   d=json.loads(msg.data)
   if d.get('type')==wanted:return d
 raise AssertionError(f'no {wanted}')
async def main():
 async with TestServer(g.app) as server:
  async with TestClient(server) as client:
   a=await client.ws_connect('/ws');b=await client.ws_connect('/ws')
   await a.send_json({'action':'create'})
   aa=await receive_type(a,'joined');code=aa['code']
   await b.send_json({'action':'join','code':code})
   bb=await receive_type(b,'joined');assert bb['code']==code
   await a.send_json({'action':'select','cat':0});await b.send_json({'action':'select','cat':2})
   await a.send_json({'action':'ready','ready':True});await b.send_json({'action':'ready','ready':True})
   live=await receive_type(a,'state')
   for _ in range(30):
    if live['phase']=='play':break
    live=await receive_type(a,'state')
   assert live['phase']=='play',(live.get('phase'),live.get('peers'))
   await a.send_json({'action':'input','kind':'move','detail':{'x':1,'y':0}})
   await b.send_json({'action':'input','kind':'jump'})
   await asyncio.sleep(.4)
   room=g.rooms[code]
   assert room.entities[0]['progress']>0
   assert room.entities[2]['jump']>0
   print('REAL WS 2 clients: OK',code,'pos',room.entities[0]['progress'],'jump',room.entities[2]['jump'])
   await a.close();await b.close()
asyncio.run(main())
