#!/bin/bash
# Script de instalação do CVE Report AI centralizado em /opt

# Baixa o Trivy
echo "baixando Trivy..."
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sudo sh -s -- -b /usr/local/bin v0.59.1

# Baixa o pip3 e as bibliotecas necessárias
echo "Atualizando pip..."
export DEBIAN_FRONTEND=noninteractive  # Se certifica de que não haverá interação com o usuário
sudo apt update -y                     # Atualiza os repositórios
sudo apt install -y python3-pip        # Instala o pip3

echo "Instalando dependências..."
sudo pip3 install -r requirements.txt  # Instala as bibliotecas necessárias do projeto

# Definição dos caminhos base
BASE_DIR="/opt/dockshield"                           # Diretório principal onde todos os arquivos ficarão centralizados
SYSTEMD_LINK="/etc/systemd/system/dockshield.service" # Link simbólico para o systemd
CONFIG_LINK="/etc/dockshield/ai_config.ini"            # Link simbólico para o arquivo de configuração
BIN_LINK="/usr/local/bin/dockshield_start"            # Link simbólico para execução direta via terminal

# Criação da estrutura de diretórios dentro de /opt
echo "Criando estrutura de diretórios em $BASE_DIR..."
sudo mkdir -p "$BASE_DIR/relatorios"   # Diretório para relatórios
sudo mkdir -p "$BASE_DIR/imagens"      # Diretório para imagens .tar
sudo mkdir -p "$BASE_DIR/config"        # Diretório para configurações
sudo mkdir -p "$BASE_DIR/bin"           # Diretório para scripts
sudo mkdir -p /etc/dockshield


# Movendo os arquivos para o diretório base
echo "Movendo arquivos para $BASE_DIR..."
sudo cp dockshield.service "$BASE_DIR/"        # Arquivo de configuração do systemd
sudo cp ai.py "$BASE_DIR/"                         # Script Python principal
sudo cp api.py "$BASE_DIR/"                        # Script Python da API
sudo cp dockshield_start.sh "$BASE_DIR/bin/"    # Script shell de inicialização
sudo cp ai_config.ini "$BASE_DIR/config/"          # Arquivo de configuração da aplicação

# Ajustando permissões dos arquivos
echo "Ajustando permissões..."
sudo chmod 644 "$BASE_DIR/dockshield.service"     # Permissão padrão para o systemd
sudo chmod 755 "$BASE_DIR/ai.py"                     # Executável
sudo chmod 755 "$BASE_DIR/api.py"                    # Executável
sudo chmod 755 "$BASE_DIR/bin/dockshield_start.sh" # Executável
sudo chmod 644 "$BASE_DIR/config/ai_config.ini"      # Somente leitura

# Criando links simbólicos nos diretórios padrão do sistema
echo "Criando links simbólicos..."
sudo ln -sf "$BASE_DIR/dockshield.service" "$SYSTEMD_LINK"      # Link do systemd
sudo ln -sf "$BASE_DIR/config/ai_config.ini" "$CONFIG_LINK"         # Link para configuração
sudo ln -sf "$BASE_DIR/bin/dockshield_start.sh" "$BIN_LINK"      # Link para execução direta

# Recarrega o systemd e ativa o serviço
echo "Ativando serviço..."
sudo systemctl daemon-reload
sudo systemctl enable dockshield.service
sudo systemctl start dockshield.service

echo "Instalação concluída com sucesso!"
