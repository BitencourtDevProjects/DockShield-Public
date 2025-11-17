import ast
import configparser
import json
import logging
import os
import re
import subprocess
from threading import Lock

import openai
import pymongo
from fastapi import FastAPI, HTTPException, Request
from nvdlib import searchCVE

# ================================================== #
# SEÇÃO 1: CONFIGURAÇÕES
# ================================================== #

# ========== Arquivo De Configurações ========== #
CONFIG_FILE = (
    "/etc/dockshield/ai_config.ini"
)
config = configparser.ConfigParser()
config.read(CONFIG_FILE)


# ========== Conexão Com O Banco De Dados ========== #
client = pymongo.MongoClient(
    # Constroi o caminho para o servidor de banco de dados com base no arquivo de configurção
    f"mongodb://{config['DATABASE']['location']}:{config['DATABASE']['port']}/"
)
db = client["DockShield"]


# ========== Configuração de logs ========== #
logging.basicConfig(
    filename="/var/log/dockshield.log", # Diretório padrão para logs dos sistemas GNU/Linux
    level=logging.INFO,  # Menor nível de log, fora DEBUG
    format="%(asctime)s - %(message)s",  # O formato das logs será (YYYY-MM-DD HH:MM:SS,mm - Mensagem da Log)
)


# ========== API Da LLM ========== #
# Configura a chave de API e a url do ai_LLM com base no arquivo de configuração
openai_client = openai.OpenAI(
    api_key=config["AI"]["api_key"], base_url=config["AI"]["base_url"]
)


# ========== Outros ========== #
app = FastAPI()  # Cria a aplicação FastAPI
lock = Lock()  # Cria uma trava para evitar problemas com threads


