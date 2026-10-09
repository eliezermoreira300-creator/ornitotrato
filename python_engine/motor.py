# -*- coding: utf-8 -*-
import csv
import re
import shutil
import sqlite3
import sys
from io import StringIO
from pathlib import Path

try:
    import pandas as pd  # type: ignore
except ImportError:
    pd = None

try:
    import pdfplumber  # type: ignore
except ImportError:
    pdfplumber = None

try:
    import ofxparse  # type: ignore
    from ofxparse import OfxParser
except ImportError:
    OfxParser = None

try:
    import fitz  # type: ignore
except ImportError:
    fitz = None

try:
    import easyocr  # type: ignore
    import numpy as np
    import PIL.Image
except ImportError:
    easyocr = None


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


class MotorUniversalExtratos:
    def __init__(self, db_path=None):
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            self.db_path = repo_root() / "ornitotrato.db"
        self._leitor_easyocr = None

    def _obter_easyocr(self):
        if self._leitor_easyocr is None and easyocr:
            pasta_cache = Path.home() / ".ornitotrato" / "modelos_ocr"
            pasta_cache.mkdir(parents=True, exist_ok=True)
            self._leitor_easyocr = easyocr.Reader(["pt"], gpu=False, model_storage_directory=str(pasta_cache))
        return self._leitor_easyocr

    def _conectar_db(self):
        if self.db_path.exists():
            try:
                return sqlite3.connect(str(self.db_path))
            except Exception:
                return None
        return None

    def _identificar_empresa_e_conta(self, texto_completo: str, agencia_extrato: str, numero_conta_extrato: str):
        conn = self._conectar_db()
        if not conn:
            return None, "2"

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, cnpj, razao_social FROM empresas")
            empresas = cursor.fetchall()
            cnpj_encontrado = None

            texto_limpo_geral = re.sub(r"[^0-9]", "", texto_completo or "")
            for _, cnpj_db, _ in empresas:
                cnpj_nums = re.sub(r"[^0-9]", "", str(cnpj_db))
                if cnpj_nums and cnpj_nums in texto_limpo_geral:
                    cnpj_encontrado = str(cnpj_db)
                    break

            query = "SELECT agencia, numero_conta, conta_reduzida, cnpj_empresa FROM bancos_contas"
            params = ()
            if cnpj_encontrado:
                query += " WHERE cnpj_empresa = ?"
                params = (cnpj_encontrado,)

            cursor.execute(query, params)
            contas = cursor.fetchall()

            if not contas:
                cursor.execute("SELECT agencia, numero_conta, conta_reduzida, cnpj_empresa FROM bancos_contas")
                contas = cursor.fetchall()

            agencia_nums = re.sub(r"[^0-9]", "", agencia_extrato or "")
            conta_nums = re.sub(r"[^0-9]", "", numero_conta_extrato or "")

            melhor_match = None
            cnpj_vinculado = cnpj_encontrado

            for ag_db, num_db, reduzida, cnpj_emp in contas:
                ag_db_nums = re.sub(r"[^0-9]", "", str(ag_db or ""))
                num_db_nums = re.sub(r"[^0-9]", "", str(num_db or ""))

                conta_exata = conta_nums and num_db_nums and (conta_nums == num_db_nums)
                conta_parcial = conta_nums and num_db_nums and (conta_nums in num_db_nums or num_db_nums in conta_nums)
                agencia_compativel = not agencia_nums or not ag_db_nums or (agencia_nums in ag_db_nums or ag_db_nums in agencia_nums)

                if conta_exata and agencia_compativel:
                    return cnpj_emp, str(reduzida)
                elif conta_exata:
                    melhor_match = str(reduzida)
                    cnpj_vinculado = cnpj_emp
                elif conta_parcial and agencia_compativel and not melhor_match:
                    melhor_match = str(reduzida)
                    cnpj_vinculado = cnpj_emp

            if melhor_match:
                return cnpj_vinculado, melhor_match

            if contas:
                return contas[0][3], str(contas[0][2])

        except Exception:
            pass
        finally:
            conn.close()

        return None, "2"

    def _buscar_conta_reduzida(self, historico: str, tipo_transacao: str = "C") -> str:
        conn = self._conectar_db()
        if not conn:
            return "648" if tipo_transacao == "D" else "649"

        try:
            cursor = conn.cursor()
            hist_upper = historico.upper()

            cursor.execute(
                """
                SELECT codigo_reduzido, descricao
                FROM tipos_operacao
                WHERE descricao IS NOT NULL AND TRIM(descricao) != ''
                ORDER BY LENGTH(descricao) DESC
            """
            )
            regras = cursor.fetchall()

            for codigo_reduzido, desc_regra in regras:
                palavras_regra = [p.upper() for p in re.findall(r"\b[A-Za-zÀ-ÿ0-9]+\b", str(desc_regra))]
                if not palavras_regra:
                    continue

                todas_presentes = all(re.search(r"\b" + re.escape(p) + r"\b", hist_upper) for p in palavras_regra)
                if todas_presentes:
                    return str(codigo_reduzido)

            palavras_hist = re.findall(r"\b[A-Za-zÀ-ÿ]{2,}\b", hist_upper)
            if len(palavras_hist) >= 2:
                for i in range(len(palavras_hist) - 1):
                    dupla = f"{palavras_hist[i]} {palavras_hist[i+1]}"
                    cursor.execute(
                        """
                            SELECT codigo_reduzido
                            FROM tipos_operacao
                            WHERE ? LIKE '%' || descricao || '%' OR descricao LIKE '%' || ? || '%'
                            ORDER BY LENGTH(descricao) DESC
                            LIMIT 1
                        """,
                        (dupla, dupla),
                    )
                    res_dupla = cursor.fetchone()
                    if res_dupla:
                        return str(res_dupla[0])

            for palavra in sorted(palavras_hist, key=len, reverse=True):
                if len(palavra) < 3:
                    continue
                cursor.execute(
                    """
                        SELECT codigo_reduzido
                        FROM tipos_operacao
                        WHERE ? LIKE '%' || descricao || '%'
                        ORDER BY LENGTH(descricao) DESC
                        LIMIT 1
                    """,
                    (palavra,),
                )
                res_palavra = cursor.fetchone()
                if res_palavra:
                    return str(res_palavra[0])

        except Exception:
            pass
        finally:
            conn.close()

        return "648" if tipo_transacao == "D" else "649"

    def _adicionar_transacao(self, transacoes, data, historico, valor_float, agencia, numero_conta, texto_completo=""):
        historico = historico.replace("?", "").strip()
        hist_upper = historico.upper()

        if any(termo in hist_upper for termo in ["SALDO", "BLOQUEADO", "LIMITE", "TOTAL", "S A L D O", "EXTRATO"]):
            return

        data_limpa = re.sub(r"[^0-9/]", "", str(data))
        if len(data_limpa) == 5:
            data_limpa = f"{data_limpa}/2026"
        elif not data_limpa or len(data_limpa) < 10:
            data_limpa = "01/01/2026"

        valor = abs(valor_float)
        _, reduzida_banco = self._identificar_empresa_e_conta(texto_completo, agencia, numero_conta)

        if valor_float >= 0:
            conta_debito = reduzida_banco
            conta_credito = self._buscar_conta_reduzida(historico, "C")
        else:
            conta_debito = self._buscar_conta_reduzida(historico, "D")
            conta_credito = reduzida_banco

        item = {
            "data": data_limpa,
            "conta_debito": conta_debito,
            "conta_credito": conta_credito,
            "historico": historico,
            "valor": valor,
        }

        transacoes.append(item)

    def processar_arquivo(self, caminho_arquivo: Path) -> dict:
        extensao = caminho_arquivo.suffix.lower()
        transacoes = []
        agencia_detectada = ""
        conta_detectada = ""
        texto = ""

        if extensao == ".ofx":
            try:
                with open(caminho_arquivo, "r", encoding="latin-1", errors="ignore") as f:
                    conteudo_ofx = f.read()

                transacoes_lidas = False

                if OfxParser:
                    try:
                        ofx = OfxParser.parse(StringIO(conteudo_ofx))
                        for account in ofx.accounts:
                            conta_detectada = account.account_id or ""
                            agencia_detectada = getattr(account, "routing_number", "") or getattr(account, "bank_id", "")
                            statement = account.statement
                            if statement and statement.transactions:
                                for trans in statement.transactions:
                                    data = trans.date.strftime("%d/%m/%Y") if trans.date else ""
                                    partes_hist = []
                                    if getattr(trans, "memo", None):
                                        partes_hist.append(str(trans.memo))
                                    if getattr(trans, "payee", None):
                                        partes_hist.append(str(trans.payee))
                                    if getattr(trans, "type", None):
                                        partes_hist.append(str(trans.type))
                                    historico = " - ".join(partes_hist).replace("?", "").strip() or "OFX LANCAMENTO"
                                    texto += f"{data} {historico} {trans.amount}\n"
                                    self._adicionar_transacao(
                                        transacoes,
                                        data,
                                        historico,
                                        float(trans.amount),
                                        agencia_detectada,
                                        conta_detectada,
                                        texto_completo=historico,
                                    )
                                    transacoes_lidas = True
                    except Exception:
                        pass

                if not transacoes_lidas:
                    padrao_bloco = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", conteudo_ofx, re.DOTALL | re.IGNORECASE)
                    if not padrao_bloco:
                        padrao_bloco = conteudo_ofx.split("<STMTTRN>")

                    for bloco in padrao_bloco:
                        if not bloco.strip():
                            continue

                        match_data = re.search(r"<DT(?:POSTED|AVAIL)>(\d{8})", bloco, re.IGNORECASE)
                        data_str = "01/01/2026"
                        if match_data:
                            raw_dt = match_data.group(1)
                            if len(raw_dt) >= 8:
                                data_str = f"{raw_dt[6:8]}/{raw_dt[4:6]}/{raw_dt[0:4]}"

                        match_val = re.search(r"<TRNAMT>\s*(-?[\d\.]+,\d{2})", bloco, re.IGNORECASE)
                        if not match_val:
                            match_val = re.search(r"<TRNAMT>\s*(-?[\d\.]+)", bloco, re.IGNORECASE)

                        val_float = 0.0
                        if match_val:
                            val_raw = match_val.group(1).replace("