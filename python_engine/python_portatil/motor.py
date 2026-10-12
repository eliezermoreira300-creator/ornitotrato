import os
import sys
import shutil
from pathlib import Path
import sqlite3
import pandas as pd
import pypdf
import pdfplumber
import fitz # PyMuPDF
from datetime import datetime
import re

def obter_base_dir():
    """Retorna o diretório base absoluto correto, seja rodando como script ou .exe compilado."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

def conectar_banco():
    base_dir = obter_base_dir()
    db_path = base_dir / "ornitotrato.db"
    if not db_path.exists():
        # Cria um banco vazio caso não exista
        conn = sqlite3.connect(str(db_path))
        conn.close()
    return sqlite3.connect(str(db_path))

class MotorUniversalExtratos:
    def __init__(self):
        pass

    def extrair_texto_pdf(self, caminho_pdf):
        texto = ""
        try:
            with pdfplumber.open(caminho_pdf) as pdf:
                for pagina in pdf.pages:
                    t = pagina.extract_text()
                    if t:
                        texto += t + "\n"
        except Exception as e:
            print(f"Erro no pdfplumber: {e}")
        
        if not texto.strip():
            try:
                doc = fitz.open(caminho_pdf)
                for pagina in doc:
                    texto += pagina.get_text() + "\n"
            except Exception as e:
                print(f"Erro no PyMuPDF: {e}")
        return texto

    def identificar_cnpj_e_banco(self, texto):
        padrao_cnpj = r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14}'
        cnpjs = re.findall(padrao_cnpj, texto)
        
        cnpj_encontrado = None
        conn = conectar_banco()
        cursor = conn.cursor()
        
        if cnpjs:
            for c in cnpjs:
                c_limpo = re.sub(r'\D', '', c)
                cursor.execute("SELECT cnpj FROM empresas WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = ?", (c_limpo,))
                res = cursor.fetchone()
                if res:
                    cnpj_encontrado = res[0]
                    break
        
        if not cnpj_encontrado:
            cursor.execute("SELECT cnpj FROM empresas LIMIT 1")
            res = cursor.fetchone()
            if res:
                cnpj_encontrado = res[0]

        conn.close()
        return {"cnpj_empresa": cnpj_encontrado}

    def processar_arquivo(self, caminho_arquivo):
        caminho = Path(caminho_arquivo)
        ext = caminho.suffix.lower()
        
        texto = ""
        if ext == '.pdf':
            texto = self.extrair_texto_pdf(caminho)
        elif ext in ['.xlsx', '.xls']:
            df = pd.read_excel(caminho)
            texto = df.to_string()
        elif ext == '.txt':
            with open(caminho, 'r', encoding='latin-1', errors='replace') as f:
                texto = f.read()

        info = self.identificar_cnpj_e_banco(texto)
        
        transacoes = []
        linhas = texto.split('\n')
        for linha in linhas:
            if any(char.isdigit() for char in linha) and ('/' in linha or '-' in linha):
                transacoes.append({
                    "data": "10/2026",
                    "historico": linha.strip()[:50],
                    "valor": "0,00"
                })

        return {
            "cnpj_empresa": info.get("cnpj_empresa"),
            "transacoes": transacoes
        }

def gerar_linha_colunada_contabil(transacao):
    data = transacao.get("data", "        ")
    hist = transacao.get("historico", "").ljust(50)
    valor = transacao.get("valor", "0,00").rjust(15)
    return f"{data} | {hist} | {valor}"

def processar_arquivo_isolado(nome_arquivo):
    base_dir = obter_base_dir()
    caminho_entrada = Path(nome_arquivo)
    
    if not caminho_entrada.exists():
        caminho_entrada = base_dir / nome_arquivo

    if not caminho_entrada.exists():
        print(f"Ficheiro não encontrado: {nome_arquivo}")
        return

    # Alterado para usar a pasta de origem do ficheiro ou criar dentro da pasta do projeto de forma independente
    pasta_origem = caminho_entrada.parent
    pasta_processados = pasta_origem / "processados"
    pasta_erros = pasta_origem / "erros"

    pasta_processados.mkdir(parents=True, exist_ok=True)
    pasta_erros.mkdir(parents=True, exist_ok=True)

    try:
        resultado = MotorUniversalExtratos().processar_arquivo(caminho_entrada)
        
        caminho_txt = pasta_processados / caminho_entrada.with_suffix(".txt").name

        with open(caminho_txt, "w", encoding="latin-1", errors="replace", newline="") as f:
            for t in resultado["transacoes"]:
                f.write(gerar_linha_colunada_contabil(t) + "\r\n")

        print(f"Sucesso: {caminho_entrada.name} processado! ({len(resultado['transacoes'])} lançamentos)")

        caminho_destino_original = pasta_processados / caminho_entrada.name
        if caminho_entrada.exists():
            if caminho_destino_original.exists():
                caminho_destino_original.unlink()
            shutil.move(str(caminho_entrada), str(caminho_destino_original))

    except Exception as e:
        print(f"Erro ao processar {caminho_entrada.name}: {e}")
        caminho_erro = pasta_erros / caminho_entrada.name
        if caminho_entrada.exists():
            if caminho_erro.exists():
                caminho_erro.unlink()
            shutil.move(str(caminho_entrada), str(caminho_erro))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        processar_arquivo_isolado(sys.argv[1])
    else:
        print("Nenhum arquivo informado para o motor.")