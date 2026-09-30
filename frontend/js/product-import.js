/* Shared parsing and reporting for both catalog import entry points. */
(() => {
  'use strict';
  const aliases = {name:['name','productname','שם','שםהמוצר'],item_key:['itemkey','sku','code','productid','מזהה','מזההמוצר','מקט','מק״ט','מק"ט'],price:['price','amount','cost','מחיר','סכום'],description:['description','תיאור'],payment_link:['paymentlink','payment','קישורלתשלום','קישורתשלום'],is_active:['isactive','active','פעיל']};
  const clean = value => String(value??'').replace(/^\uFEFF/,'').trim();
  const key = value => clean(value).toLowerCase().replace(/[\s_-]+/g,'');
  const t = (he,en) => (localStorage.getItem('conversapay-language')||localStorage.getItem('talk2pay_language'))==='en'?en:he;
  function parse(rows,businessId,mapping=null) {
    const products=[],errors=[];
    rows.forEach((row,index)=>{
      const get=field=>mapping?row[mapping[field]]:row[Object.keys(row).find(k=>aliases[field].includes(key(k)))];
      const name=clean(get('name')),item_key=clean(get('item_key')),raw=clean(get('price')).replace(/₪/g,'').replace(/,/g,'');
      if(!Object.values(row).some(v=>clean(v)))return;
      const price=Number(raw);let reason='';
      if(!name||name.length>255)reason=t('שם מוצר חסר או ארוך מדי','Missing or overlong product name');
      else if(!item_key||item_key.length>100)reason=t('מק״ט חסר או ארוך מדי','Missing or overlong SKU');
      else if(!raw||!Number.isFinite(price)||price<0)reason=t('נדרש מחיר מספרי; אפס חייב להיכתב במפורש','A numeric price is required; enter zero explicitly');
      if(reason){errors.push({row:index+2,reason});return}
      products.push({row:index+2,payload:{business_id:String(businessId),name,item_key,price,currency:'ILS',description:clean(get('description'))||null,payment_link:clean(get('payment_link'))||null,is_active:!['false','0','no','לא'].includes(clean(get('is_active')).toLowerCase())}});
    });return {products,errors};
  }
  function report(root,result) {
    root.replaceChildren();root.setAttribute('aria-live','polite');
    const summary=document.createElement('p');summary.textContent=t(`נוספו ${result.created||0} מוצרים; ${result.errors.length} שורות דורשות טיפול.`,`Added ${result.created||0} products; ${result.errors.length} rows need attention.`);root.appendChild(summary);
    if(result.errors.length){const list=document.createElement('ul');result.errors.forEach(error=>{const item=document.createElement('li');const reasons={duplicate_in_file:t('מק״ט כפול בקובץ','Duplicate SKU in file'),already_exists:t('המוצר כבר קיים','Product already exists')};item.textContent=t('שורה ','Row ')+error.row+': '+(reasons[error.reason]||error.reason);list.appendChild(item)});root.appendChild(list)}
  }
  async function run(parsed,api,root) {
    const result={created:0,errors:[...parsed.errors]};
    for(let i=0;i<parsed.products.length;i+=500){
      const batch=parsed.products.slice(i,i+500);
      try{const data=await api('/products/bulk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(batch.map(x=>x.payload))});result.created+=Number(data.created||0);(data.errors||[]).forEach(error=>result.errors.push({...error,row:batch[error.row-1]?.row||error.row}));}
      catch(error){batch.forEach(x=>result.errors.push({row:x.row,reason:error.message||t('הייבוא נכשל','Import failed')}));parsed.products.slice(i+500).forEach(x=>result.errors.push({row:x.row,reason:t('לא נשלח עקב כשל בבקשה קודמת','Not sent after an earlier request failed')}));report(root,result);return result;}
      report(root,result);
    }report(root,result);return result;
  }
  window.Talk2PayImport={parse,report,run};
})();
