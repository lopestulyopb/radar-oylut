const button=document.getElementById('iniciar');
const copyButton=document.getElementById('copiar');
const status=document.getElementById('status');
const results=document.getElementById('resultados');
const openMenuButton=document.getElementById('abrirMenu');
const closeMenuButton=document.getElementById('fecharMenu');
const sidebar=document.getElementById('sidebar');
const sidebarBackdrop=document.getElementById('sidebarBackdrop');
const editoriaAtual=document.getElementById('editoriaAtual');
const usageCounter=document.getElementById('usageCounter');
let currentNews=[];

const EDITORIA_LABELS={
  policial:'Policial',servico:'Serviço',saude:'Saúde',educacao:'Educação',economia:'Economia',
  geral:'Geral',esportes:'Esportes',cultura:'Cultura',meio_ambiente:'Meio Ambiente',
  politica:'Política',justica:'Justiça',institucional:'Institucional'
};
const EDITORIA_ORDER={policial:0,servico:1,saude:2,educacao:3,economia:4,justica:5,esportes:6,cultura:7,meio_ambiente:8,institucional:9,geral:10,politica:11};
const ORDER_LABELS={editor_chefe:'Padrão',recentes:'Mais recentes dentro de cada editoria'};

function selectedEditorias(){return Array.from(document.querySelectorAll('input[name="editoria"]:checked')).map(input=>input.value)}
function selectedOrder(){return document.querySelector('input[name="ordenar"]:checked')?.value||'editor_chefe'}
function selectedEditoriasLabel(){const editorias=selectedEditorias();return editorias.length?editorias.map(e=>EDITORIA_LABELS[e]).join(', '):'Todas'}
function updateEditoriaLabel(){editoriaAtual.textContent=`Editorias: ${selectedEditoriasLabel()}`}
function updateUsage(u){if(!usageCounter||!u)return;usageCounter.dataset.used=String(u.used);usageCounter.dataset.limit=String(u.limit);usageCounter.dataset.remaining=String(u.remaining);usageCounter.textContent=`${u.remaining} consulta(s) restante(s) hoje`;if(u.remaining<=0){button.disabled=true;usageCounter.classList.add('limit-reached')}}
function openSidebar(){sidebar.classList.add('open');sidebar.setAttribute('aria-hidden','false');sidebarBackdrop.hidden=false;requestAnimationFrame(()=>sidebarBackdrop.classList.add('visible'));openMenuButton.setAttribute('aria-expanded','true');document.body.classList.add('menu-open')}
function closeSidebar(){sidebar.classList.remove('open');sidebar.setAttribute('aria-hidden','true');sidebarBackdrop.classList.remove('visible');openMenuButton.setAttribute('aria-expanded','false');document.body.classList.remove('menu-open');setTimeout(()=>{sidebarBackdrop.hidden=true},180)}
openMenuButton.addEventListener('click',openSidebar);closeMenuButton.addEventListener('click',closeSidebar);sidebarBackdrop.addEventListener('click',closeSidebar);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeSidebar()});document.querySelectorAll('input[name="editoria"]').forEach(input=>input.addEventListener('change',updateEditoriaLabel));

