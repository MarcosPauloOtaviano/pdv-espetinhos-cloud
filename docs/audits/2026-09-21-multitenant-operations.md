# Auditoria operacional multiestabelecimento — 21/09/2026

## Escopo

- Ambiente auditado: produção, `https://cloudpdv.ddns.net`.
- Build identificado: Git `af6f76e` (`feat: renomear plataforma para CloudPDV`).
- Data/hora da execução: 21/09/2026, 12:39–12:43 (America/Sao_Paulo).
- Estabelecimentos simultâneos: **Du Dair** e **Bar do Bruninho**.
- Nenhuma comanda, pedido, pagamento, produto ou usuário de produção foi criado/alterado. As únicas mutações foram login e logout dos usuários de auditoria.
- As capturas visuais foram feitas durante esta execução em sessões independentes (in-app browser, Chrome e rota pública de cliente). Credenciais não foram registradas neste documento.

## Sessões e papéis exercitados

| Sessão | Papel | Resultado |
| --- | --- | --- |
| Du Dair | Atendente | Login, painel, fila, caixa somente leitura e estoque somente leitura |
| Bar do Bruninho | Administrador | Login, painel, administração, identidade visual, Pix e gestão de usuários |
| Cliente | Rota pública com token inválido | Tratamento seguro de acesso inválido/encerrado |

Também foi aberta uma segunda aba do aplicativo com a sessão administrativa do Du Dair para confirmar que a troca de contexto não mistura os dados. As sessões realmente independentes foram mantidas no in-app browser e no Chrome.

## Resultados

### Isolamento por estabelecimento — aprovado

Foram executados 16 verificações autenticadas em paralelo (login/perfil, RLS de `products`, `commands`, `service_queue`, `cash_movements` e `profiles`, leitura do próprio estabelecimento e rejeição de token inválido). **16/16 passaram.**

- Du Dair ficou vinculado ao estabelecimento `Du Dair`, papel `atendente`.
- Bar do Bruninho ficou vinculado ao estabelecimento `Bar do Bruninho`, papel `admin`.
- O atendente do Du Dair não conseguiu ler o estabelecimento, produtos, comandas, fila, caixa ou perfis do Bar do Bruninho.
- O administrador do Bar do Bruninho não conseguiu ler os dados do Du Dair.
- O administrador do Bar do Bruninho visualizou apenas o próprio estabelecimento na consulta de estabelecimentos.
- Contagens observadas sem vazamento: Du Dair (9 produtos, 3 perfis); Bar do Bruninho (1 perfil e nenhum produto/comanda/fila/movimento de caixa).

### Interface e permissões — aprovado com ressalva de cobertura

- O painel carregou o nome correto de cada estabelecimento e os indicadores de hoje zerados.
- O administrador do Bar do Bruninho acessou Administração, cores, Pix, criação de usuários e seleção dos perfis Administrador/Caixa/Atendente/Cozinha.
- O atendente do Du Dair não recebeu Relatórios, Administração ou Plataforma; Caixa e Estoque abriram em modo operacional sem ações administrativas.
- A fila exibiu explicitamente “Ordem FIFO” e a legenda de cores **Pedidos / Atendente / Fechamento**.
- A rota de cliente com credencial inválida mostrou “Acesso inválido ou encerrado” e não expôs dados.
- Não existe, no banco auditado, um usuário com papel `cozinha`; portanto o fluxo visual de cozinha não pôde ser exercitado com uma sessão real. O formulário administrativo oferece o perfil e o código contempla a permissão.

### Fila e simultaneidade — parcialmente comprovado

- As consultas de fila dos dois estabelecimentos foram feitas em paralelo, ordenadas por `requested_at` e `id`; ambas retornaram fila vazia e ordenação válida.
- O código e a tela exibem FIFO, filtro por tipo, busca rápida e cores por tipo.
- Como não havia solicitações pendentes e não foram criados registros de teste, não foi possível observar um evento Realtime real, a disputa entre dois atendentes ou a aceitação/ conclusão de um pedido em produção. Essa parte exige um ambiente de homologação ou autorização explícita para dados temporários.

### Cliente/comanda digital — parcialmente comprovado

- A rota pública foi carregada em uma aba separada e rejeitou token inválido com erro controlado (`P0001`).
- O fluxo com token válido, inclusão de item e alteração/cancelamento antes do aceite não foi disparado para não criar histórico de teste em produção.

## Achado crítico (P1 — corrigir antes de apresentar como produção)

O frontend publicado contém a chamada `cancel_command_with_reason`, mas o banco remoto auditado não possui essa função no cache do PostgREST:

```text
PGRST202: Could not find the function public.cancel_command_with_reason(p_command_id, p_reason)
```

A chamada foi verificada autenticada no Bar do Bruninho com um UUID inexistente (nenhuma linha foi alterada). A função legada `cancel_command` existe, mas o fluxo publicado que exige justificativa não conseguirá cancelar uma comanda com itens até a migração `cloud-pwa/supabase/migrations/20260921031840_command_cancel_reason.sql` ser aplicada no projeto Supabase correto e o schema cache ser recarregado.

**Ação recomendada:** aplicar essa migração no Supabase de produção, validar a função com uma comanda temporária de homologação e só então considerar o requisito de justificativa concluído. Não aplicar a migração por este relatório para evitar uma alteração estrutural sem a credencial/conector do projeto correto.

## Verificações técnicas adicionais

- `node --test src/lib/*.test.js`: **6/6 testes passaram**.
- Build Vite local: concluído; apenas aviso de bundle JavaScript acima de 500 kB (otimização futura, não falha funcional).
- Manifesto em produção: HTTP 200, nome `CloudPDV`, descrição de PDV em nuvem.
- Console do app no in-app browser: sem erros/avisos. Os avisos observados no Chrome vieram da extensão MetaMask, não do CloudPDV.

## Conclusão

O isolamento multiestabelecimento e o carregamento simultâneo de dois ambientes estão consistentes para leitura e navegação. O painel, fila vazia, permissões básicas e tratamento de token inválido se comportaram corretamente. A publicação **não deve ser considerada totalmente pronta** até aplicar e validar a migração da justificativa de cancelamento e realizar um ensaio controlado com dados temporários (pedido do cliente → fila → cozinha/atendente → aceite → pagamento) em pelo menos dois estabelecimentos.

