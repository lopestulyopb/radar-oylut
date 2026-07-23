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

// A ordem dos blocos é fixa. Policial sempre abre o resultado.
const EDITORIA_ORDER={
  policial:0,servico:1,saude:2,educacao:3,economia:4,esportes:5,cultura:6,
  meio_ambiente:7,politica:8,justica:9,institucional:10,geral:11
};

const ORDER_LABELS={editor_chefe:'Padrão',recentes:'Mais recentes dentro de cada editoria'};
const PUBLIC_PERSON_TERMS=['ator','atriz','cantor','cantora','artista','cineasta','diretor','diretora','jornalista','reporter','apresentador','apresentadora','influenciador','influenciadora','empresario','empresaria','escritor','escritora','prefeito','ex-prefeito','governador','deputado','senador','vereador','politico','jogador','ex-jogador','esportista'];
const VIOLENT_DEATH_TERMS=['morto a tiros','morta a tiros','assassinado','assassinada','homicidio','feminicidio','latrocinio','chacina','corpo encontrado','morte violenta','morte suspeita'];
const POLICE_TERMS=['homicidio','feminicidio','latrocinio','chacina','assalto','roubo','furto','receptacao','trafico','drogas','arma','municoes','prisao','preso','presa','mandado','operacao policial','policia civil','policia militar','organizacao criminosa','faccao','sequestro','refem','estupro','atos obscenos','violencia domestica','golpe','fraude','desaparecido','desaparecida','acidente','atropelamento','colisao','capotamento','afogamento','incendio','explosao'];
const STATISTICS_TERMS=['anuario','ranking','levantamento','pesquisa aponta','dados mostram','registra alta','aumento de','queda de','taxa de','indice de','entre as cidades mais violentas'];

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
function articleText(item,index=null){const links=(item.fontes||[]).map(s=>`${s.nome}: ${s.link}`).join('\n');const published=formatDate(item.publicado_em);const prefix=index===null?'':`${index+1}. `;return `${prefix}${item.titulo}\n\n${item.resumo}${published?`\n\nPublicado: ${published}`:''}\n\nLinks:\n${links}`}
function copyText(news){return news.map((item,index)=>articleText(item,index)).join('\n\n------------------------------\n\n')}
async function copyWithFeedback(text,control,label){try{await navigator.clipboard.writeText(text);const original=control.textContent;control.textContent=label;control.classList.add('copied');setTimeout(()=>{control.textContent=original;control.classList.remove('copied')},1800)}catch(_){status.textContent='Não foi possível copiar automaticamente. Tente novamente pelo navegador.'}}
copyButton.addEventListener('click',()=>{if(currentNews.length)copyWithFeedback(copyText(currentNews),copyButton,'Resultados copiados ✓')});

function normalizedText(value){return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()}
function containsAny(text,terms){return terms.some(term=>text.includes(normalizedText(term)))}
function itemText(item){return normalizedText(`${item.titulo||''} ${item.resumo||''}`)}
function isPublicPersonDeath(text){return containsAny(text,['morre','morreu','morte','luto','falecimento'])&&containsAny(text,PUBLIC_PERSON_TERMS)&&!containsAny(text,VIOLENT_DEATH_TERMS)}
function isViolenceStatistics(text){return containsAny(text,STATISTICS_TERMS)&&containsAny(text,['violencia','crime','furto','roubo','homicidio','mortes violentas','cidade mais violenta'])}

// Classificação contextual: primeiro identifica exceções, depois o tema principal.
function normalizedEditorial(item){
  const text=itemText(item);
  const original=item.classificacao_editorial||'geral';

  if(isPublicPersonDeath(text)||isViolenceStatistics(text))return'geral';
  if(containsAny(text,['homenageia','homenagem','reconhecimento institucional','solenidade','recebe titulo','entrega medalha']))return'institucional';
  if(containsAny(text,['tse','stf','stj','tribunal','justica','juiz','juiza','sentenca','decisao judicial','acao judicial','aciona o','ministerio publico','mppb','mpf','condenacao','processo judicial']))return'justica';
  if(containsAny(text,['plano de saude','tea','autismo','vacina','vacinacao','hospital','doenca','surto','medicamento','atendimento medico','sus']))return'saude';
  if(containsAny(text,['estudante','estagio','escola','educacao','universidade','faculdade','enem','professor','aluno','matricula escolar','sindrome de down']))return'educacao';
  if(containsAny(text,['alerta de chuva','chuvas intensas','alerta amarelo','alerta laranja','inmet','falta de agua','falta de energia','abastecimento','interdicao','inscricoes abertas','cadastro','refis','renegociacao de dividas','vagas','concurso','curso gratuito']))return'servico';
  if(containsAny(text,POLICE_TERMS)||original==='seguranca'||original==='policial')return'policial';
  if(containsAny(text,['poluicao','esgoto','desmatamento','meio ambiente','ambiental','area de preservacao','fauna','flora']))return'meio_ambiente';
  if(containsAny(text,['economia','emprego','salario','preco','gasolina','inss','imposto','credito','comercio','industria']))return'economia';
  if(containsAny(text,['futebol','campeonato','torneio','botafogo-pb','botafogo pb','treze','campinense','volei','basquete']))return'esportes';
  if(containsAny(text,['cultura','festival','show','musica','teatro','cinema','livro','exposicao','sabadinho bom']))return'cultura';
  if(containsAny(text,['partido','eleicao','eleicoes','candidato','candidata','pre-candidato','pre candidata','chapa','vice','apoio politico','deputado','senador','vereador','governador','prefeito']))return'politica';
  return EDITORIA_ORDER[original]!==undefined?original:'geral';
}

