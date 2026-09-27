# Ornitotrato

Ornitotrato é um daemon de automação de alta performance desenvolvido para otimizar rotinas contábeis, eliminando o trabalho manual de redigitação e conciliação de extratos bancários.

## Sobre o Projeto
O sistema opera de forma autônoma e totalmente invisível em segundo plano (background daemon), monitorando diretórios locais na Área de Trabalho. Assim que novos arquivos de extrato (.pdf, .ofx, .csv) ou planilhas de parâmetros (.xlsx) são disponibilizados, o Ornitotrato processa os dados concorrentemente, realiza o mapeamento contábil e os formata exatamente no padrão exigido pelo ERP de destino, disparando notificações nativas do Windows ao concluir.

## Tecnologias Utilizadas
O projeto adota uma arquitetura poliglota eficiente, unindo o melhor de cada ecossistema:
* **Golang (Go):** Responsável pelo núcleo do daemon, gerenciamento de concorrência (goroutines, sync.WaitGroup), empacotamento de recursos estáticos (embed) e orquestração do sistema sem poluição visual de terminais (HideWindow).
* **Python:** Utilizado na camada de inteligência e processamento de dados, realizando o parsing de documentos, extração de texto em PDFs e regras de negócio contábeis.
* **SQLite / Bancos Embarcados:** Armazenamento leve e integrado para regras de parametrização e depara de contas.
* **PowerShell / Windows API:** Integração nativa para exibição de notificações flutuantes (Toast Notifications).

## Principais Funcionalidades
* **Execução Silenciosa:** Roda em segundo plano sem exibir janelas pretas de terminal.
* **Processamento Concorrente:** Lê múltiplos extratos simultaneamente para máxima velocidade.
* **Sincronização de Cadastros:** Validação e leitura automática de planilhas de parâmetros e contas reduzidas.
* **Portabilidade Total:** Distribuído em um único executável leve, sem exigir instalações complexas na máquina de destino.