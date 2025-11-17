#!/bin/bash

# Caminho para o arquivo PID do daemon
PID_FILE="/var/run/dock_transporter.pid"

# Função de ajuda
exibir_ajuda() {
    echo "Uso: dock-transporter [comando]"
    echo
    echo "Comandos disponíveis:"
    echo "  run     - Executa manualmente a função 'coletar' do daemon."
    echo
    echo "Exemplo:"
    echo "  dock-transporter run  - Força a execução da função 'coletar'."
}

# Verifica se o comando é "run"
if [ "$1" == "run" ]; then
    # Lê o PID do daemon
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        
        # Envia o sinal SIGUSR1 para forçar a execução da função coletar
        kill -SIGUSR1 $PID
        echo "Função coletar executada manualmente!"
    else
        echo "Daemon não encontrado ou não está em execução."
    fi
else
    # Comando desconhecido, exibe ajuda
    echo "Comando desconhecido: $1"
    exibir_ajuda
fi
