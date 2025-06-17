# 📄 Monteiro - Projeto Judiciário

Este projeto é uma aplicação Streamlit voltada para a extração e análise de dados jurídicos a partir de arquivos PDF. Ele realiza a extração de informações de tabelas, identifica documentos válidos e utiliza inteligência artificial (OpenAI) para extrair os principais dados da primeira página do processo.

---

## 🚀 Funcionalidades

1. **Upload de PDF**
   - Realizado pela barra lateral.
   - Aceita arquivos PDF com tabelas e dados de processos.

2. **Etapa 0: Extração Inteligente**
   - Utiliza o modelo GPT-4o da OpenAI para extrair automaticamente:
     - Número do processo
     - Classe
     - Órgão julgador
     - Data de distribuição
     - Valor da causa
     - Assunto
     - Partes (autor e réu)

3. **Etapa 1: Tabela extraída**
   - Extração da(s) tabela(s) usando `tabula-py`.
   - Identificação de colunas como ID, Tipo, Documento e Data de Assinatura.
   - Destaque visual para os documentos válidos.
   - Download da tabela como CSV.

4. **Etapa 2: Lista de IDs**
   - Lista apenas os IDs dos documentos marcados como válidos.

5. **Etapa 3: Geração de novo PDF**
   - Cria um novo PDF contendo apenas as páginas dos documentos válidos.
   - Exibe uma tabela com a contagem de quantas vezes cada ID aparece.
   - Permite o download do novo PDF.

---

## 📌 Requisitos

- Python 3.8+
- Java instalado (necessário para `tabula-py`)
- Dependências (listadas abaixo)

---

## 📦 Instalação

```bash
pip install -r requirements.txt
```

Ou instale manualmente:

```bash
pip install streamlit tabula-py pandas openai python-dotenv PyMuPDF
```

---

## 📁 Estrutura esperada do PDF

- Primeira página com os dados descritivos do processo.
- Páginas seguintes contendo tabelas (com colunas como ID, Tipo, etc).
- O ID do documento deve ser identificado com o prefixo **"Num."** no rodapé.

---

## 🧠 Como a IA funciona?

A IA é usada para analisar o texto bruto da primeira página e retornar um JSON estruturado com as informações processuais mais relevantes.

---

## 📬 Contato

Para dúvidas ou sugestões, entre em contato com [Eduardo Bonfim](mailto:eduardo.bonfim@monteiro.adv.br).

---

## 🛡️ Licença

Este projeto é de uso privado e interno.