const button=document.getElementById('iniciar');
const copyButton=document.getElementById('copiar');
const status=document.getElementById('status');
const results=document.getElementById('resultados');
const resultFilter=document.getElementById('resultFilter');
const openMenuButton=document.getElementById('abrirMenu');
const closeMenuButton=document.getElementById('fecharMenu');
const sidebar=document.getElementById('sidebar');
const sidebarBackdrop=document.getElementById('sidebarBackdrop');
const editoriaAtual=document.getElementById('editoriaAtual');
const usageCounter=document.getElementById('usageCounter');
let currentNews=[];
let activeResultEditorial='todos';
let lastResearch=null;

const EDITORIA_LABELS={
  policial:'Policial',servico:'Serviço',saude:'Saúde',educacao:'Educação',economia:'Economia',
  geral:'Geral',esportes:'Esportes',cultura:'Cultura',meio_ambiente:'Meio Ambiente',
  politica:'Política',justica:'Justiça',institucional:'Institucional'
};
const EDITORIA_ORDER={policial:0,servico:1,saude:2,educacao:3,economia:4,justica:5,esportes:6,cultura:7,meio_ambiente:8,institucional:9,geral:10,politica:11};
const ORDER_LABELS={editor_chefe:'Padrão (peso jornalístico)',recentes:'Mais recentes'};

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
function singleArticleText(item){return `RADAR OYLUT\n\n${articleText(item)}`}
function researchHeader(news){
  const research=lastResearch||{performedAt:new Date(),hours:'24',editorias:'Todas',order:'editor_chefe'};
  const performedAt=research.performedAt instanceof Date?research.performedAt:new Date(research.performedAt);
  const date=performedAt.toLocaleDateString('pt-BR');
  const time=performedAt.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  const period=research.hours==='1'?'última 1 hora':`últimas ${research.hours} horas`;
  const resultFilterLabel=activeResultEditorial==='todos'?'':`\nFiltro dos resultados: ${EDITORIA_LABELS[activeResultEditorial]}`;
  return `RADAR OYLUT\n\nPESQUISA\nData: ${date}\nHora: ${time}\n\nPeríodo pesquisado: ${period}\nEditorias: ${research.editorias}\nOrdenação: ${ORDER_LABELS[research.order]||'Padrão (peso jornalístico)'}${resultFilterLabel}\nTotal de fatos: ${news.length}`;
}
function copyText(news){return `${researchHeader(news)}\n\n------------------------------\n\n${news.map((item,index)=>articleText(item,index)).join('\n\n------------------------------\n\n')}`}
async function copyWithFeedback(text,control,label){try{await navigator.clipboard.writeText(text);const original=control.textContent;control.textContent=label;control.classList.add('copied');setTimeout(()=>{control.textContent=original;control.classList.remove('copied')},1800)}catch(_){status.textContent='Não foi possível copiar automaticamente. Tente novamente pelo navegador.'}}
copyButton.addEventListener('click',()=>{const visible=filteredResultNews();if(visible.length)copyWithFeedback(copyText(visible),copyButton,'Resultados copiados ✓')});

function normalizeText(value){return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\s+/g,' ').trim()}
function hasAny(text,terms){return terms.some(term=>text.includes(term))}
function inferredEditorial(item){
  const title=normalizeText(item.titulo||item.title);
  const summary=normalizeText(item.resumo||item.summary);
  const text=`${title} ${summary}`;
  if(hasAny(title,['policia','prisao','preso','presa','prende','prendeu','suspeito','suspeita','foragido','foragida','homicidio','feminicidio','assassinato','tentativa de matar','assalto','roubo','furto','trafico','faccao','arma','municao','sequestro','estupro','atos obscenos','operacao policial','acidente','colisao','atropelamento','capotamento','capota','capotou','incendio','explosao'])||hasAny(text,['anuario de seguranca','capital mais violenta','criminalidade','violencia urbana']))return'policial';
  if(hasAny(text,['inmet','alerta laranja','alerta amarelo','alerta de chuva','chuvas intensas','ventos fortes','bolsa familia','calendario de pagamento','refis','renegociacao','inscricoes','prazo','concurso','concorrencia do concurso']))return'servico';
  if(hasAny(title,['justica','stf','stj','tribunal','juiz','juiza','sentenca','alvara de soltura','ajuiza','ajuizou','acao civil','queixa-crime','inquerito','mendonca autoriza']))return'justica';
  if(hasAny(title,['pre-candidatura','pre-candidato','pre-candidata','candidato ao governo','candidatura ao senado','convencao','chapa','eleicoes','senado'])||hasAny(text,['deputado','senador','vereador','prefeito','governador','partido politico']))return'politica';
  if(hasAny(text,['musica','cinema','cineasta','festival','show','teatro','livro','exposicao','televisao','tv arapuan','comunicador','apresentador']))return'cultura';
  if(hasAny(text,['imposto de renda','restituicao','mei','meis','microempreendedor','empreendedorismo','emprego','vagas de emprego','salario','preco','gasolina','credito','comercio','industria','construcao civil','turismo','voos','assentos']))return'economia';
  return'';
}
function isGenericIndex(item){const title=normalizeText(item.titulo||item.title);return title==='noticias da paraiba e do brasil'||title==='ultimas noticias da paraiba e do brasil'}
function normalizedEditorial(item){const inferred=inferredEditorial(item);if(inferred)return inferred;const value=String(item.classificacao_editorial||item.editoria||'geral').toLowerCase();return EDITORIA_ORDER[value]!==undefined?value:'geral'}
function editorialLabel(item){const key=normalizedEditorial(item);return EDITORIA_LABELS[key]||'Geral'}
function filterNews(news){const valid=news.filter(item=>!isGenericIndex(item));const selected=new Set(selectedEditorias());if(!selected.size)return valid;return valid.filter(item=>selected.has(normalizedEditorial(item)))}
function publishedTime(item){const time=new Date(item.publicado_em||0).getTime();return Number.isNaN(time)?0:time}
function priorityScore(item){const score=Number(item.prioridade_editorial||0);return Number.isFinite(score)?score:0}
function groupAndOrder(news,order){return [...news].sort((left,right)=>{const le=normalizedEditorial(left),re=normalizedEditorial(right);if(le==='politica'&&re!=='politica')return 1;if(re==='politica'&&le!=='politica')return-1;if(order==='recentes')return publishedTime(right)-publishedTime(left);return priorityScore(right)-priorityScore(left)||publishedTime(right)-publishedTime(left)})}
function filteredResultNews(){return activeResultEditorial==='todos'?currentNews:currentNews.filter(item=>normalizedEditorial(item)===activeResultEditorial)}

