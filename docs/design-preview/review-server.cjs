/* Local review of actual delivery pages. GET fixture data only; mutations disabled. */
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const fixture=spawnSync(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'tests/render_frontend_fixtures.py')],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
if(fixture.status!==0)throw Error(fixture.stderr);
const pages=JSON.parse(fixture.stdout);
const authPages=new Set(['dashboard','settings','profile','upgrade','setup-guide','wordpress','product-import','onboarding']);
const business={id:'local-demo-business',business_name:'הסטודיו של נועה'};
function fixtureData(endpoint){
 if(endpoint.startsWith('/site-builder/verify/'))return{valid:true};
 if(endpoint==='/businesses')return[business];
 if(endpoint==='/auth/me')return{email:'demo@example.com',email_verified:true,requires_business_onboarding:false,profile:{full_name:'נועה'}};
 if(endpoint==='/profile')return{email:'demo@example.com',profile:{full_name:'נועה',phone:'0500000000'}};
 if(endpoint==='/profile/notifications')return{preferences:{payment_success:true,weekly_digest:true,security_alerts:true,product_updates:false}};
 if(endpoint==='/dashboard/analytics')return{total_revenue:12480,closed_deals:48,total_conversations:326,conversion_rate:14.7};
 if(endpoint==='/dashboard/orders')return{orders:[{id:'1',order_number:'1048',customer_info:{name:'מאיה לוי'},status:'paid',total:249},{id:'2',order_number:'1047',customer_info:{name:'דניאל כהן'},status:'pending',total:580}]};
 if(endpoint==='/products/paged')return{products:[{id:'p',name:'תיק Everyday',item_key:'everyday_bag',price:249,is_active:true}],total:1,total_pages:1,page:1};
 return{keys:[],orders:[],plan_type:'pro',status:'active',sessions:[],usage:{used:2,limit:1000},limited:false,completed:false};
}
http.createServer((req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1:4319');
 res.setHeader('Cache-Control','no-store');
 if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(409,{'Content-Type':'application/json'});return res.end(JSON.stringify({detail:'תצוגת עיצוב בלבד. פעולות שמירה זמינות בסביבת האתר.'}));}
 if(url.pathname.startsWith('/api/v1/')){res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'});return res.end(JSON.stringify(fixtureData(url.pathname.slice(7))));}
 let name=url.pathname==='/'?'home':url.pathname.slice(1).replace(/\.html$/,'');
 if(name==='auth/callback')name='auth-callback';
 if(name==='payment/success')name='success';if(name==='payment/canceled')name='canceled';
 if(pages[name]){
  const session=authPages.has(name)?'<script>localStorage.setItem("access_token","local-design-preview");</script>':name==='site-builder'?'<script>sessionStorage.setItem("site_builder_token","local-builder-preview");</script>':['login','register'].includes(name)?'<script>if(localStorage.getItem("access_token")==="local-design-preview")localStorage.removeItem("access_token");</script>':'';
  const notice='<div style="background:#eef5e8;color:#596960;text-align:center;padding:7px 12px;font:12px/1.5 Rubik,Arial,sans-serif;border-bottom:1px solid #dce5d8">תצוגת עיצוב מקומית · נתוני המחשה · פעולות שמירה אינן פעילות</div>';
  let html=pages[name].replace('</head>',session+'</head>');html=html.replace(/(<body[^>]*>)/,'$1'+notice);
  res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});return res.end(html);
 }
 if(url.pathname.startsWith('/frontend/')){
  const file=path.resolve(root,'.'+decodeURIComponent(url.pathname));
  if(file.startsWith(path.join(root,'frontend')+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile()){
   const ext=path.extname(file);res.writeHead(200,{'Content-Type':ext==='.js'?'application/javascript':ext==='.css'?'text/css':ext==='.png'?'image/png':ext==='.svg'?'image/svg+xml':'application/octet-stream'});return res.end(fs.readFileSync(file));
  }
 }
 res.writeHead(404);res.end('Not found');
}).listen(4319,'127.0.0.1',()=>console.log('Full design review: http://127.0.0.1:4319'));
