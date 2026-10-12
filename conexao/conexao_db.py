from dotenv import load_dotenv
from sqlalchemy import create_engine
import os

load_dotenv()

class conexao_bd_mysql:
    def __init__(self):
        self.user = "root"
        self.senha = "root"
        self.banco_de_dados = "mercado_financeiro" #importante especificar o banco
        self.host = "localhost"
        self.porta = 3306
        self.engine = create_engine(url=f"mysql+pymysql://{self.user}:{self.senha}@{self.host}:{self.porta}/{self.banco_de_dados}")

class conexao_bd_postgres:
    def __init__(self):
        self.user = os.getenv("DB_USER")
        self.senha = os.getenv("DB_PASSWORD")
        self.banco_de_dados = os.getenv("DB_NAME") #importante especificar o banco
        self.host = os.getenv("DB_HOST")
        self.porta = os.getenv("DB_PORT")
        self.schema = os.getenv("DB_SCHEMA")
        self.engine = create_engine(url=f"postgresql+psycopg2://{self.user}:{self.senha}@{self.host}:{self.porta}/{self.banco_de_dados}",
            connect_args={
                "options": f"-csearch_path={self.schema}"
            })