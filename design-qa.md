# Design QA — refinamento visual do PDV

## Resultado final

**passed**

Nenhum problema P0, P1 ou P2 foi encontrado nas telas e estados validados.

## Verdade visual e escopo

- Referência estrutural: `/home/marcosotaviano/Documents/Projetos/Mercado_Colina/src/MercadoColina.Desktop/Styles/Colors.xaml`
- Referência de navegação: `/home/marcosotaviano/Documents/Projetos/Mercado_Colina/src/MercadoColina.Desktop/Shell/ShellView.xaml`
- Referência de dashboard: `/home/marcosotaviano/Documents/Projetos/Mercado_Colina/src/MercadoColina.Desktop/Admin/OverviewView.xaml`
- Referência de estoque: `/home/marcosotaviano/Documents/Projetos/Mercado_Colina/src/MercadoColina.Desktop/Admin/InventoryView.xaml`
- Implementação validada: `https://costa-recognize-pan-vacuum.trycloudflare.com/?v=refined`
- Captura principal: 1264 × 720 px. A densidade de pixels não é exposta pelo capturador do navegador.
- A comparação é direcional, não pixel a pixel: o Mercado Colina foi usado como referência de hierarquia, clareza e organização, preservando a identidade própria do PDV Espetinhos.

## Estados verificados

- Login da equipe, incluindo hierarquia do painel institucional e formulário.
- Dashboard autenticado do Espetinho do Ronaldo.
- Estoque autenticado, incluindo indicadores, categorias, formulário e listagem.
- Navegação Dashboard → Estoque.
- Logout e novo login com o administrador configurado.

## Comparação por região

| Região | Expectativa | Resultado |
| --- | --- | --- |
| Cabeçalho e navegação | Estrutura clara, leve e profissional | Navegação superior branca, marca, conta, alertas e saída com hierarquia consistente |
| Fundo e superfícies | Reduzir excesso de tons escuros | Fundo marfim quente e cartões brancos com bordas e sombras discretas |
| Ações principais | Boa leitura à distância e uso rápido no balcão | Blocos de ação com rótulo, título e cores semânticas distintas |
| Estoque | Informação operacional escaneável | Métricas no topo, formulários agrupados e listagem com contraste adequado |
| Login | Identidade acolhedora sem perder sobriedade | Painel couro/madeira à esquerda e formulário claro à direita |
| Estados de foco | Navegação por teclado perceptível | Anel de foco visível em botões, campos e links |

## Contraste

- Primária `#A85A2A` sobre branco: 5,05:1.
- Texto `#2B231E` sobre marfim `#F6F2EC`: 13,83:1.
- Texto secundário `#786B62` sobre branco: 5,15:1.
- Verde operacional `#35624B` sobre branco: 7,10:1.

## Observações de baixa prioridade

- As texturas de couro e mármore foram traduzidas em cor, profundidade e acabamento visual leve, sem imagens pesadas, para preservar desempenho e legibilidade.
- A validação inicial do painel administrativo foi feita no viewport de desktop disponível.

## Validação adicional — comanda digital (2026-09-18)

- Implementada a rota pública `/#/comanda/<credencial>`, com a mesma paleta clara, nome do estabelecimento, total, pedidos e cardápio.
- Captura visual da tela do cliente em 390 × 844 px: leitura, espaçamento e botões adequados ao celular.
- Verificados os tamanhos 375, 390, 414, 768 e 1280 px; nenhuma rolagem horizontal foi detectada.
- Testada a geração do QR Code no PDV e a abertura do link sem login de cliente.
- Seleção de produto atualiza o valor do carrinho; chamada de atendente aparece na fila da equipe sem recarregar a página.
- O cancelamento da comanda vazia encerra o acesso e remove a solicitação pendente da fila; essa comanda não aparece no relatório.
- Pedidos, preços, isolamento e ciclo de vida da credencial também foram verificados no banco em transação revertida; consulte `cloud-pwa/supabase/tests/customer_access.sql`.
