# ⚡ Universo Elétrico — Instagram + robô de publicações

Este projeto contém **30 artes 1080×1350 px**, **30 legendas educativas**, logotipo, foto de perfil, calendário e um **publicador diário pela API oficial Meta**. O projeto começa em **modo seguro/desativado**. Nenhum post será enviado automaticamente até obter a autorização da API, revisar as artes e ativar o sistema.

## 1) O que está pronto

- `assets/logo-original.png` — logotipo da marca.
- `assets/foto-perfil.jpg` — arquivo para foto de perfil.
- `assets/grade-primeiros-9-posts.jpg` — prévia do feed.
- `content/calendario_30_dias.csv` — planejamento dos primeiros 30 dias.
- `content/posts.json` — assuntos, textos e legendas, em fila.
- `docs/posts/001.jpg` a `030.jpg` — posts preparados para o feed.
- `src/generate_art.py` — gerador local das artes a partir do conteúdo.
- `src/publish_daily.py` — publicador oficial, com pré-visualização e controle de duplicidade.
- `.github/workflows/publicar.yml` — agendamento diário automático no GitHub Actions.
- `content/state.json` — controle de publicação (começa vazio).

As peças são posts estáticos em imagem. A geração automática de Reels e novos roteiros por IA pode ser uma segunda etapa; **não está implementada neste pacote**.

## 2) Estado atual da conta (11/11/2026)

- Instagram profissional **@universoeletrico.br** criado e com bio/foto definidas.
- Página Facebook **Universo Elétrico** criada e conectada ao Instagram no Meta Business Suite.
- Publicação de boas-vindas já realizada em 11/11/2026.
- Arte sobre contator elétrico **agendada manualmente para 12/11/2026 às 19h** nas duas redes. O arquivo `content/state.json` reserva esse post/data para impedir duplicação.
- Todos os demais posts do pacote estão em **rascunho não aprovado**. O robô **não vai publicar nada** até uma revisão humana. A data mínima foi definida para 13/11/2026.

## 2A) Criar o Instagram (etapa já concluída)


1. No Instagram, cadastre uma conta nova com o e-mail que você controla, usando **sua idade verdadeira**. Ative autenticação de dois fatores.
2. Use o nome exibido **Universo Elétrico ⚡**.
3. Tente o usuário `@universoeletrico.br` (a disponibilidade depende do Instagram). Se indisponível, experimente `@universo.eletrico.br` ou `@universoeletrico.oficial`.
4. Use o arquivo `assets/foto-perfil.jpg` como foto de perfil.
5. Bio já definida:

   ⚡ Elétrica descomplicada  
   🔌 Componentes, motores e sensores  
   🏭 Automação industrial na prática  
   📚 Aprenda algo novo todos os dias!

**Importante se você tiver menos de 18 anos:** o Instagram pode aplicar proteções próprias para adolescentes e exigir autorização do responsável para alterar certas configurações. Siga as regras e **não altere a idade informada**. Se a plataforma não permitir a conta profissional ou publicação pela API, é possível utilizar as artes e publicá-las manualmente conforme as opções disponíveis.

## 3) Publicação automatizada — requisitos oficiais

Este kit implementa a opção **Instagram API com Facebook Login**. Para funcionar, é necessário:

- Uma conta Instagram **profissional (Criador ou Empresa)** elegível, com uma Página do Facebook vinculada.
- Um aplicativo Meta for Developers com acesso às permissões exigidas para publicar. Normalmente: `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` e `pages_show_list` (outras permissões podem ser necessárias conforme o caso).
- Um token de acesso válido para a Página, associado ao Instagram profissional, e o ID numérico da conta Instagram profissional.
- Os arquivos JPEG hospedados em uma **URL HTTPS acessível publicamente**, que a Meta consiga baixar.

