# Exclusão segura de usuários inativos e endurecimento dos fluxos

## Objetivo

Permitir que um administrador remova definitivamente usuários inativos sem atravessar o isolamento entre estabelecimentos, preservar os cadastros do estabelecimento e eliminar as regressões observadas nos fluxos de salvamento e acesso digital.

## Escopo

- Usuários: exclusão disponível somente para perfis `active = false`, nunca para o próprio usuário, superadmin ou usuário de outro estabelecimento.
- Auth: a remoção deve usar a operação administrativa do Supabase Auth e registrar a ação antes da exclusão.
- Interface: botão de exclusão somente na linha inativa, confirmação explícita, estado ocupado e atualização da lista após sucesso.
- Salvamento: uma mutação bem-sucedida não deve ser apresentada como falha só porque a recarga posterior falhou; formulários não devem limpar os dados digitados quando a mutação falhar.
- QR: manter a implementação existente, adicionando testes de elegibilidade e erro; a opção continua limitada a perfis autorizados e comandas abertas.
- Visual: validar a paleta clara e o contraste nos breakpoints exigidos sem alterar cores persistidas durante os testes.

## Decisões técnicas

1. A exclusão ficará no Edge Function administrativo já usado para criar/atualizar usuários, aproveitando a chave de serviço apenas no servidor e a API oficial `auth.admin.deleteUser`.
2. Antes da exclusão, o servidor validará o chamador e o alvo, bloqueará perfis com histórico de abertura de caixa não anulável e limpará apenas referências históricas anuláveis, preservando registros operacionais futuros e a auditoria.
3. A função de operação do frontend será separada em resultado da mutação e resultado da recarga, permitindo feedback honesto e repetição segura.
4. A autorização do banco continuará sendo a fonte de verdade; filtros e botões da interface são apenas ergonomia.

## Critérios de aceite

- Usuário inativo do mesmo estabelecimento pode ser removido e deixa de aparecer na lista.
- Usuário ativo, próprio usuário, superadmin e usuário de outro estabelecimento são recusados sem alteração.
- Falha da API mantém o formulário de produto e usuário preenchido.
- Sucesso da mutação com falha de recarga retorna sucesso com aviso de sincronização, não erro falso.
- QR continua acessível apenas para comanda aberta e perfil autorizado.
- Testes, build, checagens de sintaxe e smoke test publicado passam.
