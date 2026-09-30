(() => {
 const params=new URLSearchParams(location.search),sessionId=params.get('session_id');
 const $=id=>document.getElementById(id), t=(he,en)=>window.Talk2PayUX?.t(he,en)||he;
 const retry=document.createElement('button');retry.className='cp-button-secondary';retry.textContent=t('נסה שוב','Retry');retry.hidden=true;$('details').after(retry);
 const login=document.createElement('a');login.className='cp-button';login.textContent=t('התחברות להמשך האימות','Sign in to verify');login.href='/login?next='+encodeURIComponent(location.pathname+location.search);login.hidden=true;retry.after(login);
 function status(kind,title,message){$('title').textContent=title;$('description').textContent=message;$('statusBadge').className='status-pill '+kind;$('statusBadge').textContent=kind==='good'?t('אושר','Confirmed'):kind==='bad'?t('לא ניתן לאמת','Could not verify'):t('ממתין לאימות','Awaiting verification');$('statusText').textContent='';}
 let running=false;
 async function confirm(){if(running)return;running=true;retry.hidden=true;login.hidden=true;
 try{
  if(!sessionId){status('warn',t('לא ניתן לאמת את התשלום','Could not verify payment'),t('חסר מזהה תשלום. בדוק את הודעת ספק התשלום או חזור למסלולים.','The payment reference is missing. Check the provider email or return to plans.'));return;}
  const token=localStorage.getItem('access_token')||localStorage.getItem('conversapay_auth_token')||sessionStorage.getItem('access_token')||sessionStorage.getItem('conversapay_auth_token');
  if(!token){status('warn',t('נדרשת התחברות לאימות התשלום','Sign in to verify payment'),t('מצב התשלום טרם אומת. התחבר כדי להמשיך מאותה נקודה.','Payment is not verified yet. Sign in to continue here.'));login.hidden=false;return;}
  status('warn',t('בודקים את מצב התשלום','Checking payment status'),t('ממתינים לאישור מספק התשלום.','Waiting for confirmation from the payment provider.'));
  for(let attempt=0;attempt<8;attempt++){
   const response=await fetch('/api/v1/payments/confirm-session?session_id='+encodeURIComponent(sessionId),{headers:{Authorization:'Bearer '+token}});const data=await response.json().catch(()=>({}));
   if(response.status===401){status('warn',t('נדרשת התחברות מחדש','Please sign in again'),t('לא ניתן לאמת באמצעות ההתחברות הנוכחית.','Your current session cannot verify this payment.'));login.hidden=false;return;}
   if(!response.ok)throw Error(response.status>=500?t('השירות אינו זמין כרגע. נסה שוב.','The service is unavailable. Try again.'):t('לא ניתן לאמת את התשלום בחשבון זה.','Could not verify this payment for this account.'));
   if(data.confirmed){status('good',t('התשלום אושר בהצלחה','Payment confirmed'),data.plan_type?t('המסלול עודכן. אפשר לחזור ללוח הבקרה.','Your plan was updated. You can return to the dashboard.'):t('ספק התשלום אישר את התשלום.','The provider confirmed payment.'));return;}
   if(attempt<7)await new Promise(resolve=>setTimeout(resolve,1500));
  }
  status('warn',t('עדיין ממתינים לאישור התשלום','Still awaiting payment confirmation'),t('טרם התקבל אישור סופי. אין צורך לשלם שוב; אפשר לבדוק שוב מאוחר יותר.','No final confirmation yet. Do not pay again; check back later.'));retry.hidden=false;
 }catch(error){status('bad',t('לא ניתן לאמת כרגע','Could not verify right now'),error.message||t('בדוק את החיבור ונסה שוב.','Check your connection and retry.'));retry.hidden=false}
 finally{running=false;retry.disabled=false;}
 }
 retry.onclick=()=>{retry.disabled=true;confirm()};$('details').hidden=true;confirm();
})();
