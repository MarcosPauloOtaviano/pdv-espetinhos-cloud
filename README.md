# DUDAIR-PDV — Espetinho DU'DAIR

## Versao ativa: local / SQLite

A versao ativa deste projeto e a aplicacao local descrita abaixo: servidor
FastAPI, painel desktop, PWA na rede local e banco SQLite. Ela nao depende de
Supabase nem de outro banco externo.

O diretorio `cloud-pwa/` permanece apenas como componente experimental
separado e nao participa da execucao, dos dados ou do processo de build da
versao local.

Sistema de comandas e fechamento de caixa para o Espetinho DU'DAIR, com
**sincronizacao em tempo real entre o computador do caixa e os celulares dos
garcons/cozinha**, tudo na mesma rede Wi-Fi.

Continua sendo **um programa so** no computador: ao abrir o `DUDAIR-PDV.exe`,
ele sobe sozinho um servidor local (FastAPI + WebSocket) que e o unico dono do
banco SQLite, e abre a janela do caixa (CustomTkinter) — que fala com esse
servidor exatamente como um celular falaria. Os celulares acessam o mesmo
servidor por uma PWA (instalavel na tela inicial), pela rede Wi-Fi local.

- Backend: Python + FastAPI + WebSocket (embutido, roda em background thread)
- Painel do caixa (computador): CustomTkinter (Tkinter), fala com o servidor via HTTP/WS
- App do garcom/cozinha (celular): PWA (HTML/CSS/JS puro), instalavel na tela inicial
- Banco de dados: SQLite local (arquivo `.db`), unico, dono e o servidor
- Empacotamento: PyInstaller (+ Inno Setup opcional para instalador)

---

## 1. Usuarios padrao (primeiro acesso)

| Usuario | Senha | Perfil | Uso tipico |
|---|---|---|---|
| `admin` | `admin123` | admin | computador — cadastros, caixa, relatorios, config |
| `caixa` | `caixa123` | caixa | computador — comandas e pagamentos |
| `garcom` | `garcom123` | garcom | celular (PWA) — anotar pedidos |
| `cozinha` | `cozinha123` | cozinha | celular (PWA) — fila da cozinha |

No primeiro login o sistema avisa para trocar a senha. Troque em
**Configuracoes > Usuarios > Trocar senha** (computador, so administrador).

---

## 2. Rodando em modo desenvolvimento (com Python instalado)

Pre-requisito: Python 3.10+ instalado no Windows.

```bat
cd dudair-pdv
pip install -r requirements.txt
python main.py
```

Isso ja sobe o servidor local **e** abre a janela do caixa. O banco de dados
e criado automaticamente na primeira execucao, junto com categorias e
produtos de exemplo (espetinhos, bebidas, marmitas, porcoes, adicionais) e os
usuarios padrao da tabela acima.

---

## 3. Acesso pelo celular (garcom / cozinha) — PWA

Com o programa aberto no computador (o servidor sobe automaticamente):

1. **Descubra o IP do computador**: abra o Prompt de Comando e rode `ipconfig`.
   Procure o "Endereco IPv4" da rede Wi-Fi/Ethernet (ex.: `192.168.0.15`).
   O proprio app tambem mostra esse endereco pronto em
   **Configuracoes > Rede/Celular** (com botao de copiar).
2. No celular, conecte na **mesma rede Wi-Fi** do computador.
3. Abra o navegador (Chrome/Safari) e acesse:
   `http://<ip-do-computador>:8765/app/`
4. Faca login com o usuario `garcom` (ou `cozinha`).
5. Para instalar como aplicativo: no menu do navegador, toque em
   **"Adicionar a tela inicial"** / **"Instalar app"**. Um icone do
   DUDAIR-PDV aparece na tela inicial, abrindo em tela cheia.

### Se o celular nao conseguir acessar

O Firewall do Windows pode bloquear a primeira vez. Na primeira execucao,
o Windows costuma perguntar "Permitir que o Python/DUDAIR-PDV acesse essa
rede?" — clique em **Permitir acesso** (marque ao menos "Rede privada").

Se a pergunta nao aparecer (ou foi negada por engano), libere manualmente
abrindo o Prompt de Comando **como Administrador** e rodando:

```bat
netsh advfirewall firewall add rule name="DUDAIR-PDV" dir=in action=allow protocol=TCP localport=8765
```

Confirme tambem que o celular e o computador estao na mesma rede (nao vale
uma rede convidado/isolada, e nem dados moveis no celular).

### Acesso digital do cliente à comanda

Administradores e garçons podem abrir uma comanda e usar **Acesso do cliente**
para gerar ou mostrar novamente um QR Code. O QR abre uma consulta daquela
mesma comanda, com itens e total atualizados, sem criar outra comanda.

- **Gerar novo QR Code** invalida imediatamente o QR anterior.
- **Revogar acesso** bloqueia o link atual sem fechar ou apagar a comanda.
- Itens, pedidos, descontos e total não são alterados pela troca da credencial.
- O cliente não pode gerar, regenerar ou revogar credenciais.
- O celular precisa alcançar o computador pela mesma rede local enquanto o
  DUDAIR-PDV estiver aberto.

