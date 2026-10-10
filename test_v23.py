import asyncio,sys
from pathlib import Path
from aiohttp import web, ClientSession, WSMsgType
from playwright.async_api import async_playwright
sys.path.insert(0,'/mnt/data/nyanko_fix_v23')
from server import app
async def main():
 runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',18767);await site.start()
 try:
  async with async_playwright() as p:
   browser=await p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
   a=await browser.new_page(viewport={'width':844,'height':390});b=await browser.new_page(viewport={'width':844,'height':390})
   errors=[]
   for label,page in [('1P',a),('2P',b)]:page.on('pageerror',lambda exc,label=label: errors.append((label,str(exc))))
   await a.goto('http://127.0.0.1:18767/online.html',wait_until='domcontentloaded',timeout=30000)
   await b.goto('http://127.0.0.1:18767/online.html',wait_until='domcontentloaded',timeout=30000)
   await a.evaluate("showLobbySetup()")
   await a.evaluate("send('create')")
   await a.wait_for_function('window.room!==undefined && room.length===6',timeout=10000)
   code=await a.evaluate('room')
   await b.evaluate('showLobbySetup()')
   await b.evaluate('(code)=>send("join",{code})',code)
   await a.wait_for_timeout(200)
   await a.evaluate("send('select',{character:0})")
   await b.evaluate("send('select',{character:2})")
   await a.wait_for_timeout(200)
   await a.evaluate("send('ready')")
   await b.evaluate("send('ready')")
   await a.wait_for_timeout(1900)
   print('room',code,'sport',await a.evaluate('sport'),await b.evaluate('sport'))
   print('host frame',len(a.frames),'client frame',len(b.frames))
   print('client original controls',await b.frame_locator('#game').locator('#controls').evaluate('(e)=>getComputedStyle(e).display'))
   print('client remote buttons',await b.locator('#buttons').evaluate('(e)=>getComputedStyle(e).display'))
   await a.evaluate("send('complete',{sport:0,order:[0,2,1,3]})")
   await a.wait_for_timeout(350)
   print('race complete',await a.evaluate('finished'),await b.evaluate('finished'))
   await a.evaluate('advance()')
   await a.wait_for_timeout(1200)
   print('next sport',await a.evaluate('sport'),await b.evaluate('sport'))
   print('client original controls battle',await b.frame_locator('#game').locator('#controls').evaluate('(e)=>getComputedStyle(e).display'))
   print('errors',errors[:8]);await browser.close()
 finally:await runner.cleanup()
asyncio.run(main())
