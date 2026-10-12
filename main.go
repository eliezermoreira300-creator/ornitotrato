package main

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

func obterDiretorioBase() string {
	dir, err := os.Getwd()
	if err != nil {
		execPath, err := os.Executable()
		if err != nil {
			return "."
		}
		return filepath.Dir(execPath)
	}
	return dir
}

// Envia uma notificação nativa do Windows usando PowerShell (sem janela preta)
func mostrarNotificacaoWindows(titulo, mensagem string) {
	psScript := fmt.Sprintf(`
		[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
		[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
		$template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
		$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template)
		$text = $xml.GetElementsByTagName("text")
		$text[0].AppendChild($xml.CreateTextNode("%s")) | Out-Null
		$text[1].AppendChild($xml.CreateTextNode("%s")) | Out-Null
		$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
		[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Ornitotrato").Show($toast)
	`, titulo, mensagem)

	cmd := exec.Command("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", psScript)
	cmd.SysProcAttr = getHideWindowAttr()
	_ = cmd.Run()
}

func main() {
	baseDir := obterDiretorioBase()
	dbPath := filepath.Join(baseDir, "ornitotrato.db")

	// Garante banco limpo e vazio se não existir
	if _, err := os.Stat(dbPath); os.IsNotExist(err) {
		file, err := os.Create(dbPath)
		if err != nil {
			fmt.Printf("Erro ao criar banco: %v\n", err)
		} else {
			file.Close()
		}
	}

	// Pastas de trabalho criadas estritamente DENTRO da pasta do projeto (baseDir)
	pastaExtratos := filepath.Join(baseDir, "input_extratos")
	extratosProcessados := filepath.Join(pastaExtratos, "processados")
	extratosErros := filepath.Join(pastaExtratos, "erros")

	pastaCadastros := filepath.Join(baseDir, "input_cadastros")
	cadastrosProcessados := filepath.Join(pastaCadastros, "processados")
	cadastrosErros := filepath.Join(pastaCadastros, "erros")

	os.MkdirAll(extratosProcessados, 0755)
	os.MkdirAll(extratosErros, 0755)
	os.MkdirAll(cadastrosProcessados, 0755)
	os.MkdirAll(cadastrosErros, 0755)

	// Caminho atualizado para o Python portátil embeddable
	pythonExe := filepath.Join(baseDir, "python_engine", "python_portatil", "python.exe")
	motorExtratos := filepath.Join(baseDir, "python_engine", "motor.py")
	scriptCadastros := filepath.Join(baseDir, "python_engine", "sincronizar_cadastros.py")

	for {
		// 1. Processa Cadastros (dentro da pasta do projeto)
		processarPastaCadastros(pastaCadastros, pythonExe, scriptCadastros, cadastrosProcessados, cadastrosErros)

		// 2. Processa Extratos (dentro da pasta do projeto)
		processarPastaExtratos(pastaExtratos, pythonExe, motorExtratos, extratosProcessados, extratosErros, baseDir)

		time.Sleep(3 * time.Second)
	}
}

func processarPastaCadastros(pastaAlvo, pythonExe, scriptPython, pastaProcessados, pastaErros string) {
	ficheros, err := os.ReadDir(pastaAlvo)
	if err != nil {
		return
	}

	for _, f := range ficheros {
		if f.IsDir() {
			continue
		}

		caminhoOriginal := filepath.Join(pastaAlvo, f.Name())
		time.Sleep(500 * time.Millisecond)

		cmd := exec.Command(pythonExe, scriptPython, caminhoOriginal)
		cmd.SysProcAttr = getHideWindowAttr()

		err := cmd.Run()
		if err == nil {
			_ = moverFicheiroComRetry(caminhoOriginal, filepath.Join(pastaProcessados, f.Name()))
			mostrarNotificacaoWindows("Ornitotrato - Cadastros", "Planilha sincronizada com sucesso!")
		} else {
			_ = moverFicheiroComRetry(caminhoOriginal, filepath.Join(pastaErros, f.Name()))
			mostrarNotificacaoWindows("Ornitotrato - Erro", "Falha ao processar planilha de cadastro.")
		}
	}
}

func processarPastaExtratos(pastaAlvo, pythonExe, scriptPython, pastaProcessados, pastaErros, baseDir string) {
	ficheros, err := os.ReadDir(pastaAlvo)
	if err != nil {
		return
	}

	for _, f := range ficheros {
		if f.IsDir() {
			continue
		}

		caminhoOriginal := filepath.Join(pastaAlvo, f.Name())
		time.Sleep(500 * time.Millisecond)

		cmd := exec.Command(pythonExe, scriptPython, caminhoOriginal)
		cmd.SysProcAttr = getHideWindowAttr()

		err := cmd.Run()
		if err == nil {
			_ = moverFicheiroComRetry(caminhoOriginal, filepath.Join(pastaProcessados, f.Name()))
			procurarEMoverTxtRecente(baseDir, pastaProcessados)
			mostrarNotificacaoWindows("Ornitotrato - Extratos", fmt.Sprintf("Extrato %s processado com sucesso!", f.Name()))
		} else {
			_ = moverFicheiroComRetry(caminhoOriginal, filepath.Join(pastaErros, f.Name()))
			mostrarNotificacaoWindows("Ornitotrato - Erro", fmt.Sprintf("Erro ao processar extrato: %s", f.Name()))
		}
	}
}

func procurarEMoverTxtRecente(baseDir, pastaDestino string) {
	pastasBusca := []string{baseDir, filepath.Join(baseDir, "output_txt")}

	for _, p := range pastasBusca {
		fichs, err := os.ReadDir(p)
		if err != nil {
			continue
		}
		for _, f := range fichs {
			if !f.IsDir() && (strings.HasSuffix(f.Name(), ".txt") || strings.HasSuffix(f.Name(), ".pdf")) {
				caminhoItem := filepath.Join(p, f.Name())
				info, err := os.Stat(caminhoItem)
				if err == nil {
					if time.Since(info.ModTime()) < 4*time.Second {
						destinoItem := filepath.Join(pastaDestino, f.Name())
						_ = moverFicheiroComRetry(caminhoItem, destinoItem)
					}
				}
			}
		}
	}
}

func moverFicheiroComRetry(origem, destino string) error {
	if _, err := os.Stat(origem); os.IsNotExist(err) {
		return nil
	}

	dirDestino := filepath.Dir(destino)
	if err := os.MkdirAll(dirDestino, 0755); err != nil {
		return err
	}

	srcFile, err := os.Open(origem)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	defer srcFile.Close()

	_ = os.Remove(destino)
	dstFile, err := os.Create(destino)
	if err != nil {
		return err
	}
	defer dstFile.Close()

	_, err = io.Copy(dstFile, srcFile)
	if err != nil {
		return err
	}

	srcFile.Close()
	dstFile.Close()

	var removeErr error
	for i := 0; i < 10; i++ {
		removeErr = os.Remove(origem)
		if removeErr == nil || os.IsNotExist(removeErr) {
			return nil
		}
		time.Sleep(300 * time.Millisecond)
	}

	if os.IsNotExist(removeErr) {
		return nil
	}

	return removeErr
}

func getHideWindowAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{HideWindow: true}
}
