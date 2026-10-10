import os, json, secrets
from aiohttp import web, WSMsgType
from pathlib import Path
ROOT=Path(__file__).parent/'static'
rooms={}
SPORTS=['クロスカントリー','格闘大会','綱引き']
async def socket(req):
 ws=web.WebSocketResponse(heartbeat=20,max_msg_size=1_000_000);await ws.prepare(req)
 code=None;pid=None
 async def broadcast(r,payload):
  for w in list(r['users'].values()):
   if not w.closed:await w.send_json(payload)
 async def emit(r):
  await broadcast(r,{'type':'room','code':r['code'],'players':list(r['users']),'choices':r['choices'],'ready':r['ready'],'phase':r['phase'],'sport':r['sport']})
 async def prepare(r,sport):
  r['sport']=sport;r['phase']='prepare';r['ready']={key:False for key in r['users']}
  await broadcast(r,{'type':'prepare','sport':sport});await emit(r)
 try:
  async for msg in ws:
   if msg.type!=WSMsgType.TEXT:continue
   try:d=json.loads(msg.data)
   except (ValueError,TypeError):continue
   action=d.get('type')
   if action in ('create','join') and code is None:
    if action=='create':
     code=''.join(str(secrets.randbelow(10)) for _ in range(6))
     while code in rooms:code=''.join(str(secrets.randbelow(10)) for _ in range(6))
     rooms[code]={'code':code,'users':{},'choices':{},'ready':{},'phase':'lobby','sport':0,'last_order':None,'results':[]}
    else:
     code=str(d.get('code',''))
     if code not in rooms or len(rooms[code]['users'])>=2 or rooms[code]['phase']!='lobby':
      await ws.send_json({'type':'error','message':'参加できない部屋です'});code=None;continue
    r=rooms[code];pid='1P' if '1P' not in r['users'] else '2P';r['users'][pid]=ws;r['choices'][pid]=None;r['ready'][pid]=False
    await ws.send_json({'type':'joined','id':pid,'code':code});await emit(r)
   elif code in rooms and pid:
    r=rooms[code];phase=r['phase']
    if action=='select' and phase=='lobby':
     v=d.get('character');other='2P' if pid=='1P' else '1P'
     if type(v)==int and 0<=v<4 and r['choices'].get(other)!=v:
      r['choices'][pid]=v;r['ready'][pid]=False;await emit(r)
    elif action=='ready' and phase=='lobby' and r['choices'].get(pid) is not None:
     r['ready'][pid]=True;await emit(r)
     if len(r['users'])==2 and all(r['ready'].values()):
      r['results']=[];await broadcast(r,{'type':'start','choices':r['choices']});await prepare(r,0)
    elif action=='sport_ready' and phase=='prepare' and d.get('sport')==r['sport']:
     r['ready'][pid]=True;await emit(r)
     if len(r['users'])==2 and all(r['ready'].values()):
      r['phase']='running'
      await broadcast(r,{'type':'go','sport':r['sport']})
    elif action=='next' and phase=='result' and pid=='1P' and d.get('sport')==r['sport']:
     if r['sport']<2:await prepare(r,r['sport']+1)
     else:
      r['phase']='final';await broadcast(r,{'type':'final','results':r['results']})
    elif action=='snapshot' and phase=='running' and pid=='1P' and d.get('sport')==r['sport'] and isinstance(d.get('state'),dict) and len(msg.data)<300_000:
     w=r['users'].get('2P')
     if w and not w.closed:await w.send_json({'type':'snapshot','sport':r['sport'],'state':d['state']})
    elif action=='complete' and phase=='running' and pid=='1P':
     order=d.get('order')
     if d.get('sport')==r['sport'] and isinstance(order,list) and len(order)==4 and sorted(order)==[0,1,2,3]:
      r['phase']='result';r['last_order']=order;r['results'].append(order)
      await broadcast(r,{'type':'complete','sport':r['sport'],'order':order,'results':r['results']})
    elif action=='input' and phase=='running':
     other='2P' if pid=='1P' else '1P';w=r['users'].get(other)
     if w and not w.closed:await w.send_json({'type':'remote_input','player':pid,'input':d.get('input',{})})
 finally:
  if code in rooms and pid:
   r=rooms[code];r['users'].pop(pid,None);r['ready'].pop(pid,None);r['choices'].pop(pid,None)
   if not r['users']:rooms.pop(code,None)
   else:
    r['phase']='lobby';await broadcast(r,{'type':'error','message':'対戦相手が切断しました。再読み込みして部屋を作り直してください。'})
 return ws
app=web.Application();app.router.add_get('/ws',socket)
async def home(req):raise web.HTTPFound('/online.html')
app.router.add_get('/',home);app.router.add_static('/',ROOT,show_index=False)
if __name__=='__main__':web.run_app(app,host='0.0.0.0',port=int(os.getenv('PORT','10000')))
