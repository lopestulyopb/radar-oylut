# Radar Oylut

API para selecionar notícias de João Pessoa e da Paraíba publicadas nas últimas 24 horas, agrupar duplicidades e gerar uma leitura inicial voltada para telejornalismo.

## O que entrega

- recorte temporal estrito;
- fontes configuráveis e tolerância a falhas;
- deduplicação por similaridade de títulos;
- editoria e pontuação de potencial para TV;
- sugestões de fontes, personagem, imagens e próximos passos;
- OpenAPI automático para conectar a uma Ação de GPT.

## Estrutura

- `app/sources.py`: cadastro das fontes;
- `app/collectors/`: coletores RSS e HTML;
- `app/dedup.py`: agrupamento de notícias semelhantes;
- `app/tv.py`: análise editorial inicial;
- `app/service.py`: pipeline das últimas 24 horas;
- `app/main.py`: API FastAPI.

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Teste: `http://127.0.0.1:8000/radar?consulta=João%20Pessoa&horas=24&limite=20`

## Render

Crie um Web Service conectado ao repositório. O arquivo `render.yaml` já contém os comandos de build e inicialização.

## Observação editorial

O resultado é um radar de produção. Antes de exibir qualquer informação, abra os links, confirme os dados com fontes oficiais e verifique imagens, personagens e atualizações.
