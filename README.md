# Radar Oylut 2.0

Retorna somente links de matérias publicadas recentemente em:

- TH+ João Pessoa
- ClickPB
- Jornal da Paraíba

## Rotas

- `/` — estado da API
- `/saude` — verificação do serviço
- `/radar` — links das últimas 24 horas
- `/radar?horas=48` — período de teste
- `/radar?horas=24&limite=100` — limita a resposta

O coletor tenta RSS primeiro. Quando o portal não fornece um feed utilizável,
usa as páginas de últimas notícias e verifica a data dentro de cada matéria.

Falhas individuais de sites ou matérias são ignoradas para evitar erro 500.
