import sys
from pathlib import Path
import sqlite3
import pandas as pd

def sincronizar_tabela(conn, df, nome_tabela, mapeamento):
    cursor = conn.cursor()
    colunas_db = list(mapeamento.values())
    colunas_excel = list(mapeamento.keys())
    
    placeholders = ", ".join(["?"] * len(colunas_db))
    cols_str = ", ".join(colunas_db)
    
    for _, row in df.iterrows():
        try:
            valores = [str(row[col]) if pd.notna(row[col]) else "" for col in colunas_excel]
            # Limpa espaços em branco
            valores = [v.strip() for v in valores]
            
            cursor.execute(f"""
                INSERT OR REPLACE INTO {nome_tabela} ({cols_str})
                VALUES ({placeholders})
            """, valores)
        except Exception as e:
            print(f"Erro ao inserir linha na tabela {nome_tabela}: {e}")
            
    conn.commit()

def main():
    if len(sys.argv) < 2:
        print("Erro: Caminho da planilha não informado.")
        sys.exit(1)
        
    caminho_planilha = Path(sys.argv[1])
    if not caminho_planilha.exists():
        print(f"Erro: Arquivo não encontrado: {caminho_planilha}")
        sys.exit(1)

    db_path = Path(__file__).parent.parent / "ornitotrato.db"
    
    try:
        xls = pd.ExcelFile(str(caminho_planilha))
        conn = sqlite3.connect(str(db_path))
        
        # 1. Aba Empresas
        if "empresas" in xls.sheet_names:
            df_emp = pd.read_excel(xls, sheet_name="empresas", dtype=str)
            sincronizar_tabela(conn, df_emp, "empresas", {
                "cnpj": "cnpj",
                "razao_social": "razao_social"
            })
            print(" -> Sincronizada aba 'empresas'.")

        # 2. Aba Bancos e Contas
        if "bancos_contas" in xls.sheet_names:
            df_contas = pd.read_excel(xls, sheet_name="bancos_contas", dtype=str)
            sincronizar_tabela(conn, df_contas, "bancos_contas", {
                "agência": "agencia",
                "numero_conta": "numero_conta",
                "descrição_conta": "descricao_conta",
                "conta_reduzida": "conta_reduzida",
                "cnpj_empresa": "cnpj_empresa"
            })
            print(" -> Sincronizada aba 'bancos_contas'.")

        # 3. Aba Tipos de Operação
        if "tipos_operacao" in xls.sheet_names:
            df_op = pd.read_excel(xls, sheet_name="tipos_operacao", dtype=str)
            col_codigo = [c for c in df_op.columns if 'código' in c.lower() or 'reduzido' in c.lower()][0]
            sincronizar_tabela(conn, df_op, "tipos_operacao", {
                "descrição": "descricao",
                col_codigo: "codigo_reduzido"
            })
            print(" -> Sincronizada aba 'tipos_operacao'.")

        conn.close()
        print("[Python] Planilha de cadastros processada e banco atualizado com sucesso!")

    except Exception as e:
        print(f"Erro crítico ao processar planilha de cadastros: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()