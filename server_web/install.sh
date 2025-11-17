#!/bin/bash

set -e  # Encerra se der erro em qualquer parte

# Caminho final do projeto
PROJETO_DIR="/var/www/server_web"

echo "[1/5] Instalando Apache, mod_wsgi e Python global..."
sudo apt update
sudo apt install -y apache2 libapache2-mod-wsgi-py3 python3-pip

echo "[2/5] Instalando dependências Python globalmente..."
sudo apt remove --purge python3-blinker
sudo pip3 install --upgrade pip setuptools wheel
sudo pip3 install -r requirements.txt

echo "[3/5] Criando diretório do projeto em $PROJETO_DIR..."
sudo mkdir -p $PROJETO_DIR
sudo cp -r ./* $PROJETO_DIR
sudo chown -R www-data:www-data $PROJETO_DIR
sudo chmod -R 755 $PROJETO_DIR

echo "[4/5] Movendo arquivo de configuração para o Apache..."
sudo cp server_web.conf /etc/apache2/sites-available/server_web.conf

# Dando permissões para escrita de Logs
sudo touch /var/log/cve_report_ai.log
sudo chown www-data:www-data /var/log/cve_report_ai.log
sudo chmod 664 /var/log/cve_report_ai.log


echo "[5/5] Ativando site no Apache e reiniciando serviços..."
sudo a2ensite server_web.conf
sudo systemctl reload apache2

