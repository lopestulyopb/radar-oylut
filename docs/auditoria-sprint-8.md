# Radar Oylut — Auditoria das Sprints 8.1 e 8.2

Data: 24/07/2026

## Alterações aplicadas

### Segurança e confiabilidade

- Cabeçalhos `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` e `Permissions-Policy`.
- `Cache-Control: no-store` para login, cadastro, conta e painel administrativo.
- Identificador individual por requisição (`X-Request-ID`).
- Registro estruturado de método, rota, status e tempo de resposta.
- Aviso de inicialização quando variáveis essenciais do Supabase estiverem ausentes.
- Normalização de chaves lidas das variáveis de ambiente com remoção de espaços e quebras de linha.
- Registro das exceções internas sem enviar detalhes sensíveis ao usuário.

### Performance

- Perfil e consumo diário carregados em paralelo na página inicial.
- Bloqueio por chave de cache para impedir várias coletas iguais ao mesmo tempo.
- Reaproveitamento do resultado caso outra requisição conclua a coleta primeiro.
- Falha de um portal não interrompe a coleta dos outros portais.
- Falha no enriquecimento de uma notícia não interrompe as demais.
- Atualização das métricas das fontes feita em paralelo.
- Limite defensivo de 240 candidatos por coleta para controlar memória e tempo.
- Validação e limites seguros para TTL do cache e limite diário.
- Tempo da pesquisa incluído no JSON como `elapsed_ms`.

## Riscos encontrados e tratados

1. Uma única fonte podia cancelar toda a pesquisa.
2. Pesquisas simultâneas iguais podiam disparar coletas duplicadas.
3. Configurações inválidas do banco podiam produzir valores inesperados.
4. Exceções eram ocultadas sem identificação suficiente nos logs.
5. Métricas das fontes eram atualizadas sequencialmente.
6. Perfil e consumo eram consultados um após o outro na página inicial.

## Validação que depende do ambiente de produção

- Confirmar que o Render iniciou com `app.main_v82:app`.
- Confirmar resposta HTTP 200 em `/saude`.
- Fazer login, abrir o Radar e executar pesquisas de 1h e 24h.
- Confirmar pesquisas ilimitadas para `lopestulyo@gmail.com`.
- Verificar nos logs a presença de `request_completed` e `elapsed_ms`.
- Abrir o painel administrativo e testar Fontes e Configurações.
- Fazer duas pesquisas iguais simultaneamente e confirmar que não ocorrem duas coletas completas.
- Observar se alguma fonte falha sem impedir a entrega das demais.

## Pontos não alterados automaticamente

- Políticas RLS do Supabase não foram modificadas sem teste direto no projeto.
- Não foram definidos tempos mínimos garantidos, pois dependem da rede e dos portais externos.
- Não foi introduzido Redis ou cache distribuído; o cache continua por instância do Render.
- Não foram alterados contratos de assinatura ou cobrança.
