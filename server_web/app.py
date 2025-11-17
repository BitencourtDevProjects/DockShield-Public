import configparser
import os

import markdown
from bson import ObjectId
from flask import Flask, redirect, render_template, request, url_for
from pymongo import MongoClient

# ================================================== #
# SEÇÃO 1: CONFIGURAÇÕES E INICIALIZAÇÃO
# ================================================== #

app = Flask(__name__)
config = configparser.ConfigParser()

CVES_POR_PAGINA = 100

# ========== Conexão com Banco de Dados ========== #
# Carrega configurações
config.read("/var/www/server_web/web_config.ini")

if "DATABASE" in config:
    try:
        mongo_location = config["DATABASE"]["location"]
        mongo_port = config["DATABASE"]["port"]
        mongo_uri = f"mongodb://{mongo_location}:{mongo_port}/"
        client = MongoClient(mongo_uri)
        client.admin.command("ping")  # Testa conexão
        db = client[config["DATABASE"]["collection"]]
    except Exception:
        db = None
else:
    db = None

# ================================================== #
# SEÇÃO 2: ROTAS DO APLICATIVO
# ================================================== #

# ========== Rota Principal (Index) ========== #
@app.route("/")
def index():
    """Renderiza a página inicial.

    Busca e exibe uma lista de todas as coleções (que representam imagens
    Docker analisadas) presentes no banco de dados 'DockShield'.
    Se o banco de dados não estiver disponível, exibe a página com uma
    lista vazia.

    Returns:
        str: A página HTML renderizada (template 'index.html') com a
             lista de coleções.
    """
    # Obtém nomes das coleções; retorna lista vazia se 'db' for None
    colecoes = db.list_collection_names() if db is not None else []
    return render_template("index.html", colecoes=colecoes)


# ========== Rota de Detalhes da Imagem ========== #
@app.route("/docker/<colecao>")
def docker_details(colecao):
    """Exibe o relatório de análise principal de uma imagem (coleção).

    Busca na coleção especificada por um documento único que contém o
    relatório de análise da imagem (identificado pela chave
    'analise_do_container'). O conteúdo (Markdown) desse relatório é
    extraído, convertido para HTML e exibido.

    Args:
        colecao (str): O nome da coleção do MongoDB a ser consultada.

    Returns:
        str: A página HTML renderizada (template 'docker.html') com a
             análise. Retorna uma mensagem de erro simples se o DB
             não estiver acessível.
    """
    if db is None:
        return "<p>Banco de dados não disponível.</p>"
    
    # Busca o documento específico que contém o relatório geral da imagem
    doc_analise_imagem = db[colecao].find_one({"analise_do_container": {"$exists": True}})
    analise_imagem_html = None

    if doc_analise_imagem:
        try:
            # Extrai o relatório (Markdown) de dentro da estrutura de resposta da IA
            content_markdown = doc_analise_imagem["analise_do_container"]["choices"][0]["message"]["content"]
            analise_imagem_html = markdown.markdown(content_markdown)
        except Exception:
            # Falha se a estrutura do documento for inesperada
            analise_imagem_html = "<p>Erro ao carregar o relatório de análise da imagem.</p>"

    return render_template("docker.html", colecao=colecao, analise_imagem_html=analise_imagem_html)


# ========== Rota da Lista de CVEs (Paginada) ========== #
@app.route("/cve-list/<colecao>")
def cve_list(colecao):
    """Exibe uma lista paginada de CVEs para uma coleção específica.

    Consulta a coleção em busca de todos os documentos que contêm dados
    de CVE (identificados pela chave 'cve'). Implementa a paginação
    com base no parâmetro 'page' da URL.

    Args:
        colecao (str): O nome da coleção do MongoDB a ser consultada.

    Returns:
        str: A página HTML renderizada (template 'cve.html') com a
             lista de CVEs da página atual e controles de paginação.
             Retorna uma mensagem de erro simples se o DB
             não estiver acessível.
    """
    if db is None:
        return "<p>Banco de dados não disponível.</p>"
    # Calcula a paginação: obtém a página atual (skip) e o número total de páginas.
    page = request.args.get("page", 1, type=int)
    skip = (page - 1) * CVES_POR_PAGINA

    # Conta o total de CVEs e calcula o número de páginas necessárias para a paginação.
    query_cve = {"cve": {"$exists": True}}
    total_cves = db[colecao].count_documents(query_cve)
    total_pages = (total_cves + CVES_POR_PAGINA - 1) // CVES_POR_PAGINA if CVES_POR_PAGINA > 0 else 0

    # Busca os documentos da página atual no DB e formata os IDs para o template.
    documentos_cve = db[colecao].find(query_cve).skip(skip).limit(CVES_POR_PAGINA)
    docs_cve_list = [{**doc, "_id": str(doc["_id"])} for doc in documentos_cve]

    # Renderiza o template 'cve.html', passando os dados da consulta e da paginação.
    return render_template(
        "cve.html",
        colecao=colecao,
        documentos=docs_cve_list,
        page=page,
        total_pages=total_pages,
        total_cves=total_cves,
    )


# ========== Rota do Resumo da CVE ========== #
@app.route("/resumo/<colecao>/<id>")
def resumo(colecao, id):
    """Exibe o relatório detalhado (resumo) de uma CVE específica.

    Busca um documento específico em uma coleção usando seu '_id'.
    Se encontrado, extrai o relatório (Markdown), converte-o para HTML
    e o exibe na página de relatório.

    Args:
        colecao (str): O nome da coleção do MongoDB.
        id (str): A string do ObjectId do documento a ser exibido.

    Returns:
        str: A página HTML renderizada (template 'relatorio.html') com os
             detalhes da CVE. Redireciona para a lista de CVEs se o
             banco de dados não estiver disponível ou se o ID for
             inválido ou não encontrado.
    """
    if db is None:
        return redirect(url_for("cve_list", colecao=colecao))

    try:
        # Converte a string do ID da URL para um ObjectId do MongoDB
        object_id_instance = ObjectId(id)
    except Exception:
        # Redireciona se o ID for malformado
        return redirect(url_for("cve_list", colecao=colecao))

    # Busca o documento único pelo seu ObjectId
    doc = db[colecao].find_one({"_id": object_id_instance})

    if doc:
        doc["_id"] = str(doc["_id"])
        doc["colecao"] = colecao
        try:
            # Extrai o relatório (Markdown) da estrutura de resposta da IA
            content_markdown = doc["relatorio"]["choices"][0]["message"]["content"]
            content_html = markdown.markdown(content_markdown)
        except Exception:
            content_html = "<p>Erro ao carregar o conteúdo do relatório.</p>"

        return render_template("relatorio.html", doc=doc, content_html=content_html, colecao=colecao)

    # Redireciona se o documento com o ID não for encontrado
    return redirect(url_for("cve_list", colecao=colecao))

# ================================================== #
# SEÇÃO 3: INÍCIO DO PROGRAMA
# ================================================== #
if __name__ == "__main__":
    # Define host e porta a partir de variáveis de ambiente, com valores padrão
    app_host = os.environ.get("FLASK_RUN_HOST", "127.0.0.1")
    app_port = int(os.environ.get("FLASK_RUN_PORT", 5000))
    # Inicia o servidor de desenvolvimento do Flask
    app.run(host=app_host, port=app_port, debug=True)