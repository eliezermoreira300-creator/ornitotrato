import csv
from io import StringIO
from pathlib import Path
import re
import shutil
import sqlite3
import sys

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
    import pandas as pd  # type: ignore
except ImportError:
    pd = None


def obter_base_dir():
    """Retorna o diretório base absoluto correto, seja rodando como script ou .exe compilado."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class MotorUniversalExtratos:

    def __init__(self, db_path=None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            base_dir = obter_base_dir()
            # Garante que aponta sempre para o ornitotrato.db na raiz do projeto / junto ao .exe
            self.db_path = base_dir / "ornitotrato.db"

    def _conectar_db(self):
        if self.db_path.exists():
            try:
                return sqlite3.connect(str(self.db_path))
            except Exception as e:
                print(f"[AVISO] Erro ao conectar ao banco de dados: {e}")
                return None
        print(f"[AVISO] Banco de dados não encontrado em: {self.db_path}")
        return None

    def _identificar_empresa_e_conta(self, texto_completo: str, agencia_extrato: str, numero_conta_extrato: str):
        conn = self._conectar_db()
        if not conn:
            return None, "2"

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT agencia, numero_conta, conta_reduzida, cnpj_empresa FROM bancos_contas")
            contas = cursor.fetchall()

            if not contas:
                return None, "2"

            texto_limpo_geral = re.sub(r"[^0-9]", "", texto_completo or "")
            agencia_nums = re.sub(r"[^0-9]", "", agencia_extrato or "")
            conta_nums = re.sub(r"[^0-9]", "", numero_conta_extrato or "")

            melhor_match = None
            cnpj_vinculado = None

            for ag_db, num_db, reduzida, cnpj_emp in contas:
                ag_db_nums = re.sub(r"[^0-9]", "", str(ag_db or ""))
                num_db_nums = re.sub(r"[^0-9]", "", str(num_db or ""))

                if num_db_nums and (num_db_nums in conta_nums or num_db_nums in texto_limpo_geral or num_db_nums == conta_nums):
                    agencia_compativel = not ag_db_nums or not agencia_nums or (ag_db_nums in agencia_nums or agencia_nums in ag_db_nums or ag_db_nums in texto_limpo_geral)
                    
                    if agencia_compativel:
                        return str(cnpj_emp), str(reduzida)
                    elif not melhor_match:
                        melhor_match = str(reduzida)
                        cnpj_vinculado = str(cnpj_emp)

            if melhor_match:
                return cnpj_vinculado, melhor_match

            return str(contas[0][3]), str(contas[0][2])

        except Exception as e:
            print(f"[ERRO] Falha ao identificar empresa e conta: {e}")
        finally:
            conn.close()

        return None, "2"

    def _buscar_conta_reduzida(self, historico: str, tipo_transacao: str = "C") -> str:
        conn = self._conectar_db()
        if not conn:
            return "648" if tipo_transacao == "D" else "649"

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT codigo_reduzido, descricao FROM tipos_operacao WHERE descricao IS NOT NULL ORDER BY LENGTH(descricao) DESC")
            regras = cursor.fetchall()

            hist_upper = historico.upper()

            for codigo_reduzido, desc_regra in regras:
                if not desc_regra:
                    continue
                desc_limpa = str(desc_regra).strip().upper()
                if desc_limpa in hist_upper:
                    return str(codigo_reduzido)

            for codigo_reduzido, desc_regra in regras:
                if not desc_regra:
                    continue
                desc_limpa = str(desc_regra).strip().upper()
                palavras_regra = [p for p in re.findall(r"\b[A-Za-zÀ-ÿ0-9]{3,}\b", desc_limpa)]
                
                if palavras_regra:
                    if all(palavra in hist_upper for palavra in palavras_regra):
                        return str(codigo_reduzido)

        except Exception as e:
            print(f"[AVISO] Erro ao buscar conta reduzida: {e}")
        finally:
            conn.close()

        return "968" if tipo_transacao == "D" else "59"

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
                                        transacoes, data, historico, float(trans.amount), 
                                        agencia_detectada, conta_detectada, texto_completo=texto
                                    )
                                    transacoes_lidas = True
                    except Exception:
                        pass

                if not transacoes_lidas:
                    padrao_bloco = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", conteudo_ofx, re.DOTALL | re.IGNORECASE)
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
                            val_raw = match_val.group(1).replace(".", "").replace(",", ".") if "," in match_val.group(1) else match_val.group(1)
                            try:
                                val_float = float(val_raw)
                            except ValueError:
                                val_float = 0.0

                        match_memo = re.search(r"<MEMO>(.*?)</MEMO>", bloco, re.IGNORECASE)
                        match_name = re.search(r"<NAME>(.*?)</NAME>", bloco, re.IGNORECASE)
                        
                        historico = "OFX LANCAMENTO"
                        if match_memo:
                            historico = match_memo.group(1).strip()
                        elif match_name:
                            historico = match_name.group(1).strip()

                        historico = historico.replace("?", "").strip()
                        texto += f"{data_str} {historico} {val_float}\n"
                        self._adicionar_transacao(
                            transacoes, data_str, historico, val_float, 
                            agencia_detectada, conta_detectada, texto_completo=texto
                        )
            except Exception as e:
                raise ValueError(f"Falha ao interpretar arquivo OFX: {e}")

        elif extensao in [".xlsx", ".xls"]:
            if not pd:
                raise ValueError("Biblioteca pandas não está instalada.")
            try:
                xls = pd.ExcelFile(str(caminho_arquivo))
                texto_acumulado = []
                ultima_data_excel = "01/01/2026"

                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
                    for _, row in df.iterrows():
                        celulas = [str(c).strip() for c in row.values if c is not None and str(c).strip() != "" and str(c).strip().lower() != "nan"]
                        if not celulas:
                            continue
                        linha_unida = " ".join(celulas)
                        texto_acumulado.append(linha_unida)

                        match_d = re.search(r"\b(\d{2}/\d{2}(?:/\d{4})?)\b", linha_unida)
                        data_bruta = ""
                        if match_d:
                            data_bruta = match_d.group(1)
                            ultima_data_excel = data_bruta
                        data_util = data_bruta if data_bruta else ultima_data_excel

                        matches_val = list(re.finditer(r"(-?[\d\.]+,\d{2})", linha_unida))
                        if not matches_val:
                            matches_val = list(re.finditer(r"(-?[\d]+\.\d{2})", linha_unida))

                        if matches_val:
                            val_str = matches_val[-1].group(1)
                            val_padrao = val_str.replace(".", "").replace(",", ".") if "," in val_str else val_str
                            try:
                                val_float = float(val_padrao)
                            except ValueError:
                                continue

                            hist_limpo = linha_unida
                            if data_bruta:
                                hist_limpo = hist_limpo.replace(data_bruta, "")
                            hist_limpo = hist_limpo.replace(matches_val[-1].group(1), "").strip()
                            
                            self._adicionar_transacao(
                                transacoes, data_util, hist_limpo, val_float,
                                agencia_detectada, conta_detectada, texto_completo="\n".join(texto_acumulado)
                            )
                texto = "\n".join(texto_acumulado)
            except Exception as e:
                raise ValueError(f"Falha ao ler Excel: {e}")

        elif extensao in [".pdf", ".png", ".jpg", ".jpeg"]:
            tabelas_extraidas = []
            if pdfplumber and extensao == ".pdf":
                try:
                    with pdfplumber.open(caminho_arquivo) as pdf:
                        paginas_texto = []
                        for pagina in pdf.pages:
                            t = pagina.extract_text(layout=False)
                            t_tabelas = pagina.extract_tables()
                            if t_tabelas:
                                tabelas_extraidas.extend(t_tabelas)
                            if t:
                                paginas_texto.append(t)
                        if paginas_texto:
                            texto = "\n".join(paginas_texto)
                except Exception:
                    pass

            if not texto.strip() and fitz:
                try:
                    doc = fitz.open(str(caminho_arquivo))
                    texto_fitz = [pagina.get_text("text") for pagina in doc]
                    texto = "\n".join(texto_fitz)
                except Exception:
                    pass

            if tabelas_extraidas:
                ultima_data_bloco = "01/01/2026"
                for tabela in tabelas_extraidas:
                    for linha in tabela:
                        if not linha or all(not str(c).strip() for c in linha):
                            continue
                        primeira_celula = str(linha[0]).strip() if linha[0] is not None else ""
                        match_data = re.search(r"\b(\d{2}/\d{2}(?:/\d{4})?)\b", primeira_celula)
                        if match_data:
                            ultima_data_bloco = match_data.group(1)

                        texto_linha_unido = " ".join([str(c).strip() for c in linha if c is not None and str(c).strip() != ""])
                        match_val = re.search(r"(-?[\d\.]*,\d{2})\s*([CD]|\b)?", texto_linha_unido)
                        if match_val:
                            val_str = match_val.group(1)
                            sufixo = match_val.group(2) or ""
                            try:
                                val_float = float(val_str.replace(".", "").replace(",", "."))
                            except ValueError:
                                continue

                            if "D" in sufixo.upper() or "-" in val_str:
                                val_float = -abs(val_float)

                            self._adicionar_transacao(
                                transacoes, ultima_data_bloco, texto_linha_unido, val_float,
                                agencia_detectada, conta_detectada, texto_completo=texto
                            )

            texto_limpo = re.sub(r"[^\w\s\/\.,\-\:\(\)]", " ", texto)
            padrao_universal = re.compile(r"(?:(\d{2}/\d{2}(?:/\d{4})?)\s+)?(.*?)\s+(-?[\d\.]*,\d{2})\s*([CD]|\b)?", re.IGNORECASE)

            ultima_data_corrida = "01/01/2026"
            historico_acumulado = []

            for linha in texto_limpo.splitlines():
                linha = linha.strip()
                if not linha:
                    continue
                match = padrao_universal.search(linha)
                if match:
                    data_encontrada = match.group(1)
                    if data_encontrada:
                        ultima_data_corrida = data_encontrada
                    data = ultima_data_corrida

                    val_str = match.group(3)
                    sufixo = match.group(4) or ""

                    hist_bruto = " ".join(historico_acumulado + [linha])
                    if data_encontrada:
                        hist_bruto = hist_bruto.replace(data_encontrada, "", 1)
                    hist_bruto = hist_bruto.replace(val_str, "", 1).strip()

                    try:
                        val_float = float(val_str.replace(".", "").replace(",", "."))
                    except ValueError:
                        val_float = 0.0

                    if "D" in sufixo.upper() or val_float < 0 or "-" in val_str:
                        val_float = -abs(val_float)

                    self._adicionar_transacao(
                        transacoes, data, hist_bruto, val_float, 
                        agencia_detectada, conta_detectada, texto_completo=texto
                    )
                    historico_acumulado = []
                else:
                    historico_acumulado.append(linha)

        if not transacoes:
            raise ValueError("Nenhuma transação válida foi encontrada no extrato.")

        cnpj_vinculado, _ = self._identificar_empresa_e_conta(texto, agencia_detectada, conta_detectada)

        return {
            "cnpj_empresa": cnpj_vinculado,
            "conta": conta_detectada,
            "transacoes": transacoes,
        }


def gerar_linha_colunada_contabil(t) -> str:
    historico_limpo = str(t.get("historico", "")).replace("?", "").strip()
    data_str = str(t.get("data", ""))[:10].ljust(10)
    conta_deb = str(t.get("conta_debito", ""))[:8].ljust(8)
    conta_cred = str(t.get("conta_credito", ""))[:8].ljust(8)
    historico = historico_limpo[:45].ljust(45)
    valor_str = f"{t.get('valor', 0.0):.2f}".replace(".", ",").rjust(15)

    return f"{data_str} {conta_deb} {conta_cred} {historico} {valor_str}"


def processar_arquivo_isolado(nome_arquivo):
    base_dir = obter_base_dir()
    
    # Estrutura centralizada na pasta 'extratos' gerenciada ao lado do executável
    pasta_extratos = base_dir / "extratos"
    pasta_input = pasta_extratos
    pasta_processados = pasta_extratos / "processados"
    pasta_erros = pasta_extratos / "erros"

    pasta_processados.mkdir(parents=True, exist_ok=True)
    pasta_erros.mkdir(parents=True, exist_ok=True)

    caixa = pasta_input / nome_arquivo
    if not caixa.exists():
        print(f"Ficheiro não encontrado: {caixa}")
        return

    try:
        resultado = MotorUniversalExtratos().processar_arquivo(caixa)
        caminho_txt = pasta_processados / caixa.with_suffix(".txt").name

        with open(caminho_txt, "w", encoding="latin-1", errors="replace", newline="") as f:
            for t in resultado["transacoes"]:
                f.write(gerar_linha_colunada_contabil(t) + "\r\n")

        stdout_destino = pasta_processados / caixa.name
        if stdout_destino.exists():
            stdout_destino.unlink()
        shutil.move(str(caixa), str(stdout_destino))
        print(f"Sucesso: {nome_arquivo} processado! ({len(resultado['transacoes'])} lançamentos - CNPJ: {resultado.get('cnpj_empresa')})")

    except Exception as e:
        print(f"Erro ao processar {nome_arquivo}: {e}")
        caminho_erro = pasta_erros / caixa.name
        if caixa.exists():
            if caminho_erro.exists():
                caminho_erro.unlink()
            shutil.move(str(caixa), str(caminho_erro))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        processar_arquivo_isolado(sys.argv[1])
    else:
        print("Motor pronto para execução via daemon principal.")