function createText(tag,className,text){const e=document.createElement(tag);if(className)e.className=className;e.textContent=text;return e}
function formatDate(value){if(!value)return'';const d=new Date(value);if(Number.isNaN(d.getTime()))return'';return d.toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'})}
function sortedSources(item){return [...(item.fontes||[])].sort((a,b)=>String(a.nome||a.fonte||'').localeCompare(String(b.nome||b.fonte||''),'pt-BR',{sensitivity:'base'}))}
function firstPublished(item){return item.primeira_publicacao_em||item.publicado_em}
function articleText(item,index=null){const links=sortedSources(item).map(s=>`${s.nome||s.fonte}: ${s.link||s.url}`).join('\n');const published=formatDate(firstPublished(item));const prefix=index===null?'':`${index+1}. `;return `${prefix}${item.titulo}\n\n${item.resumo}${published?`\n\nPublicado: ${published}`:''}\n\nLinks:\n${links}`}
function copyText(news){return news.map((item,index)=>articleText(item,index)).join('\n\n------------------------------\n\n')}
async function copyWithFeedback(text,control,label){try{await navigator.clipboard.writeText(text);const original=control.textContent;control.textContent=label;control.classList.add('copied');setTimeout(()=>{control.textContent=original;control.classList.remove('copied')},1800)}catch(_){status.textContent='Não foi possível copiar automaticamente. Tente novamente pelo navegador.'}}
copyButton.addEventListener('click',()=>{if(currentNews.length)copyWithFeedback(copyText(currentNews),copyButton,'Resultados copiados ✓')});

function normalizedEditorial(item){const value=String(item.classificacao_editorial||item.editoria||'geral').toLowerCase();return EDITORIA_ORDER[value]!==undefined?value:'geral'}
function editorialLabel(item){const key=normalizedEditorial(item);return EDITORIA_LABELS[key]||'Geral'}
function filterNews(news){const selected=new Set(selectedEditorias());if(!selected.size)return news;return news.filter(item=>selected.has(normalizedEditorial(item)))}
function publishedTime(item){const time=new Date(item.publicado_em||0).getTime();return Number.isNaN(time)?0:time}
function priorityScore(item){const score=Number(item.prioridade_editorial||0);return Number.isFinite(score)?score:0}
function groupAndOrder(news,order){return [...news].sort((left,right)=>{const le=normalizedEditorial(left),re=normalizedEditorial(right);const gd=(EDITORIA_ORDER[le]??99)-(EDITORIA_ORDER[re]??99);if(gd!==0)return gd;if(order==='recentes')return publishedTime(right)-publishedTime(left);return priorityScore(right)-priorityScore(left)||publishedTime(right)-publishedTime(left)})}

function renderSourceButtons(item){const c=document.createElement('div');c.className='sources-list';sortedSources(item).forEach(source=>{const name=source.nome||source.fonte||'Fonte';const url=source.link||source.url||'#';const link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.setAttribute('aria-label',`Abrir notícia no ${name}`);link.append(name,createText('span','external-icon','↗'));c.appendChild(link)});return c}
function renderArticle(noticia,index){const article=document.createElement('article');article.className='news-card';const meta=document.createElement('div');meta.className='news-meta';meta.appendChild(createText('span','rank',`${index+1}`));const editorial=normalizedEditorial(noticia);meta.appendChild(createText('span',`editorial-badge badge-${editorial}`,editorialLabel(noticia)));const published=formatDate(firstPublished(noticia));if(published)meta.appendChild(createText('span','published',published));const actions=document.createElement('div');actions.className='card-actions';const copy=createText('button','copy-article secondary','Copiar notícia');copy.type='button';copy.addEventListener('click',()=>copyWithFeedback(articleText(noticia),copy,'Copiado ✓'));actions.appendChild(copy);article.append(meta,createText('h2','',noticia.titulo),createText('p','summary',noticia.resumo));article.appendChild(renderSourceButtons(noticia));article.appendChild(actions);return article}

function renderGroupedNews(news){const fragment=document.createDocumentFragment();let currentEditorial='';news.forEach((noticia,index)=>{const editorial=normalizedEditorial(noticia);if(editorial!==currentEditorial){currentEditorial=editorial;const section=document.createElement('section');section.className='editorial-section';section.dataset.editoria=editorial;section.appendChild(createText('h2','editorial-section-title',EDITORIA_LABELS[editorial]||'Geral'));fragment.appendChild(section)}fragment.lastElementChild.appendChild(renderArticle(noticia,index))});return fragment}

button.addEventListener('click',async()=>{const horas=document.querySelector('input[name="horas"]:checked')?.value||'24';const ordenar=selectedOrder();button.disabled=true;copyButton.hidden=true;currentNews=[];status.textContent=`Buscando fatos de ${selectedEditoriasLabel().toLowerCase()}...`;results.innerHTML='';try{const response=await fetch(`/radar?horas=${encodeURIComponent(horas)}&editoria=todas&ordenar=${encodeURIComponent(ordenar)}`);if(response.status===401){location.href='/login';return}const payload=await response.json();if(response.status===403){status.textContent=payload.detail||'Consulte sua assinatura em Minha Conta.';return}if(response.status===429){updateUsage({used:payload.used,remaining:payload.remaining,limit:payload.limit});status.textContent=payload.detail||'Limite diário atingido.';return}if(!response.ok)throw new Error(payload.detail||'Falha ao executar o Radar.');currentNews=groupAndOrder(filterNews(payload.noticias||[]),ordenar);updateUsage(payload.usage);status.textContent=`${currentNews.length} fato(s) encontrado(s). Fontes agrupadas em ordem alfabética.`;copyButton.hidden=currentNews.length===0;results.appendChild(renderGroupedNews(currentNews))}catch(error){status.textContent=error.message||'Não foi possível carregar as notícias.'}finally{const remaining=Number(usageCounter?.dataset.remaining??1);button.disabled=remaining<=0}});
updateEditoriaLabel();