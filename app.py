import streamlit as st
import pandas as pd
import tabula
import tempfile
import fitz  # PyMuPDF
from typing import List
from collections import Counter
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Função para extrair as páginas de um PDF com base nos IDs relevantes
def extrair_paginas_relevantes(caminho_pdf: str, ids_validos: List[str]):
    doc = fitz.open(caminho_pdf)
    novo_pdf = fitz.open()

    paginas_mantidas = []
    ids_encontrados = []

    for i, pagina in enumerate(doc):
        texto = pagina.get_text("text")
        for linha in texto.splitlines()[::-1]:  # varre de baixo pra cima
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

    # Contagem de quantas vezes cada ID foi encontrado
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
\"\"\"
{texto}
\"\"\"

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

    # 🔧 Remove blocos markdown se existirem
    if conteudo.startswith("```json"):
        conteudo = conteudo.strip("`").replace("json", "", 1).strip()
    elif conteudo.startswith("```"):
        conteudo = conteudo.strip("`").strip()

    try:
        return json.loads(conteudo)
    except Exception:
        return {"erro": "Não foi possível interpretar o JSON gerado.", "resposta": conteudo}


st.set_page_config(page_title="Monteiro - Projeto Judiciário", layout="wide")
st.title("📄 Monteiro - Projeto Judiciário")

st.sidebar.title("Upload PDF")
uploaded_file = st.sidebar.file_uploader("📤 Envie o PDF com a(s) tabela(s)", type="pdf")

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        temp_pdf_path = tmp_file.name

        total_paginas_pdf = fitz.open(temp_pdf_path).page_count

    # Etapa 0: Extrair informações da primeira página com IA
    with fitz.open(temp_pdf_path) as doc:
        texto_primeira_pagina = doc[0].get_text()

    dados_extraidos = extrair_dados_cabecalho_com_openai(texto_primeira_pagina)

    with st.expander("Etapa 0: Dados extraídos da primeira página (IA)", expanded=True):
        st.json(dados_extraidos)

    st.divider()

    try:
        # Lista para juntar todos os DataFrames de tabelas
        tabelas_total = []
        max_paginas = 50

        # tabula.read_pdf permite especificar as páginas (1-indexed)
        paginas = list(range(1, max_paginas + 1))
        todas_tabelas = tabula.read_pdf(
            temp_pdf_path,
            pages=paginas,
            multiple_tables=True,
            guess=True,
            lattice=True,  # Melhora a detecção para PDFs mais "quadrados"
            pandas_options={"dtype": str}
        )

        for tabela in todas_tabelas:
            # Se a tabela está vazia, pula
            if tabela.empty or tabela.shape[1] < 3:
                continue
            # Tenta detectar e ajustar cabeçalho real
            primeira_linha = tabela.iloc[0].astype(str).str.lower().str.contains("id") | tabela.iloc[0].astype(str).str.contains("assinatura")
            if primeira_linha.any():
                tabela.columns = ['ID', 'Data da Assinatura', 'Documento', 'Tipo'][:len(tabela.columns)]
                tabela = tabela.iloc[1:]  # Remove a linha de cabeçalho
            else:
                tabela.columns = ['ID', 'Data da Assinatura', 'Documento', 'Tipo'][:len(tabela.columns)]
            tabelas_total.append(tabela)

        if tabelas_total:
            df_final = pd.concat(tabelas_total, ignore_index=True)
            # Limpa quebras de linha em datas
            df_final["Data da Assinatura"] = df_final["Data da Assinatura"].str.replace("\n", " ", regex=True)
            
            # --------- Adiciona coluna Documento Válido ---------
            tipos_validos = [
                "Petição inicial",
                "Inicial",
                "Despacho",
                "Emenda à inicial",
                "Citação",
                "Contestação",
                "Petição Intercorrente",
                "Réplica",
                "Decisão",
                "Sentença",
                "Acórdão"
            ]
            def documento_valido(tipo):
                if pd.isnull(tipo):
                    return "Não"
                tipo = tipo.strip().lower()
                return "Sim" if any(tipo == valido.lower() for valido in tipos_validos) else "Não"
            df_final["Documento Válido"] = df_final["Tipo"].apply(documento_valido)

            # --------- Gera lista de IDs válidos ---------
            ids_validos = df_final[df_final["Documento Válido"] == "Sim"]["ID"].dropna().tolist()

            # -----------------------------------------------------

            # ---- Destacar "Sim" na coluna Documento Válido ----
            def highlight_sim(val):
                color = 'background-color: #2B915D' if val == "Sim" else ''
                return color
            df_final_styled = df_final.style.applymap(highlight_sim, subset=["Documento Válido"])

            st.success("✅ Todas as tabelas extraídas com sucesso!")
            with st.expander("Etapa 1: Mostrar tabela extraída (clique para expandir/ocultar)"):
                
                st.info(f"📄 Total de páginas no PDF: **{total_paginas_pdf}**")
                st.info(f"🧾 Total de documentos distintos: **{df_final['ID'].nunique()}**")

                st.dataframe(df_final_styled, use_container_width=True)

                # Botão para baixar CSV
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

        else:
            st.warning("⚠️ Nenhuma tabela encontrada nas primeiras 50 páginas.")

    except Exception as e:
        st.error(f"❌ Erro ao processar o PDF: {e}")
