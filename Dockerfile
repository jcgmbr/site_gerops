FROM python:3.10-slim

# Definir diretório de trabalho dentro do contentor
WORKDIR /app

# Instalar dependências de sistema necessárias (para compilar psycopg2, etc.)
RUN apt-get update && apt-get install -y \
  gcc \
  libpq-dev \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Copiar os requisitos e instalar dependências do Python (incluindo python-dotenv)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
  pip install --no-cache-dir gunicorn psycopg2-binary pandas reportlab numpy flask sqlalchemy python-dotenv

# Copiar todo o código do projeto para o contentor
COPY . .

# Expor a porta que o Gunicorn vai utilizar internamente
EXPOSE 8000

# Comando para iniciar a aplicação usando o Gunicorn em produção
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "app:app"]