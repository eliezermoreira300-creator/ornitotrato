-- Active: 1791034753856@@127.0.0.1@3306
import sqlite3
import os

def criar_banco_definitivo():
    nome_banco = "ornitotrato.db"
    
    # Remove o banco antigo para garantir uma estrutura limpa
    if os.path.exists(nome_banco):
        try:
            os.remove(nome_banco)
            print("Banco de dados antigo removido.")
        except PermissionError:
            print("[ERRO] O arquivo do banco está aberto no editor. Feche as abas no VS Code e tente novamente.")
            return

    conexao = sqlite3.connect(nome_banco)
    cursor = conexao.cursor()
    
    # Ativa chaves estrangeiras e modo WAL
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA journal_mode = WAL;")

    # 1. Tabela Empresas (CNPJ é a Chave Primária)
    cursor.execute("""
        CREATE TABLE empresas (
            cnpj TEXT PRIMARY KEY,
            razao_social TEXT NOT NULL
        );
    """)

    # 2. Tabela Bancos e Contas (Relacionada com empresas via cnpj_empresa)
    cursor.execute("""
        CREATE TABLE bancos_contas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agencia TEXT NOT NULL,
            numero_conta TEXT NOT NULL,
            descricao_conta TEXT,
            conta_reduzida TEXT NOT NULL,
            cnpj_empresa TEXT NOT NULL,
            FOREIGN KEY (cnpj_empresa) REFERENCES empresas(cnpj) ON DELETE CASCADE
        );
    """)

    # 3. Tabela Tipos de Operação (De-para global de histórico/descrição para código reduzido)
    cursor.execute("""
        CREATE TABLE tipos_operacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            codigo_reduzido TEXT NOT NULL
        );
    """)

    # Índices de performance para as buscas do motor em Go
    cursor.execute("CREATE INDEX idx_bancos_contas_cnpj ON bancos_contas(cnpj_empresa);")
    cursor.execute("CREATE INDEX idx_tipos_operacao_desc ON tipos_operacao(descricao);")

    conexao.commit()
    conexao.close()
    print("Banco de dados criado com sucesso, seguindo o modelo contábil exato!")

if __name__ == "__main__":
    criar_banco_definitivo()