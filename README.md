# Radar Oylut — Etapa 3, Sprint 4.1

Versão 5.4.0.

## Portais ativos

- ClickPB
- Jornal da Paraíba
- MaisPB
- Polêmica Paraíba

Foram retirados WSCOM e G1 Paraíba.

## Novidades

- Menu lateral preparado para receber outras ferramentas.
- Filtro por editoria:
  - Todas as editorias
  - Segurança e trânsito
  - Serviço, saúde e educação
  - Esportes
  - Política e Justiça
  - Geral e entretenimento
- A tela inicial continua priorizando a seleção do período: 1h, 2h, 6h, 12h ou 24h.
- A editoria selecionada é enviada para o backend.
- O backend realiza uma pré-classificação antes de abrir cada matéria, reduzindo o número de páginas processadas quando há filtro.
- A classificação final é conferida após a leitura da matéria.
- Links das fontes continuam em botões.
- Ao copiar, as URLs completas continuam no texto.

## Execução

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Sprint 4.1

Fontes ativas: ClickPB, Jornal da Paraíba, MaisPB e Polêmica Paraíba. Patos Online e Diário do Sertão foram removidos para reduzir ruído, volume e tempo de processamento.
