import streamlit as st
import pandas as pd
# import tabula
import tempfile
import fitz  # PyMuPDF
from typing import List
from collections import Counter
from openai import OpenAI
import os
import json
import requests
from dotenv import load_dotenv
import re
import pdfplumber

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")  # Defina essa variável no .env

# Função para extrair as páginas de um PDF com base nos IDs relevantes
def extrair_paginas_relevantes(caminho_pdf: str, ids_validos: List[str]):
    doc = fitz.open(caminho_pdf)
    novo_pdf = fitz.open()

    paginas_mantidas = []
    ids_encontrados = []

    for i, pagina in enumerate(doc):
        texto = pagina.get_text("text")
        for linha in texto.splitlines()[::-1]:
            if "num." in linha.lower():
                try:
                    partes = linha.lower().split("num.")
                    id_texto = partes[1].strip().split()[0]
                    if id_texto in ids_validos:
                        novo_pdf.insert_pdf(doc, from_page=i, to_page=i)
                        paginas_mantidas.append(i)
                        ids_encontrados.append(id_texto)
                    break
                except:
                    continue

    if len(paginas_mantidas) == 0:
        raise ValueError("Nenhuma página corresponde aos IDs válidos com base em 'Num.'")

    caminho_saida = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    novo_pdf.save(caminho_saida)
    novo_pdf.close()
    doc.close()

    contagem_ids = Counter(ids_encontrados)
    df_contagem = pd.DataFrame(contagem_ids.items(), columns=["ID", "Quantidade de Páginas"])
    df_contagem = df_contagem.reset_index(drop=True)

    return caminho_saida, len(paginas_mantidas), len(contagem_ids), df_contagem

# Função para extrair dados do cabeçalho usando OpenAI
def extrair_dados_cabecalho_com_openai(texto: str):
    prompt = f"""
Você receberá abaixo o conteúdo da primeira página de um processo jurídico. Extraia e retorne como JSON os seguintes campos:

- numero_processo
- classe
- orgao_julgador
- data_distribuicao
- valor_causa
- assunto
- partes (com subcampos: autor e reu)

Texto da primeira página:

{texto}


Retorne somente o JSON.
"""

    resposta = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": prompt
        }],
        temperature=0.1
    )

    conteudo = resposta.choices[0].message.content

    if conteudo.startswith("```json"):
        conteudo = conteudo.strip("`").replace("json", "", 1).strip()
    elif conteudo.startswith("```"):
        conteudo = conteudo.strip("`").strip()

    try:
        return json.loads(conteudo)
    except Exception:
        return {"erro": "Não foi possível interpretar o JSON gerado.", "resposta": conteudo}


def limpar_cabecalho_pje(texto: str) -> str:
    linhas = texto.strip().splitlines()

    # Define padrões que representam as linhas padrão do cabeçalho
    padroes_remover = [
        r"^num\.\s*\d+\s*-\s*p[áa]g\.\s*\d+",  # ex: Num. 3610332 - Pág. 1
        r"^assinado eletronicamente por:.*",
        r"^https:\/\/.*",
        r"^n[úu]mero do documento:.*",
        r"^este documento foi gerado pelo usu[áa]rio.*"
    ]

    linhas_filtradas = []
    for linha in linhas:
        linha_normalizada = linha.strip().lower()
        if not any(re.match(p, linha_normalizada) for p in padroes_remover):
            linhas_filtradas.append(linha)

    return "\n".join(linhas_filtradas).strip()


st.set_page_config(page_title="Monteiro - Projeto Judiciário", layout="wide")
st.title("📄 Monteiro - Projeto Judiciário")