function renderSourceButtons(item){const c=document.createElement('div');c.className='sources-list';sortedSources(item).forEach(source=>{const name=source.nome||source.fonte||'Fonte';const url=source.link||source.url||'#';const link=document.createElement('a');link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.setAttribute('aria-label',`Abrir notícia no ${name}`);link.append(name,createText('span','external-icon','↗'));c.appendChild(link)});return c}
function renderArticle(noticia,index){const article=document.createElement('article');article.className='news-card';const meta=document.createElement('div');meta.className='news-meta';meta.appendChild(createText('span','rank',`${index+1}`));const editorial=normalizedEditorial(noticia);meta.appendChild(createText('span',`editorial-badge badge-${editorial}`,editorialLabel(noticia)));const published=formatDate(firstPublished(noticia));if(published)meta.appendChild(createText('span','published',published));const actions=document.createElement('div');actions.className='card-actions';const copy=createText('button','copy-article secondary','Copiar notícia');copy.type='button';copy.addEventListener('click',()=>copyWithFeedback(singleArticleText(noticia),copy,'Copiado ✓'));actions.appendChild(copy);article.append(meta,createText('h2','',noticia.titulo),createText('p','summary',noticia.resumo));article.appendChild(renderSourceButtons(noticia));article.appendChild(actions);return article}
function renderNews(news){const fragment=document.createDocumentFragment();news.forEach((noticia,index)=>fragment.appendChild(renderArticle(noticia,index)));return fragment}
function refreshRenderedResults(){const visible=filteredResultNews();results.innerHTML='';results.appendChild(renderNews(visible));copyButton.hidden=visible.length===0;status.textContent=activeResultEditorial==='todos'?`${visible.length} fato(s) encontrado(s). Ordenados por peso jornalístico.`:`${visible.length} fato(s) em ${EDITORIA_LABELS[activeResultEditorial]}.`}
function renderResultFilter(){
  resultFilter.innerHTML='';
  if(!currentNews.length){resultFilter.hidden=true;return}
  const available=[...new Set(currentNews.map(normalizedEditorial))].sort((a,b)=>EDITORIA_ORDER[a]-EDITORIA_ORDER[b]);
  const options=[['todos','Todos'],...available.map(key=>[key,EDITORIA_LABELS[key]])];
  options.forEach(([key,label])=>{const filterButton=createText('button',`result-filter-button secondary${key===activeResultEditorial?' active':''}`,label);filterButton.type='button';filterButton.addEventListener('click',()=>{activeResultEditorial=key;renderResultFilter();refreshRenderedResults()});resultFilter.appendChild(filterButton)});
  resultFilter.hidden=false;
}

button.addEventListener('click',async()=>{const horas=document.querySelector('input[name="horas"]:checked')?.value||'24';const ordenar=selectedOrder();const editoriasDaPesquisa=selectedEditoriasLabel();button.disabled=true;copyButton.hidden=true;currentNews=[];activeResultEditorial='todos';lastResearch=null;resultFilter.hidden=true;resultFilter.innerHTML='';status.textContent=`Buscando fatos de ${editoriasDaPesquisa.toLowerCase()}...`;results.innerHTML='';try{const response=await fetch(`/radar?horas=${encodeURIComponent(horas)}&editoria=todas&ordenar=${encodeURIComponent(ordenar)}`);if(response.status===401){location.href='/login';return}const payload=await response.json();if(response.status===403){status.textContent=payload.detail||'Consulte sua assinatura em Minha Conta.';return}if(response.status===429){updateUsage({used:payload.used,remaining:payload.remaining,limit:payload.limit});status.textContent=payload.detail||'Limite diário atingido.';return}if(!response.ok)throw new Error(payload.detail||'Falha ao executar o Radar.');currentNews=groupAndOrder(filterNews(payload.noticias||[]),ordenar);lastResearch={performedAt:new Date(),hours:horas,editorias:editoriasDaPesquisa,order:ordenar};updateUsage(payload.usage);renderResultFilter();refreshRenderedResults()}catch(error){status.textContent=error.message||'Não foi possível carregar as notícias.'}finally{const remaining=Number(usageCounter?.dataset.remaining??1);button.disabled=remaining<=0}});
updateEditoriaLabel();