# ================================================== #
# SEÇÃO 2: FUNÇÕES
# ================================================== #
@app.post("/upload-image")
async def baixar_e_subir_imagens(request: Request):
    """Baixa, inicia e analisa imagens Docker em busca de vulnerabilidades.

    Esta função recebe uma lista de nomes de imagens Docker, baixa cada imagem,
    inicia um contêiner a partir dela e, em seguida, executa uma análise de
    segurança usando a ferramenta Trivy. Os relatórios são salvos temporariamente
    e processados.

    Args:
        request: O objeto Request do FastAPI contendo os dados da requisição.
                 Esperado um JSON com uma chave 'imagens' que é uma lista de strings.

    Returns:
        Caso a análise tenha sido executada com sucesso, retorna um JSON com a mensagem
        {"message": "Análise concluida com sucesso!"}
    """
    data = await request.json()
    images = data.get("imagens", [])
    logging.info(f"Imagens recebidas: {data}")

    for image in images:
        try:
            # Baixa a imagem Docker para uso local.
            subprocess.run(
                ["docker", "pull", image], capture_output=True, text=True, check=True
            )
            logging.info(f"Imagem {image} baixada.")

            # Inicia a imagem Docker em um contêiner separado.
            subprocess.run(
                ["docker", "run", "-d", image],
                capture_output=True,
                text=True,
                check=True,
            )
            logging.info(f"Imagem {image} subida.")

            # Configurações para o Trivy: diretório de saída e timeout.
            output_dir = "/opt/dockshield/relatorios"
            os.makedirs(output_dir, exist_ok=True)
            os.environ["TRIVY_TIMEOUT"] = "600s"

            # Cria um nome para o arquivo de relatório do trivy.
            output_file = os.path.join(
                output_dir, f'{image.replace(":", "_").replace("/", "_")}.json'
            )

            # Executa a análise de segurança das imagens com o Trivy e salva a saída.
            with open(output_file, "w", encoding="utf-8") as f:
                trivy_result = subprocess.run(
                    ["trivy", "image", "--format", "json", image],
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
            if trivy_result.returncode == 0:
                logging.info(
                    f"Análise Trivy concluída com sucesso para {image}. "
                    f"Relatório salvo em {output_file}"
                )

                # Carrega o JSON do relatório Trivy diretamente após a geração.
                with open(output_file, "r", encoding="utf-8") as f:
                    trivy_data = json.load(f)

                # Inicia a função rodar
                rodar(trivy_data, output_file)

                # Remove o arquivo de relatório temporário para economizar espaço.
                os.remove(output_file)

            else:
                logging.error(
                    f"Erro na análise do Trivy para {image}. "
                    f"Código de retorno: {trivy_result.returncode}"
                )
                logging.error(f"Mensagem de erro: {trivy_result.stderr}")

        except subprocess.CalledProcessError as e:
            logging.error(f"Erro de comando Docker/Trivy para imagem {image}: {e}")
            logging.error(f"Saída de erro: {e.stderr}")
        except Exception as e:
            logging.error(f"Erro inesperado ao processar imagem {image}: {e}")

    logging.info("Análise concluida com sucesso!")
    return {"message": "Análise concluida com sucesso!"}


def ai_LLM(cve_report_content: str) -> dict:
    """Envia dados de uma CVE para análise por um modelo de linguagem via API.

    Esta função é responsável por enviar o conteúdo dos dados de uma CVE
    para a API de chat completions da OpenAI. Ela se comunica com o modelo
    de linguagem configurado (definido externamente), enviando as informações
    da CVE para processamento. Após a requisição, a função recebe a resposta
    da API, que contém a análise gerada pelo modelo de linguagem.

    Args:
        cve_report_content: O conteúdo dos dados da CVE, que é esperado
            como uma string JSON ou um objeto que pode ser convertido
            para string para ser enviado à API.

    Returns:
        Um dicionário contendo a resposta completa do modelo de linguagem,
        que inclui a análise gerada pela IA.
    """
    # Converte o conteúdo do relatório CVE para uma string.
    # Isso é necessário para que possa ser enviado como 'content' para a IA.
    cve_report_str = str(cve_report_content)

    # Realiza a requisição para a API de chat completions da OpenAI.
    # O modelo e as mensagens são configurados para guiar o comportamento da IA.
    response = openai_client.chat.completions.create(
        model=config["AI"][
            "model"
        ],  # Define o modelo de IA a ser utilizado, ex: "gpt-4", "deepseek-reasoner"
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um especialista em segurança da informação, "
                    "especializado em análise de vulnerabilidades e CVEs "
                    "para contêineres Docker executados na plataforma FIWARE. "
                    "Sua função é analisar relatórios de segurança, identificar "
                    "vulnerabilidades críticas, detalhar os riscos associados "
                    "a cada CVE e recomendar ações de mitigação. Ao responder, "
                    "forneça informações técnicas precisas, incluindo o impacto "
                    "no CID (Confidencialidade, Integridade, Disponibilidade), "
                    "possíveis vetores de ataque e correções sugeridas. Mantenha "
                    "a linguagem clara e objetiva, mas com a profundidade "
                    "necessária para orientar profissionais de cibersegurança. "
                    "Ao final de cada análise, gere um resumo executivo para "
                    "facilitar a compreensão do risco por gestores não técnicos. "
                    "Além disso, avalie o nível de criticidade de cada "
                    "vulnerabilidade com uma pontuação de 0 a 100, onde 0 "
                    "indica risco inexistente e 100 indica risco completamente "
                    "inaceitável. Proponha medidas de resolução que minimizem "
                    "o risco, priorizando alternativas que não exijam mudanças "
                    "de versão do sistema, mas sugira essa abordagem se for "
                    "a opção mais viável para mitigar a ameaça. O parâmetro "
                    "de entrada será um dicionário Python ou um arquivo json."
                ),
            },
            # Envia a informação das CVEs para a IA
            {"role": "user", "content": cve_report_str},
        ],
    )

    # Converte o objeto de resposta retornado pela API da OpenAI para um dicionário Python.
    # Isso facilita a manipulação e acesso aos dados da resposta.
    response_dict = response.to_dict()
    return response_dict


def ai_LLM_resumo_do_cenario(scenario_info: str) -> dict:
    """Cria um resumo de cenário com base em informações de metadados do Trivy.

    Esta função é responsável por enviar informações de metadados de um
    relatório Trivy para a API de chat completions da OpenAI. Ela se
    comunica com o modelo de linguagem configurado (definido externamente)
    para gerar um resumo conciso do cenário de segurança. Após a requisição,
    a função recebe a resposta da API, que contém a análise
    e o resumo gerados pelo modelo de linguagem.

    Args:
        scenario_info: O conteúdo da informação de cenário, tipicamente
            extraído do campo 'metadata' de um relatório JSON gerado pelo Trivy.
            É esperado como uma string ou um objeto que pode ser convertido para string.

    Returns:
        Um dicionário contendo a resposta completa do modelo de linguagem,
        que inclui o resumo do cenário de segurança gerado pela IA.
    """
    # Converte a informação do cenário para uma string.
    # Isso é necessário para que possa ser enviada como 'content' para a IA.
    scenario_str = str(scenario_info)

    logging.info("Enviando informação do cenário para análise pela IA.")

    # Realiza a requisição para a API de chat completions da OpenAI.
    # O modelo e as mensagens são configurados para guiar o comportamento da IA.
    response = openai_client.chat.completions.create(
        model=config["AI"]["model"],  # Define o modelo de IA a ser utilizado.
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um especialista em segurança da informação, com foco "
                    "em análise de imagens Docker na plataforma FIWARE. Sua função "
                    "é interpretar as informações fornecidas sobre uma imagem Docker, "
                    "incluindo sua configuração, nome, metadados e outras características "
                    "relevantes, com o objetivo de contextualizar o ambiente para uma análise "
                    "de vulnerabilidades que será realizada posteriormente por outra IA. "
                    "Com base nos dados recebidos: "
                    "- Descreva a configuração e os componentes da imagem Docker. "
                    "- Explique como essas características podem influenciar a análise de "
                    "vulnerabilidades futura. "
                    "- Forneça contexto sobre o ambiente FIWARE, destacando aspectos que podem "
                    "ser relevantes para a segurança. "
                    "Não é necessário concluir ou sugerir ações, apenas contextualizar as informações "
                    "para preparar o terreno para a análise de vulnerabilidades."
                ),
            },
            # A mensagem do usuário contém a informação do cenário a ser analisada pela IA.
            {"role": "user", "content": scenario_str},
        ],
    )

    # Converte o objeto de resposta retornado pela API da OpenAI para um dicionário Python.
    # Isso facilita a manipulação e o acesso aos dados da resposta.
    response_dict = response.to_dict()
    logging.info(
        "Resposta da IA para o resumo do cenário recebida e convertida para dicionário."
    )
    return response_dict


