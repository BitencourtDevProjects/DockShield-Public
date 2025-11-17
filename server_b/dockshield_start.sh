#!/bin/bash

#Esse arquivo será usado pelo systemd para iniciar a API

cd /opt/dockshield

# Caso o uvicorn não esteja no path coloque o caminho completo para ele no script
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 1
