from werkzeug.security import generate_password_hash
from sqlalchemy import text
import conexao.conexao_db as db

engine = db.conexao_bd_postgres().engine

nome = "Administrador"
email = "gerops@gerops.com"
senha_pura = "Admin@2026!"  # Defina aqui a senha que deseja usar

senha_hash = generate_password_hash(senha_pura)

with engine.begin() as conn:
    # Garante que a tabela existe
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS gerops.usuarios (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            email VARCHAR(150) UNIQUE NOT NULL,
            senha_hash VARCHAR(255) NOT NULL,
            ativo BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))
    
    # Insere ou atualiza o utilizador
    conn.execute(text("""
        INSERT INTO gerops.usuarios (nome, email, senha_hash, ativo)
        VALUES (:nome, :email, :senha_hash, TRUE)
        ON CONFLICT (email) 
        DO UPDATE SET senha_hash = :senha_hash, ativo = TRUE;
    """), {"nome": nome, "email": email, "senha_hash": senha_hash})

print(f"Utilizador {email} criado/atualizado com sucesso com a senha: {senha_pura}")