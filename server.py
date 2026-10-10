import os, json, secrets
from aiohttp import web, WSMsgType
from pathlib import Path
ROOT=Path(__file__).parent/'static'
rooms={}
async def socket(req):
 ws=web.WebSocketResponse(heartbeat=20, max_msg_size=1_000_000);await ws.prepare(req)
 code=None;pid=None
 async def emit(r):
  for p,w in list(r['users'].items()):
   if not w.closed:
    await w.send_json({'type':'room','code':r['code'],'players':list(r['users']),'choices':r['choices'],'ready':r['ready'],'started':r['started']})
 try:
  async for msg in ws:
   if msg.type!=WSMsgType.TEXT:continue
   try:d=json.loads(msg.data)
   except:continue
   action=d.get('type')
   if action in ('create','join') and code is None:
    if action=='create':
     code=''.join(str(secrets.randbelow(10)) for _ in range(6))
     while code in rooms:code=''.join(str(secrets.randbelow(10)) for _ in range(6))
     rooms[code]={'code':code,'users':{},'choices':{},'ready':{},'started':False,'sport':0,'finished':False,'last_order':None}
    else:
     code=str(d.get('code',''))
     if code not in rooms or len(rooms[code]['users'])>=2 or rooms[code]['started']:
      await ws.send_json({'type':'error','message':'参加できない部屋です'});code=None;continue
    r=rooms[code];pid='1P' if '1P' not in r['users'] else '2P';r['users'][pid]=ws;r['choices'][pid]=None;r['ready'][pid]=False
    await ws.send_json({'type':'joined','id':pid,'code':code});await emit(r)
   elif code in rooms and pid:
    r=rooms[code]
    if action=='select' and not r['started']:
     v=d.get('character');other='2P' if pid=='1P' else '1P'
     if type(v)==int and 0<=v<4 and r['choices'].get(other)!=v:
      r['choices'][pid]=v;r['ready'][pid]=False;await emit(r)
    elif action=='ready' and r['choices'][pid] is not None:
     r['ready'][pid]=True;await emit(r)
     if len(r['users'])==2 and all(r['ready'].values()):
      r['started']=True;r['sport']=0;r['finished']=False;r['last_order']=None
      for w in r['users'].values():await w.send_json({'type':'start','choices':r['choices']})
    elif action=='event' and pid=='1P' and r['started']:
     if d.get('event')=='next' and r['finished'] and r['sport']<=2:
      r['sport']+=1;r['finished']=False
      for w in r['users'].values():
       if not w.closed:await w.send_json({'type':'event','event':'next','sport':r['sport']})
    elif action=='snapshot' and pid=='1P' and r['started'] and not r['finished']:
     w=r['users'].get('2P')
     if w and not w.closed and d.get('sport')==r['sport'] and isinstance(d.get('state'),dict) and len(msg.data)<300_000:
      await w.send_json({'type':'snapshot','sport':r['sport'],'state':d['state']})
    elif action=='complete' and pid=='1P' and r['started'] and not r['finished']:
     order=d.get('order')
     if d.get('sport')==r['sport'] and isinstance(order,list) and len(order)==4 and sorted(order)==[0,1,2,3]:
      r['finished']=True;r['last_order']=order
      for w in r['users'].values():
       if not w.closed:await w.send_json({'type':'complete','sport':r['sport'],'order':order})
    elif action=='input' and r['started']:
     other='2P' if pid=='1P' else '1P';w=r['users'].get(other)
     if w and not w.closed:await w.send_json({'type':'remote_input','player':pid,'input':d.get('input',{})})
 finally:
  if code in rooms and pid:
   r=rooms[code];r['users'].pop(pid,None);r['ready'].pop(pid,None);r['choices'].pop(pid,None)
   if not r['users']:rooms.pop(code,None)
   else:
    r['started']=False;await emit(r)
 return ws
app=web.Application();app.router.add_get('/ws',socket);app.router.add_static('/',ROOT,show_index=True)
if __name__=='__main__':web.run_app(app,host='0.0.0.0',port=int(os.getenv('PORT','10000')))
