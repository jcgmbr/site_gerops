from sqlalchemy import create_engine


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
        self.user = "postgres"
        self.senha = "87338cb097b3e2202bd7"
        self.banco_de_dados = "base_supgua" #importante especificar o banco
        self.host = "cqmlhi.easypanel.host"
        self.porta = 5432
        self.schema = "gerops"
        self.engine = create_engine(url=f"postgresql+psycopg2://{self.user}:{self.senha}@{self.host}:{self.porta}/{self.banco_de_dados}",
            connect_args={
                "options": f"-csearch_path={self.schema}"
            })