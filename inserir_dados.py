from pathlib import Path
import pandas as pd
import logging
from typing import Any
# Configuração simples de log para feedback no terminal
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
import conexao.conexao_db as db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text


def carregar_e_tratar_base_isp(
    nome_pasta: str = "dados",
    nome_arquivo: str = "BaseDPEvolucaoMensalCisp.csv",
) -> pd.DataFrame:
    """Carrega o arquivo CSV do ISP, aplica correções de enconding/espaços

    nas colunas de texto e converte colunas numéricas para inteiro.
    """
    caminho_arquivo = Path(nome_pasta) / nome_arquivo

    if not caminho_arquivo.exists():
        raise FileNotFoundError(
            f"O arquivo não foi encontrado em: {caminho_arquivo.resolve()}"
        )

    # 1. Carrega o arquivo com encoding e separador corretos
    base_isp = pd.read_csv(caminho_arquivo, encoding="latin1", sep=";")

    # 2. Define as colunas de texto esperadas
    text_columns = ["munic", "regiao", "mes_ano"]

    # 3. Limpa espaços extras em todas as colunas de texto existentes
    for col in text_columns:
        if col in base_isp.columns:
            base_isp[col] = base_isp[col].astype(str).str.strip()

    # 4. Corrige a grafia/encoding de 'Grande Niterói'
    if "regiao" in base_isp.columns:
        base_isp["regiao"] = base_isp["regiao"].replace(
            r"^Grande Niter.*", "Grande Niterói", regex=True
        )

    # 5. Identifica colunas numéricas, preenche NaNs com 0 e converte para inteiro
    numeric_columns = [
        col for col in base_isp.columns if col not in text_columns
    ]
    base_isp[numeric_columns] = (
        base_isp[numeric_columns].fillna(0).astype(int)
    )

    return base_isp

def salvar_base_no_postgres(
    df: pd.DataFrame,
    nome_tabela: str = "base_dp_evolucao_mensal_cisp",
    funcao_conexao: Any = None,
    modo_insercao: str = "replace",
) -> bool:
    """Insere o DataFrame no PostgreSQL e registra o evento na tabela de auditoria."""
    if df is None or df.empty:
        logging.warning(
            "O DataFrame está vazio ou é inválido. Operação cancelada."
        )
        return False

    try:
        engine = (
            db.conexao_bd_postgres().engine
            if funcao_conexao is None
            else funcao_conexao().engine
        )
    except Exception as e:
        logging.error(f"Falha ao conectar com o banco de dados PostgreSQL: {e}")
        return False

    try:
        logging.info(f"Iniciando a carga dos dados na tabela '{nome_tabela}'...")

        # Adiciona a coluna 'atualizado_em' diretamente no DataFrame (Opção 2)
        df_para_salvar = df.copy()
        df_para_salvar["atualizado_em"] = pd.Timestamp.now()

        # Abre transação no banco
        with engine.begin() as conexao:
            # 1. Garante que a tabela de histórico exista
            criar_tabela_controle_se_nao_existir(conexao)

            # 2. Escreve os dados da tabela principal
            df_para_salvar.to_sql(
                name=nome_tabela,
                con=conexao,
                if_exists=modo_insercao,
                index=False,
                chunksize=1000,
                method="multi",
            )

            # 3. Registra o log de auditoria na 'controle_atualizacoes' (Opção 1)
            sql_log = text("""
                INSERT INTO controle_atualizacoes (nome_tabela, total_registros, status)
                VALUES (:tabela, :registros, :status)
            """)
            conexao.execute(
                sql_log,
                {
                    "tabela": nome_tabela,
                    "registros": len(df_para_salvar),
                    "status": "SUCESSO",
                },
            )

        print("=" * 60)
        print(
            f"SUCESSO: Tabela '{nome_tabela}' salva e controle registrado!"
        )
        print(f"Total de linhas afetadas: {len(df_para_salvar)}")
        print("=" * 60)
        return True

    except SQLAlchemyError as err_sql:
        logging.error(f"Erro de Banco de Dados durante a carga: {err_sql}")
        return False
    except Exception as err:
        logging.error(f"Erro inesperado: {err}")
        return False

def criar_tabela_controle_se_nao_existir(conexao):
    """Garante que a tabela de metadados para controle de versão exista no banco."""
    sql_criar_tabela = text("""
        CREATE TABLE IF NOT EXISTS controle_atualizacoes (
            id SERIAL PRIMARY KEY,
            nome_tabela VARCHAR(100) NOT NULL,
            data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_registros INT NOT NULL,
            status VARCHAR(20) NOT NULL
        );
    """)
    conexao.execute(sql_criar_tabela)

# Exemplo de uso:
if __name__ == "__main__":

    df_isp = carregar_e_tratar_base_isp()

    # Executa o salvamento
    salvar_base_no_postgres(df_isp)