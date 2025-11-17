#!/bin/bash
# Script de instalação do Dock Transporter

# Atualiza pip3 e instala dependências
echo "Atualizando pip..."
export DEBIAN_FRONTEND=noninteractive # Se certifica de que não haverá interação com o usuário
sudo apt update -y # Atualiza repositórios
sudo apt install -y python3-pip # Instala pip

echo "Instalando dependências..."
sudo pip3 install -r requirements.txt # Instala bibliotecas necessárias

# Definindo caminhos
BASE_DIR="/opt/dock_transporter"                                 # Diretório base da aplicação
SYSTEMD_LINK="/etc/systemd/system/dock_transporter.service"      # Link simbólico do systemd
CONFIG_LINK="/etc/dock_transporter/config.ini"                   # Link simbólico do arquivo de configuração
BIN_LINK="/usr/local/bin/dock_transporter"                       # Link simbólico para executar via terminal

# Criar estrutura de diretórios
echo "Criando estrutura de diretórios em $BASE_DIR..."
sudo mkdir -p "$BASE_DIR/config"                                 # Diretório de configuração
sudo mkdir -p "$BASE_DIR/bin"                                    # Diretório de binários e scripts
sudo mkdir -p /etc/dock_transporter

# Movendo arquivos para o diretório base
echo "Movendo arquivos para $BASE_DIR..."
sudo cp dock_transporter.service "$BASE_DIR/"
sudo cp dock_transporter.py "$BASE_DIR/"
sudo cp dock_transporter.sh "$BASE_DIR/bin/"
sudo cp config.ini "$BASE_DIR/config/"

# Ajustando permissões
echo "Ajustando permissões..."
sudo chmod 644 "$BASE_DIR/dock_transporter.service"             # Permissões do arquivo de serviço
sudo chmod 755 "$BASE_DIR/dock_transporter.py"                  # Permissões do script Python
sudo chmod 755 "$BASE_DIR/bin/dock_transporter.sh"              # Permissões do script de execução
sudo chmod 644 "$BASE_DIR/config/config.ini"                    # Permissões do arquivo de configuração

# Criando links simbólicos
echo "Criando links simbólicos..."
sudo ln -sf "$BASE_DIR/dock_transporter.service" "$SYSTEMD_LINK"
sudo ln -sf "$BASE_DIR/config/config.ini" "$CONFIG_LINK"
sudo ln -sf "$BASE_DIR/bin/dock_transporter.sh" "$BIN_LINK"

# Ativando serviço
echo "Ativando serviço systemd..."
sudo systemctl daemon-reload
sudo systemctl enable dock_transporter.service
sudo systemctl start dock_transporter.service

echo "Instalação concluída com sucesso!"
