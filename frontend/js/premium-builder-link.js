/* Load after dashboard.js on dashboard.html. */
(function(){
  const api='/api/v1';
  async function addBuilderLink(){
    const token=localStorage.getItem('access_token')||localStorage.getItem('conversapay_auth_token');
    if(!token)return;
    try{
      const r=await fetch(`${api}/dashboard/features`,{headers:{Authorization:`Bearer ${token}`}});
      if(!r.ok)return;
      const f=await r.json();
      if(f.plan_type!=='premium')return;
      const nav=document.querySelector('.sidebar-nav, aside nav ul');
      if(!nav||document.getElementById('siteBuilderNavLink'))return;
      const li=document.createElement('li'); const a=document.createElement('a');
      a.id='siteBuilderNavLink'; a.href=f.site_builder_url||'https://builder.conversapay.org/'; a.target='_blank'; a.rel='noopener'; a.textContent='✨ בונה אתרים';
      li.appendChild(a); nav.appendChild(li);
    }catch(_){}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',addBuilderLink);else addBuilderLink();
})();