**Fontes oficiais**: [Documentação da Meta no Postman](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api), [API de publicação de conteúdo](https://developers.facebook.com/docs/instagram-platform/content-publishing), [GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

A autorização do aplicativo, a validade do token e a elegibilidade da conta serão avaliadas pela Meta. Não há garantia de aprovação. Não forneça sua senha do Instagram para o robô.

## 4) Hospedar o robô sem computador ligado — GitHub Actions + Pages

1. Crie um **novo repositório público**, por exemplo, `universo-eletrico`. Não coloque este projeto em repositórios de aplicativos já existentes.
2. Coloque os arquivos e pastas do kit **na raiz** do repositório, incluindo a pasta oculta `.github`. Ao enviar pelo site, confirme que `.github/workflows/publicar.yml` ficou no caminho correto.
3. Em **Settings → Pages**, ative Pages com `Deploy from a branch`, branch `main`, pasta `/docs`. A URL típica será `https://SEU-USUARIO.github.io/universo-eletrico/` (substitua usuário e nome do repositório).
4. Confirme que `https://SEU-USUARIO.github.io/universo-eletrico/posts/001.jpg` abre a imagem sem pedir login. Uma URL pública de mídia é exigência da Meta.
5. No GitHub, em **Settings → Secrets and variables → Actions** crie:

   **Secrets:**
   - `INSTAGRAM_USER_ID` = ID numérico da conta profissional Instagram (não é o @usuário).
   - `INSTAGRAM_ACCESS_TOKEN` = token autorizado para publicação.

   **Variables:**
   - `PUBLIC_MEDIA_BASE_URL` = `https://SEU-USUARIO.github.io/universo-eletrico`
   - `PUBLISH_ENABLED` = `false` no começo.

6. Antes da publicação real, revise cada arte e legenda. Para aprovar, edite `content/posts.json` e coloque `"approved": true` no conteúdo revisado, ou execute por exemplo `python src/approve_posts.py 002 003` e envie a alteração para o GitHub. **Não aprove o post 001**, que já está agendado na Meta.
7. Em **Actions**, execute manualmente `Universo Elétrico - postagem diária` para validar o modo seguro. Deve aparecer `Pré-visualização: nenhuma publicação foi enviada.`
8. Confira permissões, validade do token, conta profissional, primeira arte, primeira legenda e URL pública. **Só depois** altere `PUBLISH_ENABLED` para `true` e faça um único teste de publicação controlado.
9. Se esse teste funcionar, o fluxo executará automaticamente todos os dias por volta de **19h17 (São Paulo)**, até acabar a fila. O GitHub pode atrasar, e execuções podem não ocorrer em condições de alta carga. Verifique os logs.

### Cuidado com custos, limites e continuidade

O pacote não exige servidor Render. O GitHub Actions e o Pages têm regras, limites e eventuais custos de acordo com o tipo de conta e uso. Em repositórios públicos, o agendamento pode ser desativado após 60 dias sem atividade. Os tokens Meta podem expirar ou ser revogados. Este robô **não substitui monitoramento**. A fila tem 30 posts; ao acabar, não publicará conteúdo repetido. Para continuar diariamente, novas postagens precisam entrar na fila.

## 5) Como testar localmente (sem fazer nenhuma publicação)

No Windows, com Python instalado, abra o terminal na pasta do projeto:

```powershell
python src/publish_daily.py --dry-run
python -m unittest discover -s tests -v
```

Resultado esperado: mostra **Post 001 — Contator elétrico** e informa que nenhuma postagem foi enviada.

Para recriar as artes no computador (opcional):

```powershell
pip install -r requirements-design.txt
python src/generate_art.py
```

A versão de geração usa fontes comuns instaladas em sistemas Linux; no Windows pode usar a fonte de contingência se não encontrar essas fontes. As artes prontas não dependem disso.

## 6) Como funciona o robô

1. No horário programado, o GitHub inicia o workflow.
2. Os testes verificam se os 30 arquivos estão presentes.
3. Se `PUBLISH_ENABLED` não for `true`, apenas mostra a próxima publicação.
4. Se ativado, escolhe o **primeiro post aprovado que ainda não foi publicado**, sem repetir a data local.
5. Envia a URL da imagem e a legenda pela API oficial da Meta.
6. Aguarda a Meta preparar a mídia e solicita a publicação.
7. Quando a Meta devolve o ID do post, registra-o no `state.json` e salva o histórico no GitHub.

Se ocorrer um erro durante a chamada à API, **confira primeiro o Instagram antes de repetir o workflow**. Uma falha de comunicação após o envio pode deixar o post publicado sem gravar o estado; repetir imediatamente pode duplicá-lo.

## 7) Crescimento e patrocínio

Leia **`PLANO_DE_CRESCIMENTO.md`** com roteiros de Reels e estratégia de patrocinadores. O script atual publica somente imagens aprovadas no Instagram; a programação automática de Reels, a criação contínua por IA e o envio direto ao Facebook ainda não foram implementados. Enquanto isso, você pode usar o Meta Business Suite para agendar as duas plataformas.

## 8) Conteúdo, segurança e resultados

- Conteúdos são educativos e conceituais. Antes de publicar, revise informações, fontes e aplicabilidade.
- Não publique instruções de intervenção em equipamentos energizados nem demonstrações perigosas.
- Evite copiar imagens de fabricantes e de outros criadores sem licença.
- Não utilize automação para comprar seguidores, seguir/deixar de seguir em massa ou enviar spam.
- A publicação automática não garante engajamento ou monetização. Priorize conteúdos úteis, respostas genuínas a comentários e análise dos resultados.

## 9) Próximas evoluções

- Criar Reels verticais originais com narração e legendas.
- Integrar geração de novos roteiros e artes via API de IA, com revisão humana antes de entrar na fila.
- Painel de métricas e ranking de formatos que geram mais salvamentos e compartilhamentos.
- Evoluir o agendamento caso GitHub Actions não atenda aos requisitos de confiabilidade.

## Estado atual

**Concluído:** marca, bio, Instagram e Página conectados, primeira publicação, agendamento de 12/11, 30 artes sem numeração (em rascunho), legendas, roteiros de Reels, script e workflow.

**Pendente:** repositório GitHub exclusivo, permissão do aplicativo Meta para publicação automática, endereço público das imagens, testes de API e ativação explícita do robô. A conta precisa cumprir os requisitos oficiais de idade e elegibilidade. A ferramenta não publica automaticamente no Facebook nesta versão.
