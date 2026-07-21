const button = document.getElementById('iniciar');
const copyButton = document.getElementById('copiar');
const status = document.getElementById('status');
const results = document.getElementById('resultados');
const openMenuButton = document.getElementById('abrirMenu');
const closeMenuButton = document.getElementById('fecharMenu');
const sidebar = document.getElementById('sidebar');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');
const editoriaAtual = document.getElementById('editoriaAtual');
let currentNews = [];

const EDITORIA_LABELS = {
  todas: 'Todas as editorias',
  seguranca: 'Segurança e trânsito',
  servico: 'Serviço, saúde e educação',
  esportes: 'Esportes',
  politica: 'Política e Justiça',
  geral: 'Geral e entretenimento',
};

function selectedEditoria() {
  const selected = document.querySelector('input[name="editoria"]:checked');
  return selected ? selected.value : 'todas';
}

function updateEditoriaLabel() {
  editoriaAtual.textContent = `Editoria: ${EDITORIA_LABELS[selectedEditoria()]}`;
}

function openSidebar() {
  sidebar.classList.add('open');
  sidebar.setAttribute('aria-hidden', 'false');
  sidebarBackdrop.hidden = false;
  requestAnimationFrame(() => sidebarBackdrop.classList.add('visible'));
  openMenuButton.setAttribute('aria-expanded', 'true');
  document.body.classList.add('menu-open');
}

function closeSidebar() {
  sidebar.classList.remove('open');
  sidebar.setAttribute('aria-hidden', 'true');
  sidebarBackdrop.classList.remove('visible');
  openMenuButton.setAttribute('aria-expanded', 'false');
  document.body.classList.remove('menu-open');
  setTimeout(() => { sidebarBackdrop.hidden = true; }, 180);
}

openMenuButton.addEventListener('click', openSidebar);
closeMenuButton.addEventListener('click', closeSidebar);
sidebarBackdrop.addEventListener('click', closeSidebar);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeSidebar();
});
document.querySelectorAll('input[name="editoria"]').forEach(input => {
  input.addEventListener('change', () => {
    updateEditoriaLabel();
    closeSidebar();
  });
});

function createText(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

function articleText(item, index = null) {
  const sourceLines = (item.fontes || []).map(source => `${source.nome}: ${source.link}`).join('\n');
  const published = formatDate(item.publicado_em);
  const prefix = index === null ? '' : `${index + 1}. `;
  return `${prefix}${item.titulo}\n\n${item.resumo}${published ? `\n\nPublicado: ${published}` : ''}\n\nLinks:\n${sourceLines}`;
}

function copyText(news) {
  return news.map((item, index) => articleText(item, index)).join('\n\n------------------------------\n\n');
}

async function copyWithFeedback(text, control, successLabel) {
  try {
    await navigator.clipboard.writeText(text);
    const original = control.textContent;
    control.textContent = successLabel;
    control.classList.add('copied');
    setTimeout(() => {
      control.textContent = original;
      control.classList.remove('copied');
    }, 1800);
  } catch (_) {
    status.textContent = 'Não foi possível copiar automaticamente. Tente novamente pelo navegador.';
  }
}

copyButton.addEventListener('click', () => {
  if (currentNews.length) copyWithFeedback(copyText(currentNews), copyButton, 'Resultados copiados ✓');
});

function renderSourceButtons(sources) {
  const container = document.createElement('div');
  container.className = 'sources-list';
  (sources || []).forEach(source => {
    const link = document.createElement('a');
    link.href = source.link;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.setAttribute('aria-label', `Abrir notícia no ${source.nome}`);
    link.append(source.nome, createText('span', 'external-icon', '↗'));
    container.appendChild(link);
  });
  return container;
}

function renderArticle(noticia, index) {
  const article = document.createElement('article');
  article.className = 'news-card';

  const meta = document.createElement('div');
  meta.className = 'news-meta';
  meta.appendChild(createText('span', 'rank', `${index + 1}`));
  const published = formatDate(noticia.publicado_em);
  if (published) meta.appendChild(createText('span', 'published', published));

  const cardActions = document.createElement('div');
  cardActions.className = 'card-actions';
  const copyArticleButton = createText('button', 'copy-article secondary', 'Copiar notícia');
  copyArticleButton.type = 'button';
  copyArticleButton.addEventListener('click', () => copyWithFeedback(articleText(noticia), copyArticleButton, 'Copiado ✓'));
  cardActions.appendChild(copyArticleButton);

  article.append(meta, createText('h2', '', noticia.titulo), createText('p', 'summary', noticia.resumo));
  article.appendChild(renderSourceButtons(noticia.fontes));
  article.appendChild(cardActions);
  return article;
}

button.addEventListener('click', async () => {
  const selectedHours = document.querySelector('input[name="horas"]:checked');
  const horas = selectedHours ? selectedHours.value : '24';
  const editoria = selectedEditoria();
  button.disabled = true;
  copyButton.hidden = true;
  currentNews = [];
  status.textContent = `Buscando notícias de ${EDITORIA_LABELS[editoria].toLowerCase()}...`;
  results.innerHTML = '';

  try {
    const response = await fetch(`/radar?horas=${encodeURIComponent(horas)}&editoria=${encodeURIComponent(editoria)}`);
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (!response.ok) throw new Error('Falha ao executar o Radar.');
    currentNews = await response.json();
    status.textContent = `${currentNews.length} fato(s) encontrado(s) em ${EDITORIA_LABELS[editoria].toLowerCase()}, organizados por relevância.`;
    copyButton.hidden = currentNews.length === 0;
    currentNews.forEach((noticia, index) => results.appendChild(renderArticle(noticia, index)));
  } catch (error) {
    status.textContent = error.message || 'Não foi possível carregar as notícias.';
  } finally {
    button.disabled = false;
  }
});

updateEditoriaLabel();