def detalhar_CVE(cve_id: str) -> dict | None:
    """Busca detalhes de uma CVE específica na base de dados do NIST NVD.

    Esta função valida o formato do ID da CVE e, se for válido, realiza
    uma consulta à API do NIST NVD para obter informações detalhadas sobre
    a vulnerabilidade. A função tenta converter o resultado da busca para
    um dicionário Python antes de retorná-lo.

    Args:
        cve_id: O identificador da CVE (ex: "CVE-2023-12345").

    Returns:
        Um dicionário contendo os detalhes da CVE se a busca for bem-sucedida
        e o formato do ID for válido. Retorna `None` em caso de formato inválido
        ou erro durante a busca.
    """
    # Compila a expressão regular para validar o formato do ID da CVE.
    # O padrão esperado é "CVE-YYYY-NNNNN...".
    cve_pattern = re.compile(r"^CVE-\d{4}-\d{4,7}$")

    # Limpa o ID da CVE, removendo espaços em branco e quebras de linha.
    cleaned_cve_id = cve_id.strip()

    # Verifica se o ID da CVE limpo corresponde ao padrão esperado.
    if not cve_pattern.match(cleaned_cve_id):
        logging.error(
            f"'{cleaned_cve_id}' não está no formato CVE esperado. Pulando análise."
        )
        return None  # Retorna None para indicar que o formato é inválido.

    try:
        # Busca os detalhes da CVE na base de dados do NIST NVD.
        # A chave da API é obtida do arquivo de configurações
        raw_result = searchCVE(cveId=cleaned_cve_id, key=config["NVDLIB"]["api_key"])

        # Converte o resultado da busca para um dicionário Python.
        # O searchCVE retorna um objeto que, apesar de ser identico a um dicionário python, não
        # pode ser convertido em um diretamente pela função literal_eval(), então convertemos em
        # uma string antes de transformar em um dicionário.
        result_dict = ast.literal_eval(str(raw_result))
        return result_dict

    except Exception as e:
        # Captura qualquer exceção que ocorra durante a busca ou conversão.
        logging.error(f"Erro ao buscar detalhes da CVE '{cleaned_cve_id}': {e}")
        return None  # Retorna None em caso de erro na busca.


def extrair_ids_vulnerabilidades(trivy_report: dict | list) -> list:
    """Extrai IDs de vulnerabilidades (CVEs) de um relatório Trivy aninhado.

    Esta função percorre recursivamente a estrutura de dados de um relatório
    de análise de vulnerabilidades gerado pelo Trivy. Ela coleta
    todos os valores associados à chave "VulnerabilityID", que tipicamente
    correspondem aos IDs de CVEs, garantindo que os IDs retornados sejam únicos
    (sem duplicatas).

    Args:
        trivy_report: A estrutura de dados aninhada do relatório Trivy (dicionário
                      ou lista), de onde os IDs de vulnerabilidade serão extraídos.

    Returns:
        Uma lista de strings contendo todos os IDs de vulnerabilidade únicos
        (CVEs) encontrados no relatório Trivy.
    """
    # Inicializa uma lista para armazenar todos os IDs de vulnerabilidade encontrados.
    found_vulnerability_ids = []

    # Define uma função auxiliar recursiva para percorrer a estrutura de dados do relatório.
    def _recursive_search(obj):
        """Função auxiliar recursiva para buscar a chave 'VulnerabilityID'."""
        if isinstance(obj, dict):
            # Se o objeto atual for um dicionário.
            for key, value in obj.items():
                if key == "VulnerabilityID":
                    # Se a chave for "VulnerabilityID", adiciona seu valor (o ID da CVE) à lista.
                    found_vulnerability_ids.append(value)
                else:
                    # Se a chave não for "VulnerabilityID", chama recursivamente a função
                    # para o valor, para explorar sub-dicionários ou listas aninhadas.
                    _recursive_search(value)
        elif isinstance(obj, list):
            # Se o objeto atual for uma lista.
            for item in obj:
                # Chama recursivamente a função para cada item da lista.
                _recursive_search(item)
        # Outros tipos de dados (strings, int, bool, etc.) são ignorados,
        # pois não podem conter a chave "VulnerabilityID" de forma aninhada.

    # Inicia a busca recursiva a partir da estrutura de dados do relatório Trivy fornecida.
    _recursive_search(trivy_report)

    # Converte a lista de IDs encontrados para um conjunto (set) para remover quaisquer duplicatas,
    # e então converte de volta para uma lista. Isso garante a unicidade dos IDs retornados.
    unique_vulnerability_ids = list(set(found_vulnerability_ids))

    logging.info(
        f"Extraídos {len(unique_vulnerability_ids)} IDs de vulnerabilidade únicos do relatório Trivy."
    )
    return unique_vulnerability_ids