---

## 4. Gerando o executavel (.exe)

Com o Python e as dependencias instaladas, basta rodar:

```bat
build.bat
```

Isso instala as dependencias (incluindo o servidor FastAPI/uvicorn e a PWA),
limpa builds antigos e gera a pasta:

```
dist/DUDAIR-PDV/
├── DUDAIR-PDV.exe      <- executavel principal (sem terminal preto)
├── data/               <- pasta onde o banco SQLite fica (modo portatil)
├── _internal/          <- bibliotecas do Python + arquivos da PWA empacotados
```

### Modo portatil (pendrive)

Copie a pasta inteira `dist\DUDAIR-PDV` para um pendrive. Em qualquer
computador Windows, abra a pasta e execute `DUDAIR-PDV.exe`. O banco de dados
fica dentro de `DUDAIR-PDV\data\database.db`, junto com o programa — nao
precisa instalar nada. Os celulares acessam normalmente pelo IP desse
computador (item 3 acima).

### Modo instalador (.exe de instalacao profissional)

1. Rode `build.bat` primeiro (para gerar `dist\DUDAIR-PDV`).
2. Instale o [Inno Setup](https://jrsoftware.org/isinfo.php) (gratuito).
3. Abra `installer\setup.iss` no Inno Setup Compiler e clique em **Compile**.
4. O instalador final aparece em `installer\Output\DUDAIR-PDV-Setup.exe`.

Ao instalar com esse instalador, o programa vai para
`Arquivos de Programas\DUDAIR-PDV` e cria atalhos no menu iniciar e,
opcionalmente, na area de trabalho. Como essa pasta normalmente e
somente-leitura para o usuario comum, o sistema detecta isso automaticamente
e passa a guardar o banco de dados em:

```
%LOCALAPPDATA%\DUDAIR-PDV\database.db
```

Voce **nao** precisa configurar nada disso manualmente — o programa decide
sozinho, na primeira execucao, onde gravar os dados (pasta `data` local se
for gravavel, ou `%LOCALAPPDATA%` caso contrario).

---

## 5. Onde fica o banco de dados

| Situacao | Local do banco |
|---|---|
| Rodando com `python main.py` (modo dev) | `<projeto>\data\database.db` |
| Executavel em pendrive / pasta gravavel | `<pasta do exe>\data\database.db` |
| Instalado via instalador (Program Files) | `%LOCALAPPDATA%\DUDAIR-PDV\database.db` |

Voce pode forcar um local especifico definindo a variavel de ambiente
`DUDAIR_DATA_DIR` antes de abrir o programa. Tambem e possivel trocar a porta
padrao (8765) com `DUDAIR_PORT`.

O banco **nunca e apagado automaticamente**. Comandas pagas, canceladas e
fechamentos de caixa ficam guardados para sempre no historico.

---

## 6. Backup (manual e automatico) e restauracao

O servidor faz **backup automatico a cada 30 minutos** sozinho, salvando em
`<pasta de dados>\backups\backup-dudair-AAAA-MM-DD-HH-MM.db` (mantem os 20
mais recentes). Nao precisa fazer nada para isso acontecer.

Alem disso, dentro do sistema (computador): **Configuracoes > Backup**.

- **Fazer backup agora**: escolha uma pasta (pode ser um pendrive) e o sistema
  salva um arquivo com data e hora, por exemplo:
  `backup-dudair-2026-07-06-21-30.db`
- **Restaurar backup**: escolha um arquivo `.db` de backup. O sistema faz uma
  copia de seguranca do banco atual antes de substituir, e depois troca os
  dados pelos do backup escolhido.

Para levar o sistema todo para outro computador:

1. Feche o programa.
2. Copie a pasta `data` (ou um dos backups) para um pendrive.
3. No computador novo, instale/abra o DUDAIR-PDV normalmente.
4. Va em **Configuracoes > Backup > Restaurar backup** e selecione o arquivo
   copiado.

---

## 7. Configurando a chave Pix

Va em **Configuracoes > Pix** e preencha:

- Chave Pix (CPF, CNPJ, e-mail, telefone ou chave aleatoria)
- Nome do recebedor (sem acentos, ate 25 caracteres)
- Cidade do recebedor (sem acentos, ate 15 caracteres)
- Descricao padrao da cobranca

O sistema gera o QR Code e o codigo "copia e cola" no padrao oficial do Banco
Central (EMV / BR Code), com CRC16 calculado automaticamente, para o valor
exato de cada comanda. O fluxo e manual: o cliente paga, o atendente confere
no aplicativo do banco e clica em **Confirmar pagamento Pix**. A estrutura
(`app/pix.py`) ja esta isolada para no futuro plugar uma API de pagamento
(Mercado Pago, Asaas, Gerencianet, PagSeguro) sem mudar o restante do sistema.

---

## 8. Perfis de usuario

- **admin** (computador): cadastra produtos, edita precos, fecha caixa, ve
  relatorios, altera configuracoes de Pix/rede e gerencia usuarios.
- **caixa** (computador, tambem funciona no celular): cria comandas,
  adiciona/remove itens, abre caixa, registra sangria/reforco e finaliza
  pagamentos.
- **garcom** (celular - PWA): abre comanda, adiciona/remove itens, altera
  quantidade, escreve observacao por item, consulta comandas abertas. Nao
  finaliza pagamento (isso e feito no caixa).
- **cozinha** (celular - PWA): ve a fila de itens pendentes de todas as
  comandas abertas e avanca o status (pendente → preparando → pronto →
  entregue).

Crie novos usuarios em **Configuracoes > Usuarios** (apenas administrador,
no computador).

---

## 9. Atalhos de teclado (computador)

| Tecla | Acao |
|---|---|
| F2 | Nova comanda |
| F3 | Consultar comanda |
| F4 | Focar busca de produto (dentro da comanda) |
| F8 | Finalizar comanda (dentro da comanda) |
| ESC | Fechar janela/modal atual |

---

## 10. Estrutura do projeto

```
dudair-pdv/
├── main.py                  # ponto de entrada: sobe o servidor + abre a janela
├── requirements.txt
├── build.bat                 # gera o executavel com PyInstaller
├── README.md
│
├── app/
│   ├── database.py           # schema SQLite + seed inicial
│   ├── services.py           # regras de negocio (comandas, caixa, auditoria, etc.)
│   ├── server.py               # servidor FastAPI + WebSocket (API para PWA e desktop)
│   ├── api_client.py            # cliente HTTP usado pela janela do caixa
│   ├── pix.py                     # geracao do Pix EMV/BR Code + QR Code
│   ├── backup.py                    # backup/restauracao do banco
│   └── utils.py                      # paths, IP da rede, formatacao, hash de senha
│
├── ui/                        # janela do caixa (computador)
│   ├── theme.py
│   ├── widgets.py
│   ├── ws_client.py             # cliente WebSocket do desktop (auto-atualizacao)
│   ├── login_window.py
│   ├── main_window.py
│   ├── dashboard_window.py
│   ├── comandas_window.py
│   ├── comanda_detalhe_window.py
│   ├── payment_dialog.py
│   ├── produtos_window.py
│   ├── caixa_window.py
│   ├── fechamento_window.py
│   ├── relatorios_window.py
│   └── configuracoes_window.py
│
├── webapp/                    # PWA do garcom/cozinha (servida pelo proprio servidor)
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.json
│   ├── sw.js
│   └── icons/
│
├── assets/
│   ├── logo.png
│   └── icons/app.ico
│
├── data/                      # banco SQLite + backups automaticos (criado sozinho)
│
└── installer/
    └── setup.iss              # script do Inno Setup
```

---

## 11. Regras de negocio importantes

- Comandas so podem ser finalizadas com pelo menos 1 item.
- Pagamento em dinheiro nao fecha com valor recebido menor que o total.
- Pagamento misto exige que a soma das formas seja igual ao total (tolerancia
  de 1 centavo).
- Vendas so podem ser finalizadas com o **caixa aberto**.
- Fechamento de caixa alerta se houver comandas em aberto (permite forcar,
  com confirmacao).
- Somente comandas com status **Paga** entram no total do fechamento de
  caixa. Canceladas e fiado/pendente ficam separadas.
- Baixa de estoque acontece automaticamente ao finalizar ou marcar uma
  comanda como fiado (o produto ja saiu do estoque fisico).
- Produtos ja vendidos alguma vez nao sao apagados de verdade (evita perder
  o historico) — sao apenas desativados.
- O servidor e o **unico dono do banco** — computador e celular sempre
  conversam com ele por API, nunca acessam o arquivo `.db` diretamente. Isso
  evita conflito quando duas pessoas mexem na mesma comanda ao mesmo tempo.
- Toda mudanca em comanda (item, quantidade, observacao, pagamento, caixa)
  fica registrada na tabela de auditoria com usuario, acao e horario.
- Todo registro tem data/hora de criacao e atualizacao.

---

## 12. Duvidas comuns

**O executavel abriu um terminal preto atras da janela.**
Isso nao deveria acontecer (o build usa `--windowed`). Se acontecer, confira
se o `build.bat` foi executado sem erros e gere novamente.

**O celular nao consegue acessar o endereco.**
Confira: (1) celular e computador na mesma rede Wi-Fi; (2) o Firewall do
Windows liberou o Python/DUDAIR-PDV (veja o item 3); (3) o endereco digitado
bate com o IP mostrado em Configuracoes > Rede/Celular, incluindo a porta
`:8765` e o `/app/` no final.

**Troquei de computador e os dados sumiram.**
O banco fica fora do `.exe`. Use **Configuracoes > Backup** no computador
antigo (ou pegue um arquivo da pasta `data\backups`), leve o arquivo `.db`
num pendrive e restaure no computador novo pela mesma tela.

**Posso ter mais de um computador servidor ao mesmo tempo?**
Nao — so um computador deve rodar o DUDAIR-PDV como servidor por vez (ele e o
unico dono do banco). Os celulares dos garcons/cozinha se conectam nesse
computador pela rede; eles nao precisam (nem devem) rodar o programa.
