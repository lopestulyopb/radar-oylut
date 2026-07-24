function updateUsage(u){
  if(!usageCounter||!u)return;
  if(u.unlimited||usageCounter.dataset.unlimited==='true'){
    usageCounter.dataset.unlimited='true';
    usageCounter.dataset.remaining='999999';
    usageCounter.textContent='Pesquisas ilimitadas';
    usageCounter.classList.remove('limit-reached');
    return;
  }
  usageCounter.dataset.used=String(u.used);
  usageCounter.dataset.limit=String(u.limit);
  usageCounter.dataset.remaining=String(u.remaining);
  usageCounter.textContent=`${u.remaining} consulta(s) restante(s) hoje`;
  if(u.remaining<=0){button.disabled=true;usageCounter.classList.add('limit-reached')}
}
