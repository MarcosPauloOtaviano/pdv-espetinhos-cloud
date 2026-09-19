# PDV Espetinhos Cloud PWA

Plataforma em nuvem multiestabelecimento do PDV Espetinhos. Esta pasta nao substitui o sistema local
Python/SQLite: ela cria uma PWA independente, usando Supabase/PostgreSQL como
banco central para celular e computador.

## Arquitetura

- Frontend: React + Vite, responsivo e instalavel como PWA.
- Banco: Supabase PostgreSQL.
- Autenticacao: Supabase Auth.
- Sincronizacao: Supabase Realtime em tabelas de comandas, itens, pagamentos,
  caixa, produtos e configuracoes.
- Regras criticas: funcoes SQL transacionais no schema e nas migracoes de `supabase/migrations/`.
- Multiestabelecimento: isolamento por `establishment_id` com RLS, validacao por
  trigger e estabelecimento derivado da sessao autenticada.

O celular e o computador acessam o mesmo link publicado. Nenhum dispositivo
depende do outro estar ligado.

## Primeira instalacao

1. Crie um projeto no Supabase.
2. Copie `.env.example` para `.env` e preencha:

```env
VITE_SUPABASE_URL=https://SEU-PROJETO.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=SUA_CHAVE_PUBLICAVEL
SUPABASE_SERVICE_ROLE_KEY=SUA_SERVICE_ROLE_KEY_SECRETA
DATABASE_URL=postgresql://postgres.SEU-PROJETO:SUA-SENHA@aws-0-regiao.pooler.supabase.com:6543/postgres?sslmode=require
```

As duas primeiras variaveis sao publicas e entram no app. `SUPABASE_SERVICE_ROLE_KEY`
e `DATABASE_URL` sao usadas somente nos scripts de instalacao deste computador.
Nao publique essas duas chaves no navegador.

3. Revise `scripts/setup-users.json` e troque as senhas temporarias se desejar.
4. Instale as dependencias:

```bash
npm install
```

5. Aplique o banco e crie os usuarios:

```bash
npm run setup:all
```

Tambem e possivel rodar em partes:

```bash
npm run setup:check
npm run setup:schema
npm run setup:users
```

6. Rode localmente:

```bash
npm run dev
```

## Build

```bash
npm run build
```

A pasta `dist/` gerada pode ser publicada em Netlify, Vercel, Cloudflare Pages
ou qualquer hospedagem estatica HTTPS. HTTPS e importante para PWA no celular.

Esta pasta ja contem `vercel.json` e `netlify.toml` para publicar como site
estatico. Na hospedagem, configure apenas:

```env
VITE_SUPABASE_URL=https://SEU-PROJETO.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=SUA_CHAVE_PUBLICAVEL
```

## Acesso e usuarios

- Usuario admin: `admin`
- A senha inicial fica somente no arquivo local ignorado
  `scripts/setup-users.json` e deve ser trocada no primeiro acesso.
- O admin tem controle total: comandas, caixa, produtos, relatorios,
  configuracoes e usuarios.
- O super admin cadastra estabelecimentos e seus administradores. O admin de
  cada estabelecimento cria operadores que herdam automaticamente o mesmo
  estabelecimento.
- Para criar ou atualizar usuarios pelo app: entre como admin, abra
  `Configuracoes` > `Usuarios`, preencha usuario, nome, senha e perfil.
  Se o usuario ja existir, o formulario atualiza nome, senha, perfil e status.
- A criacao de usuarios usa a Edge Function `admin-upsert-user`, publicada no
  Supabase com JWT obrigatorio e liberada apenas para admin.

## Comanda digital do cliente

Na comanda aberta, a equipe encontra **Acesso do cliente → Gerar acesso do cliente**.
O QR Code abre `/#/comanda/<credencial>` na mesma URL da aplicação, sem login.
O cliente acompanha itens/total, monta novos pedidos com observações, chama o
atendente e solicita fechamento. Os pedidos usam os preços cadastrados no banco,
entram na mesma comanda e geram uma solicitação na fila FIFO em uma transação.

- Enquanto um pedido digital estiver **pendente**, o cliente pode alterá-lo ou
  cancelá-lo por completo. Ao aceitar a solicitação na fila, os itens passam para
  **Em preparo** e o link do cliente não pode mais removê-los nem alterá-los.
- Linhas já existentes não são removidas pelo cliente, mesmo que o QR Code seja
  compartilhado. Uma correção posterior é exclusiva do administrador: ele escolhe
  o item/quantidade (ou remoção) e informa uma justificativa obrigatória, que fica
  em `audit_logs`.
- A equipe de cozinha também pode acessar a fila. O aceite da próxima solicitação
  é o evento que protege o pedido do cliente contra novas alterações.

