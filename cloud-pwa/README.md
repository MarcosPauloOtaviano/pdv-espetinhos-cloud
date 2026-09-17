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
