/* Optional dashboard enhancement. Load after dashboard.js on dashboard.html. */
(function(){
  const api='/api/v1';
  async function addBuilderLink(){
    const token=localStorage.getItem('access_token')||localStorage.getItem('conversapay_auth_token');
    if(!token)return;
    try{const r=await fetch(`${api}/dashboard/features`,{headers:{Authorization:`Bearer ${token}`}});if(!r.ok)return;const f=await r.json();if(f.plan_type!=='premium')return;const nav=document.querySelector('.sidebar-nav, aside nav ul');if(!nav||document.getElementById('siteBuilderNavLink'))return;const li=document.createElement('li');const a=document.createElement('a');a.id='siteBuilderNavLink';a.href='/site-builder.html';a.textContent='✨ בונה אתרים';a.title='בונה אתרים למשתמשי PREMIUM';li.appendChild(a);nav.appendChild(li)}catch(_){}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',addBuilderLink);else addBuilderLink();
})();
