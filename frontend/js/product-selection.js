/* Selection survives pagination; deleting the whole catalog is an explicit scope. */
window.Talk2PayProductSelection = ({ getState, api, reload, note, tr }) => {
  const root = document.getElementById('products');
  const bar = document.createElement('div');
  bar.className = 'product-selection-bar';
  bar.setAttribute('role', 'group');
  bar.setAttribute('aria-label', tr('בחירת מוצרים', 'Product selection'));
  const pageLabel = document.createElement('label'), pageBox = document.createElement('input'), pageText = document.createElement('span');
  pageBox.type = 'checkbox';
  pageText.textContent = tr('בחירת העמוד', 'Select page');
  pageLabel.append(pageBox, pageText);
  const count = document.createElement('span');
  count.setAttribute('role', 'status');
  const all = document.createElement('button'), clear = document.createElement('button'), remove = document.createElement('button');
  [all, clear, remove].forEach(button => { button.type = 'button'; button.className = 'btn mini'; });
  all.textContent = tr('בחירת כל הקטלוג', 'Select entire catalog');
  clear.textContent = tr('ביטול הבחירה', 'Clear selection');
  remove.textContent = tr('מחיקת הנבחרים', 'Delete selected');
  remove.classList.add('product-delete-selected');
  bar.append(pageLabel, count, all, clear, remove);
  root.before(bar);
  const selected = new Set();
  let entireCatalog = false, busy = false, activeJob = null, restoring = false;
  const jobKey = () => 'talk2pay-product-delete-' + getState().business?.id;
  async function followJob(id) {
    activeJob = id; busy = true;
    localStorage.setItem(jobKey(), id);
    sync();
    try {
      let job;
      do {
        job = await api('/products/delete-jobs/' + encodeURIComponent(id));
        count.textContent = tr('נמחקו ' + job.deleted + ' מתוך ' + job.total, 'Deleted ' + job.deleted + ' of ' + job.total);
        if (job.status === 'pending') await new Promise(resolve => setTimeout(resolve, 1000));
      } while (job.status === 'pending');
      localStorage.removeItem(jobKey());
      selected.clear(); entireCatalog = false;
      await reload(1);
      note(job.status === 'completed' ? tr(job.deleted + ' מוצרים נמחקו', job.deleted + ' products deleted') : tr('המחיקה נעצרה אחרי ' + job.deleted + ' מוצרים. אפשר לבחור שוב את המוצרים שנותרו.', 'Deletion stopped after ' + job.deleted + ' products. Select the remaining products to retry.'), job.status !== 'completed');
    } catch (error) {
      if (error.status === 404) localStorage.removeItem(jobKey());
      note(error.status === 404 ? tr('משימת המחיקה לא נמצאה. יש לרענן את הקטלוג ולבדוק את המוצרים שנותרו.', 'Deletion job was not found. Refresh the catalog to check the remaining products.') : tr('לא ניתן לבדוק כרגע את התקדמות המחיקה. יש לרענן את הדף לפני ניסיון נוסף.', 'Deletion progress is unavailable. Refresh the page before trying again.'), true);
    } finally { activeJob = null; busy = false; sync(); }
  }
  function sync() {
    const state = getState(), total = entireCatalog ? state.productTotal : selected.size;
    if (!restoring && !activeJob && state.business && localStorage.getItem(jobKey())) {
      restoring = true;
      queueMicrotask(() => followJob(localStorage.getItem(jobKey())));
    }
    bar.hidden = !state.productTotal && !selected.size;
    count.textContent = total ? tr(total + ' מוצרים נבחרו', total + ' products selected') : tr('לא נבחרו מוצרים', 'No products selected');
    pageBox.checked = entireCatalog || (state.products.length > 0 && state.products.every(p => selected.has(p.id)));
    pageBox.indeterminate = !entireCatalog && state.products.some(p => selected.has(p.id)) && !pageBox.checked;
    pageBox.disabled = busy || entireCatalog || !state.products.length;
    all.disabled = busy || entireCatalog || !state.productTotal;
    clear.disabled = busy || !total;
    remove.disabled = busy || !total;
    remove.textContent = busy ? tr('מוחק...', 'Deleting...') : tr('מחיקת הנבחרים', 'Delete selected');
    root.querySelectorAll('.item').forEach((row, index) => {
      const product = state.products[index];
      if (!product) return;
      let label = row.querySelector('.product-selection');
      if (!label) {
        label = document.createElement('label'); label.className = 'product-selection';
        const box = document.createElement('input'); box.type = 'checkbox'; box.dataset.selectProduct = product.id;
        box.setAttribute('aria-label', tr('בחירת ', 'Select ') + product.name);
        label.append(box); row.prepend(label);
      }
      const box = label.firstElementChild;
      box.checked = entireCatalog || selected.has(product.id);
      box.disabled = busy || entireCatalog;
      row.classList.toggle('product-selected', box.checked);
      row.querySelectorAll('button').forEach(button => button.disabled = busy);
    });
  }
  root.addEventListener('change', e => {
    const id = e.target.dataset.selectProduct;
    if (!id || busy) return;
    if (e.target.checked && selected.size >= 500) {
      e.target.checked = false;
      note(tr('אפשר לבחור עד 500 מוצרים, או לבחור את כל הקטלוג.', 'Select up to 500 products, or choose the entire catalog.'), true);
      return;
    }
    e.target.checked ? selected.add(id) : selected.delete(id);
    sync();
  });
  pageBox.onchange = () => {
    const products = getState().products;
    if (pageBox.checked && new Set([...selected, ...products.map(p => p.id)]).size > 500) {
      note(tr('אפשר לבחור עד 500 מוצרים, או לבחור את כל הקטלוג.', 'Select up to 500 products, or choose the entire catalog.'), true);
    } else products.forEach(p => pageBox.checked ? selected.add(p.id) : selected.delete(p.id));
    sync();
  };
  all.onclick = () => { entireCatalog = true; selected.clear(); sync(); };
  clear.onclick = () => { entireCatalog = false; selected.clear(); sync(); };
  remove.onclick = async () => {
    const state = getState(), expected = entireCatalog ? state.productTotal : selected.size;
    if (busy || !expected) return;
    const question = entireCatalog
      ? tr('למחוק את כל ' + expected + ' המוצרים בקטלוג? הפעולה סופית. הזמנות קיימות יישמרו.', 'Delete all ' + expected + ' products in the catalog? This cannot be undone. Existing orders will be retained.')
      : tr('למחוק את ' + expected + ' המוצרים שנבחרו? הפעולה סופית. הזמנות קיימות יישמרו.', 'Delete the ' + expected + ' selected products? This cannot be undone. Existing orders will be retained.');
    if (!confirm(question)) return;
    busy = true; sync();
    try {
      const result = await api('/products/bulk-delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ business_id: state.business.id, product_ids: [...selected], all_products: entireCatalog, expected_count: expected }) });
      if (result.job_id) { await followJob(result.job_id); return; }
      selected.clear(); entireCatalog = false;
      await reload(1);
      note(tr(result.deleted + ' מוצרים נמחקו', result.deleted + ' products deleted'));
    } catch (error) {
      const setupError = ['product_delete_schema_missing', 'product_delete_permissions_missing'].includes(error.code);
      note(setupError ? tr('שירות המחיקה דורש עדכון במסד הנתונים של האתר. יש לפנות למנהל האתר.', 'Deletion requires a site database update. Contact the site administrator.') : error.code === 'selection_changed' ? tr('הקטלוג השתנה. יש לרענן ולבחור מחדש לפני המחיקה.', 'The catalog changed. Refresh and select again before deleting.') : tr('לא התקבל אישור למחיקה. יש לרענן את הקטלוג לפני ניסיון נוסף.', 'Deletion was not confirmed. Refresh the catalog before trying again.'), true);
    } finally { busy = false; sync(); }
  };
  return { sync, forget(id) { selected.delete(id); sync(); } };
};