- Mostrar o QR novamente conserva o acesso; gerar outro invalida o anterior.
- Revogação, expiração (24 horas), cancelamento e pagamento impedem o acesso.
- Só a equipe autorizada do estabelecimento gerencia credenciais.
- A tabela de credenciais fica no schema privado, com RLS e sem leitura pelos clientes.
- A API pública recebe somente a credencial e valida o estabelecimento da comanda;
  não aceita preços ou identificação de estabelecimento enviados pelo cliente.
- Reenvio usa identificador único para evitar duplicação de itens e eventos na fila.
- A tela pública usa um cliente anônimo independente da sessão da equipe.
- A equipe recebe eventos pelo Realtime existente; a tela do cliente atualiza
  automaticamente a cada cinco segundos (30 segundos em segundo plano).
- No link temporário, o servidor e o túnel precisam permanecer ativos. Uma URL
  permanente é necessária para uso diário com QR Codes persistentes.

Aplicar `supabase/migrations/202609180001_digital_customer_access.sql` e depois
`supabase/migrations/202609190001_customer_order_controls.sql`, uma vez cada, após
as migrações anteriores. A CLI não estava instalada nesta sessão; as migrações são
mantidas no repositório e podem ser aplicadas no SQL Editor autenticado.
`supabase/tests/customer_access.sql` verifica acesso anônimo, isolamento, preços,
estoque, repetição de envio, edição/cancelamento pendente, bloqueio após aceite,
auditoria administrativa, fila, renovação, revogação, expiração e encerramento,
com dados temporários revertidos ao final. O teste usa a conta Ronaldo e dois
estabelecimentos já configurados, sem gravar credenciais.

Fiado foi removido das ações da PWA e novas alterações para esse status são
bloqueadas pelo banco. O histórico oculta cancelamentos sem itens, inclusive
na contagem de canceladas; os registros técnicos continuam disponíveis para auditoria.

## Fila de atendimento

- Pedidos digitais, chamados de garcom e solicitacoes de fechamento entram na
  tabela `service_queue`.
- O RPC `claim_next_service_request()` usa ordem por data/hora e bloqueio
  concorrente, garantindo que a solicitacao pendente mais antiga seja atendida
  primeiro dentro do estabelecimento.
- Eventos sao transmitidos por Realtime somente para o estabelecimento da
  sessao e geram aviso visual; o som e habilitado pelo operador no navegador.

## Regras de caixa

- Existe apenas um caixa aberto por vez, garantido por indice unico parcial.
- Pagamentos so finalizam se existir caixa aberto.
- Finalizar pagamento recalcula total no banco, insere pagamentos, baixa
  estoque e vincula a comanda ao caixa em uma unica transacao.
- Fechamento calcula total vendido, dinheiro esperado, Pix, cartoes, misto,
  sangrias, reforcos, comandas abertas/canceladas/fiado, top produtos e
  usuarios vendedores.

## Offline

Esta versao funciona online. O service worker faz cache apenas da casca do
app. Chamadas ao Supabase nao sao cacheadas.

Se a internet cair, o app mostra aviso e o usuario deve aguardar para operar
vendas/pagamentos. Isso evita:

- Duas comandas com o mesmo numero.
- Fechamento de caixa incompleto.
- Estoque divergente.
- Pagamento duplicado.
- Dois usuarios editando a mesma comanda sem transacao central.

Offline-first pode ser feito no futuro com fila local, UUIDs, reconciliacao e
regras de conflito, mas para PDV pequeno a opcao mais segura e bloquear
operacoes criticas sem internet.

## Migracao do SQLite local

1. Feche o sistema desktop antigo.
2. Rode o exportador:

```bash
python scripts/export_sqlite_to_csv.py --db ../dist/DUDAIR-PDV/data/database.db --out ./migration-csv
```

3. Revise os CSVs gerados.
4. Importe primeiro categorias/produtos, depois caixas, comandas, itens,
   pagamentos e movimentos. Para operacao nova, normalmente vale migrar apenas
   produtos/configuracoes e manter historico antigo em backup/CSV.

## Backup

Use os backups do Supabase:

- Backups diarios do projeto.
- Point-in-time recovery em plano pago.
- Exportacoes CSV de relatorios pelo app.

Tambem mantenha uma rotina mensal de exportacao dos relatorios de caixa.

## O que foi preservado do sistema atual

- Modelo de comandas, itens, produtos, pagamentos e caixa.
- Geracao de Pix copia-e-cola.
- Visual escuro com laranja/dourado.
- Regras de pagamento misto, dinheiro com troco, Pix, debito e credito.
- Auditoria de operacoes importantes.

## O que mudou

- SQLite local deixa de ser a fonte principal.
- O computador deixa de ser servidor.
- O app desktop passa a ser legado; celular e computador usam o mesmo PWA.
- Sincronizacao passa a acontecer por Supabase Realtime.
