#!/bin/bash
echo "Atualizando a aplicação GEROPS via Docker..."
sudo docker compose down
sudo docker compose up --build -d
echo "Atualização concluida com sucesso!"
sudo docker compose ps