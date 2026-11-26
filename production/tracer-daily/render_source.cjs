// Public, unauthenticated source rendering; no supplier browser or login reuse.
const {chromium}=require('/tmp/wingman-site-qa/node_modules/playwright');
const allowed=new Set(['swing.vision','www.swing.vision','tenniscut.com','www.tenniscut.com','spintip.com','www.spintip.com','matchcutpro.com','www.matchcutpro.com','unforce.io','www.unforce.io']);
(async()=>{
 const target=new URL(process.argv[2]);if(target.protocol!=='https:'||!allowed.has(target.hostname)||target.username||target.password||target.port)throw Error('Unregistered rendering source');
 const browser=await chromium.launch({executablePath:'/var/lib/swi-codex/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome',headless:true,args:['--no-sandbox'],proxy:{server:process.env.ACECUT_SOURCE_PROXY||'http://127.0.0.1:7890'}});
 try{
  const context=await browser.newContext({acceptDownloads:false});let requests=0;
  await context.route('**/*',async route=>{const req=route.request();let u;try{u=new URL(req.url())}catch{return route.abort()}
   if(++requests>100||['image','media','font'].includes(req.resourceType())||u.protocol!=='https:'||u.port||/^(localhost|127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(u.hostname))return route.abort();
   if(req.isNavigationRequest()&&!allowed.has(u.hostname))return route.abort();return route.continue();
  });
  const page=await context.newPage();const response=await page.goto(target.href,{waitUntil:'domcontentloaded',timeout:30000});if(!response||response.status()!==200)throw Error('Source returned '+response?.status());
  await page.waitForFunction(()=>document.body.innerText.length>=500,{},{timeout:12000});
  const html=await page.content();if(Buffer.byteLength(html)>2000000)throw Error('Rendered document exceeds bound');
  console.log(JSON.stringify({http:200,url:page.url(),html,representation:'rendered_dom',requests}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e.name+': '+e.message);process.exitCode=1});
