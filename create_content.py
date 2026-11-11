import json, pathlib, csv
root=pathlib.Path(__file__).parent
# Conteúdos educativos: explicações conceituais sem orientações práticas de intervenções em sistemas energizados.
rows = [
("Contator elétrico", "O que um contator faz?", "É uma chave eletromagnética usada para comandar cargas elétricas à distância.", "Um contator permite comandar cargas por meio de um circuito de controle. Ele não substitui, por si só, as proteções contra sobrecarga e curto-circuito."),
("Disjuntor x fusível", "Disjuntor ou fusível?", "Ambos ajudam na proteção, mas seu modo de atuação e rearme são diferentes.", "O fusível interrompe o circuito quando seu elemento interno atua; normalmente precisa ser substituído. O disjuntor pode ser rearmado após identificar e resolver a causa do disparo."),
("Sensor indutivo", "Como detecta metal?", "O sensor indutivo detecta objetos metálicos sem contato físico.", "Sensores indutivos criam um campo eletromagnético para perceber a aproximação de metais. São comuns em máquinas e linhas de produção."),
("CLP", "O cérebro da automação", "O CLP lê sinais, executa uma lógica e comanda saídas.", "CLP é a sigla de Controlador Lógico Programável. Ele ajuda a automatizar sequências e processos industriais."),
("Inversor de frequência", "Como controlar a velocidade?", "O inversor ajusta frequência e tensão para controlar motores adequados.", "Inversores de frequência possibilitam variar a velocidade de muitos motores CA. Sua aplicação depende do tipo de motor e do projeto."),
("Motor trifásico", "Por que três fases?", "A alimentação trifásica cria um campo magnético girante em motores de indução.", "Motores trifásicos são muito usados na indústria pela robustez e pela adequação a aplicações de diferentes potências."),
("Encoder", "Como a máquina sabe a posição?", "Encoders fornecem sinais relacionados ao movimento, à posição ou à velocidade.", "Encoders ajudam no acompanhamento de eixos e transportadores. Conforme o tipo, fornecem posição incremental ou absoluta."),
("Relé térmico", "Quem protege o motor?", "O relé de sobrecarga ajuda a proteger motores contra correntes excessivas prolongadas.", "O relé de sobrecarga é associado à proteção de motores. Sua função é diferente da proteção contra curto-circuito."),
("Sensor capacitivo", "Só detecta metal?", "Sensores capacitivos podem detectar materiais metálicos e não metálicos.", "Dependendo do ajuste e da aplicação, sensores capacitivos percebem a presença de plástico, vidro ou líquidos."),
("IHM", "Operador e máquina", "A IHM apresenta dados e comandos de um equipamento ao operador.", "Interface Homem-Máquina (IHM) é a tela ou painel usado para acompanhar estados, alarmes e comandos autorizados."),
("SCADA", "O que um SCADA mostra?", "Sistemas SCADA supervisionam processos, estados, históricos e alarmes.", "SCADA significa Supervisory Control And Data Acquisition: supervisão e aquisição de dados industriais."),
("Contato NA/NF", "NA e NF: qual a diferença?", "NA significa normalmente aberto; NF, normalmente fechado.", "Os termos se referem ao estado de repouso do contato, sem acionamento. O comportamento final depende do dispositivo e da lógica."),
("PROFINET", "Rede industrial em tempo real", "PROFINET é uma tecnologia de comunicação Ethernet industrial.", "PROFINET conecta equipamentos de automação e viabiliza trocas de dados industriais, incluindo aplicações com exigências de tempo."),
("PROFIBUS", "A rede antes do Ethernet", "PROFIBUS é uma família de redes de comunicação de campo industriais.", "O PROFIBUS é usado para troca de dados entre controladores e dispositivos de campo. Existem diferentes variantes da tecnologia."),
("Sensores fotoelétricos", "Detectar sem tocar", "Sensores fotoelétricos usam luz para detectar a presença de objetos.", "Sensores fotoelétricos podem usar reflexão ou barreira óptica. São frequentes em contagem e detecção de peças."),
("Servo motor", "Precisão no movimento", "Sistemas servo controlam movimento com realimentação de posição ou velocidade.", "O servoacionamento combina motor, controle e feedback para atender exigências dinâmicas de posicionamento e movimento."),
("SINAMICS", "O que é SINAMICS?", "SINAMICS é uma família de acionamentos da Siemens.", "Acionamentos SINAMICS podem ser usados para controle de motores e eixos industriais. Modelos diferentes atendem aplicações distintas."),
("SIMOTION", "Movimento sincronizado", "SIMOTION é uma plataforma Siemens para controle de movimento.", "O SIMOTION aparece em aplicações que exigem coordenação e sincronismo de eixos, como máquinas industriais."),
("WinCC", "O que faz o WinCC?", "WinCC é uma plataforma Siemens para visualização e supervisão.", "Aplicações WinCC podem apresentar telas, tendências, alarmes e informações de processos. As funcionalidades dependem da versão."),
("24 Vcc", "Por que tantos painéis usam 24 V?", "24 Vcc é comum em circuitos de controle e automação industrial.", "A tensão de 24 volts em corrente contínua é muito utilizada em sensores, controladores e circuitos de comando. Cuidados e projeto adequado continuam necessários."),
("Ciclo de varredura", "Como um CLP pensa?", "O CLP executa etapas cíclicas de leitura, processamento e atualização.", "O ciclo de varredura é uma forma simplificada de entender como muitos CLPs operam. Há tarefas e arquiteturas com comportamentos distintos."),
("Sensor PNP/NPN", "PNP ou NPN?", "PNP e NPN descrevem modos de chaveamento de saídas de sensores.", "A escolha entre sensores PNP e NPN depende das características das entradas do sistema e das especificações dos equipamentos."),
("PID", "O que significa PID?", "PID combina ações proporcional, integral e derivativa no controle de processos.", "Controladores PID são aplicados em variáveis como temperatura, pressão e velocidade. Ajustes exigem análise do processo."),
("Falha e alarme", "Alarme não é diagnóstico completo", "O alarme sinaliza uma condição; o diagnóstico investiga sua origem.", "Em manutenção, a mensagem de alarme é uma pista. Histórico, documentação e procedimentos autorizados ajudam na análise segura."),
("Manutenção preventiva", "Antes que a máquina pare", "Manutenção preventiva segue um plano para reduzir falhas e indisponibilidades.", "Uma boa estratégia combina inspeções planejadas, indicadores e recomendações do fabricante, sempre executadas por pessoal habilitado."),
("Fibra óptica", "Dados pela luz", "A fibra óptica transporta informação por sinais luminosos.", "Na indústria, a fibra pode ajudar em enlaces de comunicação com boa imunidade a interferências eletromagnéticas."),
("Motor x gerador", "Qual a diferença?", "O motor transforma energia elétrica em mecânica; o gerador realiza o caminho inverso.", "Motores e geradores são conversores de energia. Os detalhes dependem da tecnologia e do regime de operação."),
("Sinal analógico", "Digital ou analógico?", "Um sinal analógico varia continuamente; o digital usa estados ou valores discretos.", "Em automação, sensores e controladores trabalham com informações analógicas e digitais, conforme a variável monitorada."),
("Segurança industrial", "Segurança vem antes da produção", "Intervenções elétricas exigem procedimento, isolamento de energia e profissionais habilitados.", "A segurança elétrica depende de avaliação de riscos, procedimentos da empresa e profissionais capacitados. Nunca improvise intervenções em equipamentos energizados."),
("Robótica industrial", "Como o robô sabe o destino?", "Controladores combinam programas, sensores e referências de movimento.", "Robôs industriais são integrados a sistemas de controle para movimentar peças de forma coordenada, conforme projeto e sistemas de segurança."),
]
posts=[]
for i,(topic,hook,body,caption) in enumerate(rows,1):
    posts.append({"id":f"{i:03d}","title":topic,"hook":hook,"body":body,"caption":f"⚡ {hook}\n\n{caption}\n\n💡 Gostou? Salve este post para revisar depois e compartilhe com alguém que estuda elétrica!\n\n#UniversoEletrico #Eletrica #AutomacaoIndustrial #Eletricidade #ManutencaoIndustrial", "approved":True, "media_type":"IMAGE", "format":"feed"})
(root/'content'/'posts.json').write_text(json.dumps(posts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (root/'content'/'calendario_30_dias.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f,delimiter=';');w.writerow(['Dia','Assunto','Gancho','Formato','Status'])
    for i,p in enumerate(posts,1):w.writerow([i,p['title'],p['hook'],'Imagem','Aprovado para fila'])
(root/'content'/'state.json').write_text(json.dumps({'published':[]},indent=2)+'\n',encoding='utf-8')
print(len(posts))
