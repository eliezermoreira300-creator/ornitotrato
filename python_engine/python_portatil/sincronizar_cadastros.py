from pathlib import Path
import sqlite3
import pandas as pd
import unicodedata
import re
import sys

def obter_base_dir():
    """Retorna o diretório base absoluto correto, seja rodando como script ou .exe compilado."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

def limpar_nome_coluna(coluna):
    """Padroniza o nome da coluna: minúsculas, sem acentos, sem caracteres especiais."""
    col_str = str(coluna).strip().lower()
    nfkd = unicodedata.normalize('NFKD', col_str)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    limpa = re.sub(r'[^a-z0-9_]', '_', sem_acento)
    return re.sub(r'_+', '_', limpa).strip('_')

def sincronizar():
    base_dir = obter_base_dir()
    
    # Recebe o caminho do arquivo enviado via argumento pelo Go ou busca o padrão local
    if len(sys.argv) > 1:
        excel_origem = Path(sys.argv[1])
    else:
        excel_origem = base_dir / "dadosX.xlsx"

    db_path = base_dir / "ornitotrato.db"

    if not excel_origem.exists():
        print(f"[ERRO] O arquivo {excel_origem} não foi encontrado.")
        return

    print(f"Iniciando sincronização dos cadastros usando: {excel_origem.name}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Limpa as tabelas antigas para garantir substituição completa
    cursor.execute("DROP TABLE IF EXISTS empresas;")
    cursor.execute("DROP TABLE IF EXISTS bancos_contas;")
    cursor.execute("DROP TABLE IF EXISTS tipos_operacao;")

    # Recria as tabelas estruturadas
    cursor.execute("""
        CREATE TABLE empresas (
            cnpj TEXT PRIMARY KEY,
            razao_social TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE bancos_contas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agencia TEXT NOT NULL,
            numero_conta TEXT NOT NULL,
            descricao_conta TEXT,
            conta_reduzida TEXT NOT NULL,
            cnpj_empresa TEXT NOT NULL,
            FOREIGN KEY (cnpj_empresa) REFERENCES empresas(cnpj) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE tipos_operacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            codigo_reduzido TEXT NOT NULL
        )
    """)

    xls = pd.ExcelFile(str(excel_origem))
    total_abas = len(xls.sheet_names)

    # -------------------------------------------------------------
    # ABA 0: EMPRESAS
    # -------------------------------------------------------------
    if total_abas > 0:
        df_emp = pd.read_excel(xls, sheet_name=0)
        df_emp.columns = [limpar_nome_coluna(c) for c in df_emp.columns]
        print(f"-> Lendo Aba 0 (Empresas) | Colunas: {list(df_emp.columns)}")
        
        for _, row in df_emp.iterrows():
            cnpj = str(row.get("cnpj", "")).strip()
            razao = str(row.get("razao_social", "")).strip()
            if cnpj and razao and cnpj.lower() != "nan":
                cursor.execute("INSERT OR IGNORE INTO empresas (cnpj, razao_social) VALUES (?, ?)", (cnpj, razao))

    # -------------------------------------------------------------
    # ABA 1: BANCOS E CONTAS
    # -------------------------------------------------------------
    if total_abas > 1:
        df_bc = pd.read_excel(xls, sheet_name=1)
        df_bc.columns = [limpar_nome_coluna(c) for c in df_bc.columns]
        print(f"-> Lendo Aba 1 (Bancos e Contas) | Colunas: {list(df_bc.columns)}")
        
        for _, row in df_bc.iterrows():
            ag = str(row.get("agencia", row.get("agência", ""))).strip()
            num = str(row.get("numero_conta", "")).strip()
            desc = str(row.get("descricao_conta", row.get("descriçao_conta", ""))).strip()
            red = str(row.get("conta_reduzida", "")).strip()
            cnpj_emp = str(row.get("cnpj_empresa", "")).strip()
            
            if num and cnpj_emp and red and num.lower() != "nan":
                cursor.execute("""
                    INSERT INTO bancos_contas (agencia, numero_conta, descricao_conta, conta_reduzida, cnpj_empresa)
                    VALUES (?, ?, ?, ?, ?)
                """, (ag, num, desc, red, cnpj_emp))

    # -------------------------------------------------------------
    # ABA 2: TIPOS DE OPERAÇÃO
    # -------------------------------------------------------------
    if total_abas > 2:
        df_to = pd.read_excel(xls, sheet_name=2)
        df_to.columns = [limpar_nome_coluna(c) for c in df_to.columns]
        print(f"-> Lendo Aba 2 (Tipos de Operação) | Colunas: {list(df_to.columns)}")
        
        col_desc = [c for c in df_to.columns if "descri" in c]
        col_red = [c for c in df_to.columns if "reduzido" in c or "codigo" in c]

        if col_desc and col_red:
            c_desc = col_desc[0]
            c_red = col_red[0]
            for _, row in df_to.iterrows():
                desc_val = str(row.get(c_desc, "")).strip()
                red_val = row.get(c_red)
                if desc_val and desc_val.lower() != "nan" and pd.notna(red_val):
                    red_str = str(int(float(red_val))) if str(red_val).replace('.', '', 1).isdigit() else str(red_val).strip()
                    cursor.execute("INSERT INTO tipos_operacao (descricao, codigo_reduzido) VALUES (?, ?)", (desc_val, red_str))

    conn.commit()
    conn.close()
    print("Sincronização concluída com sucesso! Banco totalmente reescrito com as contas reduzidas atualizadas.")

if __name__ == "__main__":
    sincronizar()