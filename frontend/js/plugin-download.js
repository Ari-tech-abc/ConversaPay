(() => {
 const root=document.querySelector('#panel-wordpress article');if(!root)return;
 const english=(localStorage.getItem('conversapay-language')||localStorage.getItem('talk2pay_language')||document.documentElement.lang)==='en';
 const button=document.createElement('button'),status=document.createElement('p');button.type='button';button.className='cp-button';button.style.minHeight='44px';button.textContent=english?'Download WordPress plugin':'הורדת תוסף WordPress';status.setAttribute('role','status');root.prepend(button,status);
 button.onclick=async()=>{button.disabled=true;status.textContent='';try{
  const token=localStorage.getItem('access_token')||sessionStorage.getItem('access_token')||localStorage.getItem('conversapay_auth_token')||sessionStorage.getItem('conversapay_auth_token');
  if(!token){location.href='/login?next='+encodeURIComponent('/setup-guide?tab=wordpress');return;}
  const headers={Authorization:'Bearer '+token},businesses=await fetch('/api/v1/businesses',{headers});if(!businesses.ok)throw Error();const rows=await businesses.json();if(!rows[0]?.id)throw Error();
  const response=await fetch('/api/v1/payments/wordpress-plugin/'+encodeURIComponent(rows[0].id),{headers});if(!response.ok)throw Error();
  const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='conversapay-chat.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  status.textContent=english?'Install the ZIP under Plugins → Add New → Upload Plugin.':'התקינו את קובץ ה־ZIP דרך Plugins → Add New → Upload Plugin.';
 }catch(_){status.textContent=english?'Download failed. Sign in and try again.':'ההורדה נכשלה. יש להתחבר ולנסות שוב.';}finally{button.disabled=false;}};
})();