def rodar(trivy_full_report: dict, output_file_path: str):
    """Processa um relatório completo do Trivy, analisa CVEs com IA e armazena os resultados.

    Esta função orquestra o fluxo de trabalho de análise de um relatório Trivy.
    Ela extrai informações-chave do relatório, solicita um resumo de cenário à IA,
    busca detalhes de CVEs individuais, gera relatórios de IA para cada CVE
    e armazena os resultados em uma coleção MongoDB dedicada para a imagem.

    Args:
        trivy_full_report: O dicionário completo do relatório de análise Trivy
                           da imagem Docker.
        output_file_path: O caminho do arquivo onde o relatório Trivy foi salvo
                          (usado apenas para fins de log, não para leitura).
    """
    # Extrai metadados da imagem no relatório do Trivy, excluindo os resultados de vulnerabilidades.
    docker_metadata = {
        key: value for key, value in trivy_full_report.items() if key != "Results"
    }

    # Gera um resumo do cenário da imagem utilizando a IA.
    scenario_summary_ai_response = ai_LLM_resumo_do_cenario(docker_metadata)
    logging.info("Resumo do cenário da imagem gerado pela IA.")

    # Define o nome da coleção MongoDB com base no nome da imagem Trivy e se conecta a ele.
    collection_name = (
        trivy_full_report["ArtifactName"].replace("/", "_").replace(":", "_")
    )
    collection = db[collection_name]
    logging.info(f"Conectado à coleção MongoDB: '{collection_name}'")

    # Prepara o documento com o resumo do cenário da imagem docker gerado pela IA e insere no MongoDB.
    document_scenario_ai_analysis = {
        "analise_do_container": scenario_summary_ai_response
    }
    collection.insert_one(document_scenario_ai_analysis)
    logging.info("Resumo da análise do container pela IA inserido no MongoDB.")

    # Processa cada CVE encontrada no relatório Trivy individualmente.
    for cve_id in extrair_ids_vulnerabilidades(trivy_full_report):
        logging.info(f"Iniciando detalhamento e análise de IA para CVE: {cve_id}")

        # Busca detalhes completos da CVE no NIST NVD.
        detailed_cve_info = detalhar_CVE(cve_id)
        if detailed_cve_info is None:
            # Pula a CVE se os detalhes não puderem ser obtidos (insere informação no log).
            logging.warning(
                f"Detalhes para CVE '{cve_id}' não puderam ser obtidos. Pulando."
            )
            continue
        
        #Esse bloco pega apenas as informações úteis para a IA, 
        # isso evita o erro de exesso de tokens de entrada e economiza dinheiro
        dados_para_ia = detailed_cve_info[0].copy() # detalied_cve_info é uma lista com um único argumento.
        for campo in ['configurations', 'references', 'cpe']:
            dados_para_ia.pop(campo, None)
                
        # Gera um relatório de análise da CVE utilizando a IA.
        ai_cve_report = ai_LLM(dados_para_ia)
        logging.info(f"Relatório de IA gerado para CVE: {cve_id}")

        # Combina os detalhes da CVE e o relatório da IA e insere como um documento no MongoDB.
        cve_document_for_db = {"cve": detailed_cve_info, "relatorio": ai_cve_report}
        collection.insert_one(cve_document_for_db)
        logging.info(
            f"Documento da CVE '{cve_id}' (detalhes + relatório IA) inserido no MongoDB."
        )

    logging.info(
        f"Fim da análise e armazenamento para a imagem associada ao arquivo: {output_file_path}"
    )
