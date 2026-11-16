/* Verified account-scoped summaries; provider IDs and card data stay private. */
(() => {
  let state = null, history = null, historyError = false, busy = false;
  const el = id => document.getElementById(id);
  const en = () => document.documentElement.lang === 'en';
  const t = (he, english) => en() ? english : he;
  const fmt = value => value ? new Date(value).toLocaleDateString(en() ? 'en-GB' : 'he-IL') : '—';
  function draw() {
    el('billingTitle').textContent = t('ניהול חיובים', 'Billing management');
    el('historyTitle').textContent = t('היסטוריית חיובים', 'Billing history');
    el('historyNote').textContent = t('מוצגים חיובים שאומתו במערכת. רשימה זו אינה חשבונית מס.', 'Only verified billing records are shown. This list is not a tax invoice.');
    el('planRequestLabel').textContent = t('בקשת שינוי מסלול', 'Request a plan change');
    el('planRequestHelp').textContent = t('הבקשה דורשת אישור מהספק. עד לאישור, המסלול והחיוב נשארים כפי שהם.', 'Provider confirmation is required. Your current plan and billing remain in effect until then.');
    el('requestPlanChange').textContent = t('שמירת בקשה', 'Save request');
    el('withdrawPlanChange').textContent = t('ביטול בקשת שינוי', 'Withdraw request');
    if (state) {
      el('billingState').textContent = state.next_billing_at
        ? t('מועד חידוש צפוי: ', 'Expected renewal date: ') + fmt(state.next_billing_at)
        : state.is_paid && !state.auto_renew
          ? t('החידוש האוטומטי בוטל. הגישה נשמרת עד ', 'Automatic renewal is canceled. Access remains until ') + fmt(state.subscription_end_date)
          : t('אין מועד חיוב הבא מאושר להצגה.', 'No confirmed next billing date is available.');
      el('billingAction').hidden = !state.payment_action_required;
      el('billingAction').textContent = t('חידוש המנוי לא הושלם. אין לפתוח מנוי נוסף. יש לפנות לתמיכה להסדרת התשלום; הגישה בתשלום נשמרת רק עד סוף התקופה ששולמה.', 'Renewal has not completed. Do not create another subscription. Contact support to resolve payment; paid access lasts only through the paid period.');
    }
    const pending = history?.plan_change_request;
    const latestCancellation = history?.cancellation;
    const cancellation = latestCancellation?.provider_subscription_id === state?.provider_subscription_id ? latestCancellation : null;
    el('cancellationState').hidden = !cancellation;
    if (cancellation) el('cancellationState').textContent = cancellation.status === 'confirmed'
      ? t('ביטול החידוש אושר ב־', 'Renewal cancellation confirmed on ') + fmt(cancellation.confirmed_at) + (cancellation.request_refund ? t('. בקשת ההחזר נרשמה לבדיקה; אין בכך אישור לביצוע החזר.', '. Refund review was requested; this does not confirm a refund.') : '')
      : t('בקשת ביטול החידוש ממתינה לאישור מהספק. הביטול טרם הושלם.', 'Renewal cancellation is awaiting provider confirmation. It has not completed.');
    el('planRequestArea').hidden = !state?.plan_change_request_available || !history || Boolean(pending);
    if (state && !pending) el('requestedPlan').value = state.plan_type === 'pro' ? 'premium' : 'pro';
    el('pendingPlanText').hidden = !pending;
    el('withdrawPlanChange').hidden = !pending;
    if (pending) el('pendingPlanText').textContent = t('בקשה למעבר למסלול ', 'Requested plan: ') + pending.requested_plan.toUpperCase() + t(' ממתינה לאישור. טרם נקבע מועד שינוי ולא בוצע חיוב בגינה.', ' — awaiting confirmation. No change date or charge has been applied.');
    el('requestPlanChange').disabled = busy;
    el('withdrawPlanChange').disabled = busy;
    const list = el('billingHistory');
    list.replaceChildren();
    if (!history || !history.invoices.length) {
      list.textContent = historyError ? t('לא ניתן לטעון את היסטוריית החיובים כרגע.', 'Billing history is temporarily unavailable.') : history ? t('אין עדיין חיובים מאומתים להצגה.', 'There are no verified billing records yet.') : t('טוען...', 'Loading…');
    } else for (const invoice of history.invoices) {
      const row = document.createElement('div');
      row.setAttribute('role', 'listitem');
      row.style.cssText = 'padding:14px 0;border-bottom:1px solid #e2e8e3;display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between';
      const status = document.createElement('span');
      status.textContent = fmt(invoice.occurred_at) + ' · ' + (invoice.status === 'paid' ? t('שולם', 'Paid') : t('התשלום לא הושלם', 'Payment not completed'));
      const amount = document.createElement('bdi');
      amount.dir = 'ltr';
      amount.textContent = new Intl.NumberFormat(en() ? 'en-GB' : 'he-IL', {style:'currency', currency:invoice.currency}).format(invoice.amount_minor / 100);
      row.append(status, amount);
      list.append(row);
    }
  }
  async function refresh() {
    try {
      const data = await api('/subscription/history');
      if (!Array.isArray(data.invoices)) throw Error('Invalid billing history');
      history = data; historyError = false;
    }
    catch { historyError = true; history = null; }
    draw();
  }
  async function mutate(path, options) {
    busy = true; draw();
    try {
      await api(path, options);
      await refresh();
    } catch (error) {
      toast(billingMessage(error.message) || t('לא ניתן לשמור את הבקשה כרגע. יש לבדוק את מצב המנוי ולנסות שוב.', 'The request could not be saved. Check your subscription and try again.'));
    } finally { busy = false; draw(); }
  }
  el('requestPlanChange').onclick = () => mutate('/subscription/plan-change', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({plan_type:el('requestedPlan').value})});
  el('withdrawPlanChange').onclick = () => {
    if (history?.plan_change_request) mutate('/subscription/plan-change/' + encodeURIComponent(history.plan_change_request.id), {method:'DELETE'});
  };
  window.addEventListener('billing-management-refresh', refresh);
  window.addEventListener('billing-status', event => { state = event.detail; draw(); });
  let lastLanguage = document.documentElement.lang;
  new MutationObserver(() => {
    if (document.documentElement.lang !== lastLanguage) {
      lastLanguage = document.documentElement.lang;
      draw();
    }
  }).observe(document.documentElement, {attributes:true, attributeFilter:['lang']});
  refresh();
})();
