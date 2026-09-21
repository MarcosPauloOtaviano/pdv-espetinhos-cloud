# Exclusão de Usuários Inativos e Endurecimento de Regressões Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Excluir usuários inativos com autorização real e corrigir os fluxos de salvamento e QR sem quebrar o isolamento multiestabelecimento.

**Architecture:** O Edge Function administrativo existente receberá uma operação explícita de exclusão, usando `auth.admin.deleteUser` no servidor e validações de tenant antes da remoção. O frontend ganhará um helper testável para separar sucesso da mutação e falha de recarga; a tela de usuários e o editor de produtos usarão esse resultado sem apagar entradas quando houver erro.

**Tech Stack:** React 19, Vite 7, Supabase Auth/Edge Functions/Postgres, Node `node:test`, QRCode 1.5.4.

**Spec:** `docs/superpowers/specs/2026-09-20-user-deletion-and-regression-hardening-design.md`

## Global Constraints

- Exclusão somente de usuários inativos do estabelecimento do administrador.
- Nunca apagar produtos, categorias, estabelecimentos, configurações ou contadores.
- Nunca incluir service role, publishable key ou outros segredos no código cliente.
- Migrações e alterações de banco devem ser aditivas e preservar dados existentes.
- Validar 375px, 390px, 414px, tablet e desktop.

## Review Focus

- Usuário ativo ou superadmin enviado diretamente à função: deve ser recusado.
- Usuário de outro estabelecimento: deve ser recusado mesmo quando o chamador é superadmin, salvo operação explicitamente autorizada pela plataforma; a UI local nunca oferece esse alvo.
- Falha da mutação de produto/usuário: formulário permanece preenchido.
- Mutação concluída e `refreshAll` falhando: usuário recebe aviso de sincronização, não erro de salvamento.
- QR de comanda encerrada ou perfil sem permissão: acesso não aparece e RPC não é chamado pela interface.

### Task 1: Helpers de autorização e operação

**Files:**
- Modify: `cloud-pwa/src/lib/admin.js`
- Test: `cloud-pwa/src/lib/admin.test.js`
- Create: `cloud-pwa/src/lib/operations.js`
- Test: `cloud-pwa/src/lib/operations.test.js`

**Interfaces:**
- `canDeleteInactiveUser(target, caller)` returns boolean.
- `runMutationWithRefresh(action, refresh)` returns `{ result, refreshError }` and preserves a successful mutation result when refresh fails.

- [x] **Step 1: Write failing tests** for active/self/superadmin/cross-tenant deletion and mutation-success-refresh-failure.
- [x] **Step 2: Run the focused tests and confirm the expected failures.**
- [x] **Step 3: Implement the minimal pure helpers.**
- [x] **Step 4: Run focused tests and the complete JavaScript suite.**

### Task 2: Secure administrative user deletion

**Files:**
- Modify: `cloud-pwa/supabase/functions/admin-upsert-user/index.ts`

**Interfaces:**
- Request body `{ action: "delete_inactive", user_id: string }`.
- Success response `{ mode: "deleted", profile: { id, username, establishment_id } }`.
- Rejection response uses 4xx and Portuguese reason without leaking service credentials.

- [x] **Step 1: Add pure authorization assertions** for inactive same-tenant target and every forbidden target class.
- [x] **Step 2: Run the focused assertions and confirm the expected initial failure.**
- [x] **Step 3: Add the server-side branch using `auth.admin.deleteUser`, audit insertion, tenant validation, and a clear historical-cash blocker.**
- [x] **Step 4: Deploy the updated function through the authenticated Supabase project.**
- [x] **Step 5: Invoke it against a nonexistent UUID and verify a safe 4xx response without deleting any user.**

### Task 3: User-management UI

**Files:**
- Modify: `cloud-pwa/src/App.jsx`
- Modify: `cloud-pwa/src/styles.css`

**Interfaces:**
- Inactive rows expose `Excluir usuário`; active rows do not.
- Successful deletion refreshes the list and shows a success toast.

- [x] **Step 1: Add the failing helper assertions** for inactive-only visibility and busy-state copy.
- [x] **Step 2: Run the helper assertions red before implementation.**
- [x] **Step 3: Add confirmation, invocation, error handling, and accessible disabled state.**
- [x] **Step 4: Run the UI/unit suite and inspect the rendered panel at mobile and desktop widths.**

### Task 4: Save/QR regression fixes

**Files:**
- Modify: `cloud-pwa/src/App.jsx`
- Test: `cloud-pwa/src/lib/operations.test.js`

- [x] **Step 1: Add failing mutation/refresh assertions** for preserving form state when the refresh fails.
- [x] **Step 2: Run them red.**
- [x] **Step 3: Wire `runMutationWithRefresh` into `run`, clear forms only after a successful mutation, and keep QR URL/error state stable during asynchronous rendering.**
- [x] **Step 4: Run unit tests and build.**

### Task 5: Production smoke and visual stress QA

**Files:**
- No product files unless a verified contrast or responsive defect is found.

- [x] **Step 1: Run build, tests, `node --check public/sw.js`, and `git diff --check`.**
- [x] **Step 2: Verify production bundle points at the configured Supabase project.**
- [x] **Step 3: Inspect login, administration, inactive-user row, product editor, QR route, and queue at 375px, 390px, 414px, tablet, and desktop.**
- [x] **Step 4: Apply only defects reproduced by these checks, then rerun the full verification.**
- [x] **Step 5: Record the outcome in the central memory and report any remaining production-only blocker.**
