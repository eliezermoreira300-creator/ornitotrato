package main

import (
    "embed"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
    "runtime"
    "strings"
    "sync"
    "time"
)

//go:embed ornitotrato.db
var dbFile embed.FS

func repoRoot() string {
    wd, err := os.Getwd()
    if err != nil || wd == "" {
        return "."
    }
    return wd
}

func resolvePythonExecutable() string {
    root := repoRoot()
    candidates := []string{
        filepath.Join(root, "python_engine", "venv", "Scripts", "python.exe"),
        filepath.Join(root, "python_engine", "venv", "bin", "python"),
        filepath.Join(root, "python_engine", "portable", "python.exe"),
        filepath.Join(root, "python_engine", "portable", "python"),
        filepath.Join(root, "python_engine", "portable", "Python.exe"),
    }

    for _, candidate := range candidates {
        if _, err := os.Stat(candidate); err == nil {
            return candidate
        }
    }

    for _, name := range []string{"python3", "python", "py"} {
        if _, err := exec.LookPath(name); err == nil {
            return name
        }
    }

    return "python"
}

func getDBPath() string {
    root := repoRoot()
    return filepath.Join(root, "ornitotrato.db")
}

func inicializarBancoDeDados() {
    targetDbPath := getDBPath()
    if _, err := os.Stat(targetDbPath); err == nil {
        return
    }

    data, err := dbFile.ReadFile("ornitotrato.db")
    if err != nil {
        fmt.Fprintf(os.Stderr, "Erro ao ler banco embutido: %v\n", err)
        return
    }
    if err := os.WriteFile(targetDbPath, data, 0o644); err != nil {
        fmt.Fprintf(os.Stderr, "Erro ao extrair banco embutido: %v\n", err)
        return
    }
}

func mostrarNotificacao(titulo, mensagem string) {
    if runtime.GOOS == "windows" {
        scriptPowerShell := fmt.Sprintf(
            `Add-Type -AssemblyName System.Windows.Forms;`+
                `Add-Type -AssemblyName System.Drawing;`+
                `$notify = New-Object System.Windows.Forms.NotifyIcon;`+
                `$notify.Icon = [System.Drawing.SystemIcons]::Information;`+
                `$notify.BalloonTipTitle = '%s';`+
                `$notify.BalloonTipText = '%s';`+
                `$notify.Visible = $true;`+
                `$notify.ShowBalloonTip(3000);`,
            titulo, mensagem,
        )

        cmd := exec.Command("powershell", "-WindowStyle", "Hidden", "-Command", scriptPowerShell)
        if err := cmd.Run(); err != nil {
            fmt.Printf("[%s] %s\n", titulo, mensagem)
        }
        return
    }

    fmt.Printf("[%s] %s\n", titulo, mensagem)
}

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

    pythonExe := resolvePythonExecutable()
    scriptCadastros := filepath.Join(repoRoot(), "python_engine", "sincronizar_cadastros.py")

    temArquivos := false
    for _, arquivo := range arquivos {
        if arquivo.IsDir() {
            continue
        }

        ext := strings.ToLower(filepath.Ext(arquivo.Name()))
        if ext != ".xlsx" && ext != ".xls" {
            continue
        }

        temArquivos = true
        caminhoCompleto := filepath.Join(pastaCadastros, arquivo.Name())

        cmd := exec.Command(pythonExe, scriptCadastros, caminhoCompleto)
        if _, err := cmd.CombinedOutput(); err != nil {
            destinoErro := filepath.Join(pastaErros, arquivo.Name())
            _ = os.Remove(destinoErro)
            _ = os.Rename(caminhoCompleto, destinoErro)
            continue
        }

        destinoProcessado := filepath.Join(pastaProcessados, arquivo.Name())
        _ = os.Remove(destinoProcessado)
        _ = os.Rename(caminhoCompleto, destinoProcessado)
    }

    if temArquivos {
        mostrarNotificacao("Ornitotrato", "Sincronização de cadastros concluída com sucesso.")
    }
}

func processarArquivoConcorrente(nomeArquivo string, wg *sync.WaitGroup) {
    defer wg.Done()

    pythonExe := resolvePythonExecutable()
    scriptPy := filepath.Join(repoRoot(), "python_engine", "motor.py")
    cmd := exec.Command(pythonExe, scriptPy, nomeArquivo)
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
                if arquivo.IsDir() {
                    continue
                }

                ext := strings.ToLower(filepath.Ext(arquivo.Name()))
                if ext == ".pdf" || ext == ".ofx" || ext == ".csv" {
                    contador++
                    wg.Add(1)
                    go processarArquivoConcorrente(arquivo.Name(), &wg)
                }
            }

            if contador > 0 {
                wg.Wait()
                mostrarNotific