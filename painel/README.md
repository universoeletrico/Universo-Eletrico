# ⚡ Universo Elétrico Studio — painel V1

Plataforma inicial de gestão do **Universo Elétrico**. O painel organiza as artes e textos existentes e não altera as automações do Instagram.

## Recursos disponíveis
- Login administrativo protegido (senha armazenada como hash no servidor)
- Galeria com 30 imagens, buscas e filtros: revisão, aprovado, agendado e publicado
- Prévia em formato de feed e legenda completa
- Planejamento da fila de conteúdos
- Página de evolução futura: IA, Reels, métricas, financeiro e multiempresa
- Aprovação/edição preparada na API, **desabilitada enquanto GITHUB_WRITE_TOKEN não estiver configurado**

## Hospedagem
Serviço Render: universo-eletrico-studio (plano Free, código em painel/).
- Build: pip install -r painel/requirements.txt
- Start: gunicorn --chdir painel app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 90
- PANEL_SESSION_SECRET: chave aleatória guardada somente na Render
- PANEL_PASSWORD_HASH: hash da senha do administrador guardado somente na Render
- GITHUB_WRITE_TOKEN: opcional, necessário para aprovar pelo painel (criar futuramente um token fine-grained com Contents Read and write limitado EXCLUSIVAMENTE ao repositório Universo-Eletrico)
- AutoDeploy desligado para evitar novo deploy a cada post gravado pelo robô. Atualizações do painel exigem redeploy manual.

## Salvamento
- Posts, legendas e histórico continuam registrados no GitHub, sem banco local na Render.
- Ao aprovar, o painel alterará APENAS o content/posts.json, respeitando bloqueios de posts já publicados ou reservados.
- Publicar conteúdo segue sendo responsabilidade do fluxo do GitHub Actions, não do painel.
- Na Render Free não usar SQLite ou armazenamento local para guardar aprovações (dados são efêmeros).

## Próximas etapas
1. Validar galeria e login com o Universo Elétrico.
2. Autorizar escrita limitada no GitHub para habilitar salvar/aprovar no painel.
3. Construir calendário real, geração recorrente de artes com revisão e edição visual.
4. Integrar dados oficiais de métricas e controle financeiro.
5. Só depois criar estrutura segura multiempresa com isolamento de dados, contas por cliente e autenticação oficial Meta.

**Nunca armazenar senhas, tokens nem dados de clientes no repositório público.**