function editorialLabel(item){const key=normalizedEditorial(item);return EDITORIA_LABELS[key]||'Geral'}
function filterNews(news){const selected=new Set(selectedEditorias());if(!selected.size)return news;return news.filter(item=>selected.has(normalizedEditorial(item)))}
function publishedTime(item){const time=new Date(item.publicado_em||0).getTime();return Number.isNaN(time)?0:time}
function priorityScore(item){const score=Number(item.prioridade_editorial||0);return Number.isFinite(score)?score:0}
function groupAndOrder(news,order){
  return [...news].sort((left,right)=>{
    const leftEditorial=normalizedEditorial(left);
    const rightEditorial=normalizedEditorial(right);
    const groupDifference=(EDITORIA_ORDER[leftEditorial]??99)-(EDITORIA_ORDER[rightEditorial]??99);
    if(groupDifference!==0)return groupDifference;
    if(order==='recentes')return publishedTime(right)-publishedTime(left);
    return priorityScore(right)-priorityScore(left)||publishedTime(right)-publishedTime(left);
  });
}

function renderSourceButtons(sources){const c=document.createElement('div');c.className='sources-list';(sources||[]).forEach(source=>{const link=document.createElement('a');link.href=source.link;link.target='_blank';link.rel='noopener noreferrer';link.setAttribute('aria-label',`Abrir notícia no ${source.nome}`);link.append(source.nome,createText('span','external-icon','↗'));c.appendChild(link)});return c}
function renderArticle(noticia,index){const article=document.createElement('article');article.className='news-card';const meta=document.createElement('div');meta.className='news-meta';meta.appendChild(createText('span','rank',`${index+1}`));const editorial=normalizedEditorial(noticia);meta.appendChild(createText('span',`editorial-badge badge-${editorial}`,editorialLabel(noticia)));const published=formatDate(noticia.publicado_em);if(published)meta.appendChild(createText('span','published',published));const actions=document.createElement('div');actions.className='card-actions';const copy=createText('button','copy-article secondary','Copiar notícia');copy.type='button';copy.addEventListener('click',()=>copyWithFeedback(articleText(noticia),copy,'Copiado ✓'));actions.appendChild(copy);article.append(meta,createText('h2','',noticia.titulo),createText('p','summary',noticia.resumo));article.appendChild(renderSourceButtons(noticia.fontes));article.appendChild(actions);return article}

button.addEventListener('click',async()=>{const horas=document.querySelector('input[name="horas"]:checked')?.value||'24';const ordenar=selectedOrder();button.disabled=true;copyButton.hidden=true;currentNews=[];status.textContent=`Buscando notícias de ${selectedEditoriasLabel().toLowerCase()}...`;results.innerHTML='';try{const response=await fetch(`/radar?horas=${encodeURIComponent(horas)}&editoria=todas&ordenar=${encodeURIComponent(ordenar)}`);if(response.status===401){location.href='/login';return}const payload=await response.json();if(response.status===403){status.textContent=payload.detail||'Consulte sua assinatura em Minha Conta.';return}if(response.status===429){updateUsage({used:payload.used,remaining:payload.remaining,limit:payload.limit});status.textContent=payload.detail||'Limite diário atingido.';return}if(!response.ok)throw new Error(payload.detail||'Falha ao executar o Radar.');currentNews=groupAndOrder(filterNews(payload.noticias||[]),ordenar);updateUsage(payload.usage);status.textContent=`${currentNews.length} fato(s) encontrado(s). Editorias agrupadas, com Policial no topo e ordenação ${ORDER_LABELS[ordenar].toLowerCase()}.`;copyButton.hidden=currentNews.length===0;const fragment=document.createDocumentFragment();currentNews.forEach((noticia,index)=>fragment.appendChild(renderArticle(noticia,index)));results.appendChild(fragment)}catch(error){status.textContent=error.message||'Não foi possível carregar as notícias.'}finally{const remaining=Number(usageCounter?.dataset.remaining??1);button.disabled=remaining<=0}});
updateEditoriaLabel();