from pathlib import Path
import pandas as pd
import logging
from typing import Any
# Configuração simples de log para feedback no terminal
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
import conexao.conexao_db as db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

def consultar_historico_atualizacoes(
    funcao_conexao: Any = None, limite: int = 5
):
    """Função utilitária para visualizar as últimas cargas registradas."""
    engine = (
        db.conexao_bd_postgres().engine
        if funcao_conexao is None
        else funcao_conexao().engine
    )

    query = text("""
        SELECT nome_tabela, data_atualizacao, total_registros, status
        FROM controle_atualizacoes
        ORDER BY data_atualizacao DESC
        LIMIT :limite
    """)

    with engine.connect() as conexao:
        df_historico = pd.read_sql(query, con=conexao, params={"limite": limite})

    return df_historico

if __name__ == "__main__":

    print(consultar_historico_atualizacoes())