st.sidebar.title("Upload PDF")
uploaded_file = st.sidebar.file_uploader("📤 Envie o PDF com a(s) tabela(s)", type="pdf")

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        temp_pdf_path = tmp_file.name
        uploaded_file.seek(0)  # Reseta o ponteiro para reuso posterior
        pdf_bytes = uploaded_file.read()

    total_paginas_pdf = fitz.open(temp_pdf_path).page_count

    with fitz.open(temp_pdf_path) as doc:
        texto_primeira_pagina = doc[0].get_text()

    dados_extraidos = extrair_dados_cabecalho_com_openai(texto_primeira_pagina)

    with st.expander("Etapa 0: Dados extraídos da primeira página (IA)", expanded=True):
        st.json(dados_extraidos)

    st.divider()

    try:
        tabelas_total = []
        max_paginas = 50

        todas_tabelas = []

        with pdfplumber.open(temp_pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                if i >= max_paginas:
                    break
                try:
                    tabelas_na_pagina = page.extract_tables()
                    for tabela_raw in tabelas_na_pagina:
                        df = pd.DataFrame(tabela_raw)

                        # Ignora tabelas vazias ou com menos de 3 colunas
                        if df.empty or df.shape[1] < 3:
                            continue

                        # Padroniza colunas
                        primeira_linha = df.iloc[0].astype(str).str.lower().str.contains("id") | df.iloc[0].astype(str).str.contains("assinatura")
                        if primeira_linha.any():
                            df.columns = ['ID', 'Data da Assinatura', 'Documento', 'Tipo'][:len(df.columns)]
                            df = df.iloc[1:]  # Remove cabeçalho duplicado
                        else:
                            df.columns = ['ID', 'Data da Assinatura', 'Documento', 'Tipo'][:len(df.columns)]

                        # Filtra somente linhas com ID numérico
                        df['ID'] = df['ID'].astype(str)
                        df = df[df['ID'].str.isnumeric()]

                        if not df.empty:
                            tabelas_total.append(df)
                except Exception:
                    continue

        if tabelas_total:
            df_final = pd.concat(tabelas_total, ignore_index=True)
            df_final["Data da Assinatura"] = df_final["Data da Assinatura"].str.replace("\n", " ", regex=True)

            tipos_validos = [
                "Petição inicial", "Inicial", "Despacho", "Emenda à inicial", "Citação",
                "Contestação", "Petição Intercorrente", "Réplica", "Decisão", "Sentença", "Acórdão"
            ]
            def documento_valido(tipo):
                if pd.isnull(tipo): return "Não"
                tipo = tipo.strip().lower()
                return "Sim" if any(tipo == valido.lower() for valido in tipos_validos) else "Não"
            df_final["Documento Válido"] = df_final["Tipo"].apply(documento_valido)

            ids_validos = df_final[df_final["Documento Válido"] == "Sim"]["ID"].dropna().tolist()

            def highlight_sim(val):
                return 'background-color: #2B915D' if val == "Sim" else ''
            df_final_styled = df_final.style.applymap(highlight_sim, subset=["Documento Válido"])

            st.success("✅ Todas as tabelas extraídas com sucesso!")
            with st.expander("Etapa 1: Mostrar tabela extraída (clique para expandir/ocultar)"):
                st.info(f"📄 Total de páginas no PDF: **{total_paginas_pdf}**")
                st.info(f"🧾 Total de documentos distintos: **{df_final['ID'].nunique()}**")
                st.dataframe(df_final_styled, use_container_width=True)

                csv = df_final.to_csv(index=False).encode("utf-8")
                st.download_button("Baixar como CSV", data=csv, file_name="tabelas_extraidas.csv", mime="text/csv")

            with st.expander("Etapa 2: Mostrar lista de IDs com Documento Válido"):
                st.code(ids_validos)

            with st.expander("Etapa 3: Gerar PDF somente com documentos válidos"):
                if ids_validos:
                    try:
                        caminho_pdf_filtrado, total_paginas, total_ids, df_contagem = extrair_paginas_relevantes(temp_pdf_path, ids_validos)
                        st.info(f"📄 Total de páginas no novo PDF: **{total_paginas}**")
                        st.info(f"🧾 Total de documentos distintos: **{total_ids}**")
                        st.markdown("### 📊 Distribuição de páginas por ID")
                        st.dataframe(df_contagem, use_container_width=True)
                        with open(caminho_pdf_filtrado, "rb") as f:
                            st.download_button(
                                label="📥 Baixar PDF filtrado",
                                data=f,
                                file_name="documentos_validos.pdf",
                                mime="application/pdf"
                            )
                    except ValueError as e:
                        st.error(f"❌ {e}")
                else:
                    st.warning("Nenhum ID válido identificado para filtrar o PDF.")

            with st.expander("Etapa 4: Enviar dados do PDF filtrado para o N8N"):
                if "caminho_pdf_filtrado" in locals():
                    if st.button("🚀 Enviar PDF filtrado para o N8N"):
                        try:
                            doc_filtrado = fitz.open(caminho_pdf_filtrado)
                            linhas = []

                            for i, pagina in enumerate(doc_filtrado):
                                texto_original = pagina.get_text("text")
                                texto_limpo = limpar_cabecalho_pje(texto_original)

                                id_encontrado = None
                                tipo_documento = None

                                for linha in texto_original.splitlines()[::-1]:
                                    if "num." in linha.lower():
                                        try:
                                            partes = linha.lower().split("num.")
                                            id_texto = partes[1].strip().split()[0]
                                            id_encontrado = id_texto
                                            break
                                        except:
                                            continue

                                if id_encontrado:
                                    tipo_documento = df_final.loc[
                                        df_final["ID"] == id_encontrado, "Tipo"
                                    ].dropna().astype(str).values
                                    tipo_documento = tipo_documento[0] if len(tipo_documento) else None

                                linhas.append({
                                    "pagina": i + 1,
                                    "conteudo": texto_limpo + " ||||| ",
                                    "id_documento": id_encontrado,
                                    "tipo_documento": tipo_documento
                                })

                            df_paginas_filtradas = pd.DataFrame(linhas)

                            st.success("✅ Tabela com as páginas do PDF filtrado gerada com sucesso!")
                            st.dataframe(df_paginas_filtradas, use_container_width=True)

                            dados = {
                                "dados_cabecalho": json.dumps(dados_extraidos),
                                "tabela_paginas_filtradas": json.dumps(df_paginas_filtradas.to_dict(orient="records"))
                            }

                            resposta = requests.post(N8N_WEBHOOK_URL, data=dados)
                            if resposta.status_code == 200:
                                st.success("✅ Dados do PDF filtrado enviados com sucesso para o N8N!")
                            else:
                                st.error(f"❌ Erro ao enviar para o N8N: {resposta.text}")

                        except Exception as e:
                            st.error(f"❌ Falha na geração ou envio da tabela: {e}")
                else:
                    st.warning("⚠️ Você precisa primeiro gerar o PDF filtrado na Etapa 3.")

            with st.expander("Etapa 5: Executar Análise via N8N"):
                if st.button("📡 Chamar N8N e exibir resposta"):
                    try:
                        with st.spinner("Aguardando resposta do N8N..."):
                            resposta = requests.post(os.getenv("N8N_WEBHOOK_URL_2"))
                            if resposta.status_code == 200:
                                st.success("✅ Resposta recebida com sucesso!")

                                try:
                                    dados = resposta.json()
                                    relatorio = dados.get("relatorio") or resposta.text
                                except:
                                    relatorio = resposta.text

                                st.markdown("### 🧾 Relatório Gerado")
                                st.markdown(relatorio, unsafe_allow_html=True)

                            else:
                                st.error(f"❌ Erro na requisição: {resposta.status_code}")
                                st.text(resposta.text)
                    except Exception as e:
                        st.error(f"❌ Falha na comunicação com o N8N: {e}")

        else:
            st.warning("⚠️ Nenhuma tabela encontrada nas primeiras 50 páginas.")

    except Exception as e:
        st.error(f"❌ Erro ao processar o PDF: {e}")
