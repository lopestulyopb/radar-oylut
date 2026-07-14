# Radar Oylut 1.1

API simples que consulta TH+ João Pessoa, ClickPB e Jornal da Paraíba.

A rota `/radar`:

1. coleta links candidatos nas páginas dos portais;
2. abre cada matéria;
3. extrai a data de publicação por metadados ou JSON-LD;
4. mantém apenas publicações das últimas 24 horas;
5. retorna somente uma lista de URLs.

Exemplo:

`/radar`

Período alternativo para teste:

`/radar?horas=48`
