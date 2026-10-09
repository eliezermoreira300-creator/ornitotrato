# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

def main() -> None:
    repo_root = Path(__file__).resolve().parent
    db_path = repo_root / "ornitotrato.db"

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bancos_contas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agencia TEXT NOT NULL,
        numero_conta TEXT NOT NULL,
        descricao_conta TEXT,
        conta_reduzida TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tipos_operacao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descricao TEXT NOT NULL,
        codigo_reduzido TEXT NOT NULL
    );
    """)

    cursor.execute("DELETE FROM bancos_contas;")
    cursor.execute("DELETE FROM tipos_operacao;")

    bancos_iniciais = [
        ('2591-7', '48073-8', 'Conta Banco 1', '6'),
        ('3224-7', '4.516-0', 'Conta Banco 2', '8'),
        ('3214-0', '120.308-8', 'Conta Banco 3', '3')
    ]