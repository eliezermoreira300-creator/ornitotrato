package main

import (
	"embed"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

//go:embed ornitotrato.db
var dbFile embed.FS

// Função para garantir que o banco de dados embutido seja extraído para a pasta de trabalho
func inicializarBancoDeDados() {
	execPath, err := os.Executable()
	if err != nil {
		return
	}
	targetDir := filepath.Dir(execPath)
	targetDbPath := filepath.Join(targetDir, "ornitotrato.db")

	// Se o banco ainda não existir na pasta do .exe, extrai dos bytes embutidos
	if _, err := os.Stat(targetDbPath); os.IsNotExist(err) {
		data, err := dbFile.ReadFile("ornitotrato.db")
		if err != nil {
			return
		}
		err = os.WriteFile(targetDbPath, data, 0644)
		if err != nil {
			return
		}
	}
}

// Função para exibir notificação flutuante no canto inferior direito do Windows
func mostrarNotificacao(titulo string, mensagem string) {
	scriptPowerShell := fmt.Sprintf(
		"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); $text = $template.GetElementsByTagName('text'); $text[0].AppendChild($template.CreateTextNode('%s')) | Out-Null; $text[1].AppendChild($template.CreateTextNode('%s')) | Out-Null; $toast = [Windows.UI.Notifications.ToastNotification]::new($template); [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Ornitotrato').Show($toast);",
		titulo, mensagem,
	)

	cmd := exec.Command("powershell", "-WindowStyle", "Hidden", "-Command", scriptPowerShell)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	_ = cmd.Run()
}

// Função responsável por processar a planilha de cadastros/parâmetros na Área de Trabalho
func processarCadastros() {
	userDir, err := os.UserHomeDir()
	if err != nil {
		return
	}

	pastaCadastros := filepath.Join(userDir, "Desktop", "cadastros")
	pastaProcessados := filepath.Join(pastaCadastros, "processados")
	pastaErros := filepath.Join(pastaCadastros, "erros")

	_ = os.MkdirAll(pastaProcessados, os.ModePerm)
	_ = os.MkdirAll(pastaErros, os.ModePerm)

	arquivos, err := os.ReadDir(pastaCadastros)
	if err != nil {
		return
	}

	pythonExe, err := filepath.Abs(filepath.Join("python_engine", "venv", "Scripts", "python.exe"))
	if err != nil {
		return
	}

	scriptCadastros, err := filepath.Abs(filepath.Join("python_engine", "sincronizar_cadastros.py"))
	if err != nil {
		return
	}

	temArquivos := false
	for _, arquivo := range arquivos {
		if !arquivo.IsDir() {
			ext := strings.ToLower(filepath.Ext(arquivo.Name()))
			if ext == ".xlsx" || ext == ".xls" {
				temArquivos = true
				caminhoCompleto := filepath.Join(pastaCadastros, arquivo.Name())

				cmd := exec.Command(pythonExe, scriptCadastros, caminhoCompleto)
				// Oculta completamente a janela do subprocesso do Python
				cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}

				_, err := cmd.CombinedOutput()
				if err != nil {
					destinoErro := filepath.Join(pastaErros, arquivo.Name())
					_ = os.Remove(destinoErro)
					_ = os.Rename(caminhoCompleto, destinoErro)
					continue
				}

				destinoProcessado := filepath.Join(pastaProcessados, arquivo.Name())
				_ = os.Remove(destinoProcessado)
				_ = os.Rename(caminhoCompleto, destinoProcessado)
			}
		}
	}

	if temArquivos {
		mostrarNotificacao("Ornitotrato", "Sincronização de cadastros concluída com sucesso.")
	}
}

func processarArquivoConcorrente(nomeArquivo string, wg *sync.WaitGroup) {
	defer wg.Done()

	pythonExe := filepath.Join("python_engine", "venv", "Scripts", "python.exe")
	scriptPy := filepath.Join("python_engine", "motor.py")

	cmd := exec.Command(pythonExe, scriptPy, nomeArquivo)
	// Oculta completamente a janela do subprocesso do Python em paralelo
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}

	_ = cmd.Run()
}

func main() {
	inicializarBancoDeDados()

	userDir, err := os.UserHomeDir()
	if err != nil {
		return
	}

	pastaInputExtratos := filepath.Join(userDir, "Desktop", "extratos")
	if err := os.MkdirAll(pastaInputExtratos, os.ModePerm); err != nil {
		return
	}

	for {
		processarCadastros()

		arquivos, err := os.ReadDir(pastaInputExtratos)
		if err == nil {
			var wg sync.WaitGroup
			contador := 0

			for _, arquivo := range arquivos {
				if !arquivo.IsDir() {
					ext := strings.ToLower(filepath.Ext(arquivo.Name()))
					if ext == ".pdf" || ext == ".ofx" || ext == ".csv" {
						contador++
						wg.Add(1)
						go processarArquivoConcorrente(arquivo.Name(), &wg)
					}
				}
			}

			if contador > 0 {
				wg.Wait()
				mostrarNotificacao("Ornitotrato Automático", fmt.Sprintf("Lote de %d extrato(s) processado e importado com sucesso!", contador))
			}
		}

		time.Sleep(3 * time.Second)
	}
}
