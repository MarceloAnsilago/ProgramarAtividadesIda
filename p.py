import streamlit as st
from datetime import date, timedelta
from io import BytesIO
import base64
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
import pdf_relatorio
from pdf_utils import generate_pdf_for_week
import streamlit.components.v1 as components
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date


# ------------------------------------------------------------------------------
# CSS para personalizar estilos
# ------------------------------------------------------------------------------
st.markdown("""
<style>
.summary-card {
    border: 1px solid #ccc; 
    border-radius: 5px; 
    padding: 10px; 
    margin: 5px 0;
    background-color: #ffffff;
}
.summary-flex {
    display: flex; 
    gap: 20px; 
    justify-content: space-between;
}
.summary-column {
    flex: 1; 
    min-width: 0; 
}
.full-width-hr {
    width: 100%;
    border: 1px solid #ccc;
    margin-top: 50px;
}
.day-title {
    font-size: 1.3rem !important;
    font-weight: 600 !important;
    margin: 0.5rem 0 0.5rem 0 !important;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Sessão e Estruturas de Dados
# ------------------------------------------------------------------------------
def init_plantao_session_state():
    st.session_state.setdefault("semanas", {})  # chave: "YYYY-WW" -> lista de datas
    st.session_state.setdefault("week_order", [])  # ordem de criação das semanas
    st.session_state.setdefault("atividades_dia", {})  # chave: "dd/mm/yyyy" -> lista de atividades
    st.session_state.setdefault("unavailable_periods", {})  # indisponibilidades por servidor
    st.session_state.setdefault("plantao_itens", [])  # escala gerada
    st.session_state.setdefault("checklist", {})  # controle de impressão (atividades/servidores marcados)
    st.session_state.setdefault("all_servidores", [])  # lista carregada de servidores
    st.session_state.setdefault("servidores", [])
    st.session_state.setdefault("all_atividades", [])  # lista de atividades disponíveis
    st.session_state.setdefault("all_veiculos", [])  # lista de veículos cadastrados
    st.session_state.setdefault("all_ul_sups", [])  # lista de supervisões/unidades se necessário

init_plantao_session_state()

if st.session_state.get("recarregar", False):
    st.session_state["recarregar"] = False
    st.rerun()

# Inicializa chaves necessárias, se ainda não existirem
if "week_order" not in st.session_state:
    st.session_state["week_order"] = []
if "unavailable_periods" not in st.session_state:
    st.session_state["unavailable_periods"] = {}
if "plantao_itens" not in st.session_state:
    st.session_state["plantao_itens"] = []

# Função para gerar blocos de plantão (Sábado a Sexta)
def gerar_blocos_sabado_sexta(data_inicio, data_fim, selected_names, itens, unavailable_periods):
    """
    Gera uma lista de blocos com a data e os servidores disponíveis,
    considerando que o plantão é para dias de sábado a sexta (excluindo domingos).
    """
    blocos = []
    current_date = data_inicio
    while current_date <= data_fim:
        # Se não for domingo (weekday() == 6)
        if current_date.weekday() != 6:
            disponiveis = []
            for nome in selected_names:
                # Se não houver período de indisponibilidade ou se o servidor estiver disponível
                if nome not in unavailable_periods or all(not (start <= current_date <= end)
                                                           for start, end in unavailable_periods[nome]):
                    disponiveis.append(nome)
            blocos.append({
                "data": current_date.strftime("%d/%m/%Y"),
                "disponiveis": disponiveis
            })
        current_date += timedelta(days=1)
    return blocos

# Função para gerar o HTML da escala para exibição via iframe
def gerar_html_para_iframe(blocos, ano, NOME_MESES, titulo_pagina="Programação de Atividades"):
    """
    Gera um HTML com <title> customizado para aparecer corretamente na aba do navegador.
    """
    html = f"""
    <html>
    <head>
        <meta charset='UTF-8'>
        <title>{titulo_pagina}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 20px;
            }}
            h2 {{
                color: #2c3e50;
            }}
            p {{
                margin-bottom: 8px;
            }}
        </style>
    </head>
    <body>
        <h2>Escala de Plantão - {ano}</h2>
    """
    for bloco in blocos:
        html += f"<p><strong>{bloco['data']}</strong>: {', '.join(bloco['disponiveis'])}</p>"
    
    html += """
    </body>
    </html>
    """
    return html


# Mapeamento do número do mês para o nome em português
month_map_pt = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
}

# Lista de ordinal para semanas no mês
ordinal_names = [
    "Primeira", "Segunda", "Terceira", "Quarta", "Quinta", "Sexta",
    "Sétima", "Oitava", "Nona", "Décima", "Décima Primeira", "Décima Segunda"
]

def get_ordinal_week_in_month(n: int) -> str:
    """Retorna o ordinal em português para a semana do mês (1->Primeira, 2->Segunda, etc.)"""
    if 1 <= n <= len(ordinal_names):
        return ordinal_names[n-1]
    else:
        return f"{n}ª"

# Dias da semana em português (para exibição)
dias_semana = {
    "Monday": "Segunda-feira",
    "Tuesday": "Terça-feira",
    "Wednesday": "Quarta-feira",
    "Thursday": "Quinta-feira",
    "Friday": "Sexta-feira",
    "Saturday": "Sábado",
    "Sunday": "Domingo"
}


# ------------------------------------------------------------------------------
# Funções Auxiliares para Programação
# ------------------------------------------------------------------------------
def get_week_id(ref_date):
    year, week, _ = ref_date.isocalendar()
    return f"{year}-W{week:02d}"

def get_week_dates(ref_date, include_saturday=False, include_sunday=False):
    """Retorna as datas da semana: sempre segunda a sexta; inclui sábado/domingo se marcado."""
    year, week, weekday = ref_date.isocalendar()
    monday = ref_date - timedelta(days=weekday - 1)
    dates = [monday + timedelta(days=i) for i in range(5)]
    if include_saturday:
        dates.append(monday + timedelta(days=5))
    if include_sunday:
        dates.append(monday + timedelta(days=6))
    return dates

def add_week_if_not_exists(ref_date, include_saturday=False, include_sunday=False):
    wid = get_week_id(ref_date)
    if wid not in st.session_state["semanas"]:
        st.session_state["semanas"][wid] = get_week_dates(ref_date, include_saturday, include_sunday)
        st.session_state["week_order"].append(wid)

        # Garante que "servidores" está disponível antes de usar
        servidores = st.session_state.get("servidores", [])
        for day_date in st.session_state["semanas"][wid]:
            add_activity_to_date(
                day_date,
                atividade="Expediente Administrativo",
                servidores=servidores,
                veiculo="Nenhum"
            )


def add_activity_to_date(activity_date, atividade, servidores, veiculo):
    date_str = activity_date.strftime("%d/%m/%Y")
    if date_str not in st.session_state["atividades_dia"]:
        st.session_state["atividades_dia"][date_str] = []
    st.session_state["atividades_dia"][date_str].append({
        "atividade": atividade,
        "servidores": servidores,
        "veiculo": veiculo
    })

def add_server_to_expediente(date_str, server):
    for act in st.session_state["atividades_dia"].get(date_str, []):
        if act["atividade"] == "Expediente Administrativo":
            if server not in act["servidores"]:
                act["servidores"].append(server)
            return


def remove_server_from_card(date_str, card_index, server):
    card = st.session_state["atividades_dia"][date_str][card_index]
    if card["atividade"] != "Expediente Administrativo":
        if server in card["servidores"]:
            card["servidores"].remove(server)
            add_server_to_expediente(date_str, server)



def remove_activity_card(date_str, card_index):
    card = st.session_state["atividades_dia"][date_str][card_index]
    for server in card["servidores"]:
        add_server_to_expediente(date_str, server)
    del st.session_state["atividades_dia"][date_str][card_index]

def remove_week(week_id):
    if week_id in st.session_state["semanas"]:
        for day_date in st.session_state["semanas"][week_id]:
            date_str = day_date.strftime("%d/%m/%Y")
            if date_str in st.session_state["atividades_dia"]:
                del st.session_state["atividades_dia"][date_str]
        del st.session_state["semanas"][week_id]
    if week_id in st.session_state["week_order"]:
        st.session_state["week_order"].remove(week_id)

# ------------------------------------------------------------------------------
# Resumo: conta itens (exceto Expediente Administrativo)
# ------------------------------------------------------------------------------
def get_summary_details_for_week(week_id):
    activities = {}
    servers = {}
    vehicles = {}
    week_dates = st.session_state["semanas"].get(week_id, [])
    for day_date in week_dates:
        date_str = day_date.strftime("%d/%m/%Y")
        day_acts = st.session_state["atividades_dia"].get(date_str, [])
        for act_idx, act in enumerate(day_acts):
            if act["atividade"] != "Expediente Administrativo":
                activities[act["atividade"]] = activities.get(act["atividade"], 0) + 1
                for s in act["servidores"]:
                    key_server = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                    if st.session_state.get(key_server, True):
                        servers[s] = servers.get(s, 0) + 1
                if act["veiculo"] and act["veiculo"] != "Nenhum":
                    vehicles[act["veiculo"]] = vehicles.get(act["veiculo"], 0) + 1
    return activities, servers, vehicles


# --------------------------------------------------
# FUNÇÕES AUXILIARES PARA IMPRESSÃO
# --------------------------------------------------
def build_cards_list(week_dates):
    """
    Retorna uma lista de dias (cards_list), onde cada dia contém apenas
    as atividades e servidores que estão marcados nos checkboxes.
    """
    cards_list = []
    for day_date in week_dates:
        date_str = day_date.strftime("%d/%m/%Y")
        day_name_en = day_date.strftime("%A")
        day_label = f"{dias_semana.get(day_name_en, day_name_en)} ({date_str})"

        day_acts = st.session_state["atividades_dia"].get(date_str, [])
        filtered_acts = []

        for act_idx, act in enumerate(day_acts):
            # 1) Se a atividade NÃO for "Expediente Administrativo", verificar se o checkbox da atividade está marcado
            if act["atividade"] != "Expediente Administrativo":
                act_key = f"checkbox_atividade_{date_str}_{act_idx}"
                if not st.session_state.get(act_key, True):
                    # Se estiver desmarcada, pula essa atividade
                    continue

            # 2) Filtrar servidores marcados
            filtered_servers = []
            for s in act["servidores"]:
                server_key = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                # Se o checkbox do servidor estiver marcado (ou não existir, por padrão True), inclui
                if st.session_state.get(server_key, True):
                    filtered_servers.append(s)

            # Se não for Exp. Administrativo e não sobrou nenhum servidor, podemos pular
            if act["atividade"] != "Expediente Administrativo" and not filtered_servers:
                continue

            # Monta uma nova atividade com os servidores filtrados
            new_act = {
                "atividade": act["atividade"],
                "servidores": filtered_servers,
                "veiculo": act["veiculo"]
            }
            filtered_acts.append(new_act)

        cards_list.append({
            "Dia": day_label,
            "Activities": filtered_acts
        })
    return cards_list


def build_atividades_por_servidor(week_dates):
    """
    Retorna um dicionário {servidor: [lista de atividades]} apenas com
    o que estiver marcado nos checkboxes (e ignorando "Expediente Administrativo").
    """
    atividades_por_servidor = {}
    for day_date in week_dates:
        date_str = day_date.strftime("%d/%m/%Y")
        day_acts = st.session_state["atividades_dia"].get(date_str, [])
        for act_idx, act in enumerate(day_acts):
            if act["atividade"] != "Expediente Administrativo":
                # Verifica se a atividade está marcada
                act_key = f"checkbox_atividade_{date_str}_{act_idx}"
                if not st.session_state.get(act_key, True):
                    continue  # pula se a atividade foi desmarcada

                # Filtra servidores marcados
                for s in act["servidores"]:
                    server_key = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                    if st.session_state.get(server_key, True):
                        if s not in atividades_por_servidor:
                            atividades_por_servidor[s] = []
                        atividades_por_servidor[s].append({
                            "Data": date_str,
                            "Atividade": act["atividade"]
                        })
    return atividades_por_servidor
# # === 1) Defina as funções auxiliares fora do bloco with tab3 ===

def alinhar_sabado_ou_proximo(data_ref):
    dia_semana = data_ref.weekday()
    if dia_semana <= 5:
        diff = 5 - dia_semana
    else:
        diff = 6
    return data_ref + timedelta(days=diff)

def servidor_indisponivel(nome_servidor, ini_bloco, fim_bloco, indisponibilidades):
    if nome_servidor not in indisponibilidades:
        return False
    for (ini_indisp, fim_indisp) in indisponibilidades[nome_servidor]:
        # Verifica sobreposição de intervalos
        if not (fim_bloco < ini_indisp or ini_bloco > fim_indisp):
            return True
    return False

def agrupar_blocos_mensalmente(blocos, NOME_MESES):
    grupos = {}
    for bloco in blocos:
        dt_start = bloco["start"]
        dt_end = bloco["end"]
        servidor = bloco["servidor"]
        telefone = bloco["telefone"]

        y = dt_start.year
        m = dt_start.month

        data_str = (f"Do dia {dt_start.strftime('%d/%m/%Y')} "
                    f"ao dia {dt_end.strftime('%d/%m/%Y')}")

        if (y, m) not in grupos:
            grupos[(y, m)] = []
        grupos[(y, m)].append({
            "Data": data_str,
            "Servidor": servidor,
            "Contato": telefone
        })
    return grupos

def gerar_html_para_iframe(blocos, ano, NOME_MESES):
    grupos = agrupar_blocos_mensalmente(blocos, NOME_MESES)
    html_head = f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: "Helvetica", sans-serif;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 20px;
        }}
        th, td {{
            border: 1px solid #999;
            padding: 6px 10px;
            text-align: left;
        }}
        h2 {{
            margin-top: 30px;
        }}
        @media print {{
            #printButton {{
                display: none;
            }}
        }}
    </style>
    <script>
        function printIframe() {{
            window.print();
        }}
    </script>
    </head>
    <body>
    <h3>Escala de Plantão IDARON para recebimento de vacinas agrotóxicos e produtos biológicos ({ano})</h3>
    """
    html_body = ""
    chaves_ordenadas = sorted(grupos.keys(), key=lambda x: (x[0], x[1]))
    for (year, month) in chaves_ordenadas:
        nome_mes = NOME_MESES[month]
        html_body += f'<h2>{nome_mes} de {year}</h2>\n'
        html_body += '<table>\n'
        html_body += '<tr><th>Data</th><th>Servidor</th><th>Contato</th></tr>\n'
        for item in grupos[(year, month)]:
            data_str = item["Data"]
            servidor = item["Servidor"]
            contato = item["Contato"]
            html_body += f"<tr><td>{data_str}</td><td>{servidor}</td><td>{contato}</td></tr>\n"
        html_body += '</table>\n'

    html_body += """
    <button id="printButton" onclick="printIframe()">Imprimir</button>
    """

    html_end = """
    </body>
    </html>
    """
    return html_head + html_body + html_end

def gerar_blocos_sabado_sexta(data_inicio, data_fim, nomes_selecionados, itens, indisponibilidades):
    dict_telefones = {nome: tel for (nome, tel) in itens}
    blocos = []

    sabado_inicial = alinhar_sabado_ou_proximo(data_inicio)
    if sabado_inicial > data_fim:
        return blocos

    idx_servidor = 0
    data_corrente = sabado_inicial

    while data_corrente <= data_fim:
        fim_bloco = data_corrente + timedelta(days=6)
        if fim_bloco > data_fim:
            fim_bloco = data_fim

        servidor_escolhido = None
        tentativas = 0
        while tentativas < len(nomes_selecionados):
            nome_atual = nomes_selecionados[idx_servidor]
            if not servidor_indisponivel(nome_atual, data_corrente, fim_bloco, indisponibilidades):
                servidor_escolhido = nome_atual
                idx_servidor = (idx_servidor + 1) % len(nomes_selecionados)
                break
            else:
                idx_servidor = (idx_servidor + 1) % len(nomes_selecionados)
                tentativas += 1

        if servidor_escolhido is None:
            blocos.append({
                "start": data_corrente,
                "end": fim_bloco,
                "servidor": "— Sem Servidor —",
                "telefone": ""
            })
        else:
            tel = dict_telefones.get(servidor_escolhido, "")
            blocos.append({
                "start": data_corrente,
                "end": fim_bloco,
                "servidor": servidor_escolhido,
                "telefone": tel
            })

        data_corrente = fim_bloco + timedelta(days=1)
        data_corrente = alinhar_sabado_ou_proximo(data_corrente)

    return blocos
def main_app():
  
    # ------------------------------------------------------------------------------
    # Layout com Abas
    # ------------------------------------------------------------------------------
    tab1, tab2, tab3 = st.tabs([
        "📊 Dados (Informações Gerais)", 
        "🗓️ Programação (Gerar programação de atividades)", 
        "📦 Programação para recebimento"
    ])
    # ------------------------------------------------------------------------------
    # Aba 1: Dados
    # ------------------------------------------------------------------------------
    with tab1:
        # Configurações do Supabase
        SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wlbvahpkcaksqkzdhnbv.supabase.co")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndsYnZhaHBrY2Frc3FremRobmJ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDMyODMxMTUsImV4cCI6MjA1ODg1OTExNX0.Cph86UhT8Q67-1x2oVfTFyELgQqWRgJ3yump1JpHSc8")
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
         # Função para carregar os escritórios (unidades)
        def get_escritorios():
            res = supabase.table("unidades").select("*").execute()
            if res.data:
                return res.data  # Lista de dicts
            else:
                return []

        # Inicializa chaves do session_state se não existirem
        if "all_servidores" not in st.session_state:
            st.session_state["all_servidores"] = []
        if "all_atividades" not in st.session_state:
            st.session_state["all_atividades"] = []
        if "all_veiculos" not in st.session_state:
            st.session_state["all_veiculos"] = []
        if "all_ul_sups" not in st.session_state:
            st.session_state["all_ul_sups"] = []
        if "unavailable_periods" not in st.session_state:
            st.session_state["unavailable_periods"] = {}

   
        
        # Filtra a aplicação pela unidade selecionada (do login)
        unidade_nome = st.session_state.get("selected_unidade", None)
        unidade_id = st.session_state.get("selected_unidade_id", None)
        usuario_admin = st.session_state.get("is_admin", False)

        if unidade_nome and unidade_id:
            st.write(f"🏢 Unidade de: {unidade_nome} (ID: {unidade_id})")
        else:
            if usuario_admin:
                st.warning("⚠️ Nenhuma unidade selecionada.")
                
        # --- PARTE DE DADOS (Uploads e multiselects) ---
        st.header("🛠️ Gerenciar Dados")
     
     
        # --- TABS DE CRUD (Servidores, Atividades, Veículos) ---
        tabs_crud = st.tabs(["🧑‍💼 Servidores", "🗂️ Atividades", "🚗 Veículos"])
       
        # -------- ABA 1: Servidores --------
        with tabs_crud[0]:
            st.header("🧑‍💼 Gerenciamento de Servidores")
            # Se houver um filtro de unidade, aplica-o
            if unidade_id:
                res_serv = supabase.table("servidores").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_serv = supabase.table("servidores").select("*").execute()
            if res_serv.data:
                st.subheader("📋 Servidores Cadastrados")
                st.dataframe(res_serv.data)
            else:
                st.info("Nenhum servidor cadastrado.")
            
            st.write("---")
            st.subheader("➕ Cadastrar Novo Servidor")
            # Carrega escritórios para escolha
            lista_escritorios = get_escritorios()
            dict_escritorios = {esc["nome"]: esc["id"] for esc in lista_escritorios}
            nomes_escritorios = list(dict_escritorios.keys())
            # Se a unidade já foi selecionada, usa-a; caso contrário, permite escolha
            if unidade_id:
                st.write(f"Escritório: {st.session_state.get('selected_unidade')}")
                chosen_esc_id = unidade_id
            else:
                esc_escolhido_nome = st.selectbox("Escritório", nomes_escritorios, key="esc_escolhido_servidor")
                chosen_esc_id = dict_escritorios[esc_escolhido_nome]
            with st.form("cadastro_servidor"):
                novo_nome = st.text_input("Nome do Servidor", key="novo_nome_servidor")
                novo_telefone = st.text_input("Telefone", key="novo_telefone_servidor")
                nova_matricula = st.text_input("Matrícula", key="nova_matricula_servidor")
                novo_cargo = st.text_input("Cargo", key="novo_cargo_servidor")
                status_servidor = st.checkbox("Ativo?", value=True, key="status_servidor_cadastro")
                submit_cadastro_serv = st.form_submit_button("➕ Cadastrar Servidor")
            if submit_cadastro_serv:
                status_val = "Ativo" if status_servidor else "Inativo"
                insert_res = supabase.table("servidores").insert({
                    "nome": novo_nome,
                    "telefone": novo_telefone,
                    "matricula": nova_matricula,
                    "cargo": novo_cargo,
                    "status": status_val,
                    "escritorio_id": chosen_esc_id
                }).execute()
                if insert_res.data:
                    st.success("✅ Servidor cadastrado com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ Erro ao cadastrar o servidor. {insert_res.error}")
            st.write("---")
            st.subheader("✏️ Editar Servidor Existente")
            if unidade_id:
                res_edit_serv = supabase.table("servidores").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_edit_serv = supabase.table("servidores").select("*").execute()
            servidores_edit = res_edit_serv.data if res_edit_serv.data else []
            if servidores_edit:
                servidor_escolhido = st.selectbox("Selecione o Servidor para editar",
                                                options=servidores_edit,
                                                format_func=lambda x: x["nome"],
                                                key="select_servidor_editar")
                if servidor_escolhido:
                    novo_nome_edit = st.text_input("Novo Nome", value=servidor_escolhido["nome"], key=f"nome_edit_{servidor_escolhido['id']}")
                    novo_telefone_edit = st.text_input("Telefone", value=servidor_escolhido.get("telefone", ""), key=f"tel_edit_{servidor_escolhido['id']}")
                    nova_matricula_edit = st.text_input("Matrícula", value=servidor_escolhido.get("matricula", ""), key=f"mat_edit_{servidor_escolhido['id']}")
                    novo_cargo_edit = st.text_input("Cargo", value=servidor_escolhido.get("cargo", ""), key=f"cargo_edit_{servidor_escolhido['id']}")
                    st.write(f"Escritório atual (ID): {servidor_escolhido.get('escritorio_id')}")
                  
                    status_padrao = (servidor_escolhido.get("status", "Inativo") == "Ativo")

                    status_edit = st.checkbox("Ativo?", value=status_padrao, key=f"status_serv_{servidor_escolhido['id']}")
                    if st.button("🔄 Atualizar Servidor", key=f"btn_atualizar_serv_{servidor_escolhido['id']}"):
                        status_val_edit = "Ativo" if status_edit else "Inativo"
                        update_res = supabase.table("servidores").update({
                            "nome": novo_nome_edit,
                            "telefone": novo_telefone_edit,
                            "matricula": nova_matricula_edit,
                            "cargo": novo_cargo_edit,
                            "status": status_val_edit
                        }).eq("id", servidor_escolhido["id"]).execute()
                        if update_res.data:
                            st.success("Servidor atualizado com sucesso!")
                            st.rerun()
                        else:
                            st.error("Erro ao atualizar o servidor!")
            else:
                st.info("Não há servidores para editar.")

        # -------- ABA 2: Atividades --------
        with tabs_crud[1]:
            st.header("Gerenciamento de Atividades")
            if unidade_id:
                res_ativ = supabase.table("atividades").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_ativ = supabase.table("atividades").select("*").execute()
            if res_ativ.data:
                st.subheader("Atividades Cadastradas")
                st.dataframe(res_ativ.data)
            else:
                st.info("Nenhuma atividade cadastrada.")
            st.write("---")
            st.subheader("Cadastrar Nova Atividade")
            lista_escritorios_ativ = get_escritorios()
            dict_escritorios_ativ = {esc["nome"]: esc["id"] for esc in lista_escritorios_ativ}
            nomes_escritorios_ativ = list(dict_escritorios_ativ.keys())
            if unidade_id:
                st.write(f"Escritório: {st.session_state.get('selected_unidade')}")
                chosen_esc_ativ = unidade_id
            else:
                esc_nome_ativ = st.selectbox("Escritório", nomes_escritorios_ativ, key="esc_ativ_cadastro")
                chosen_esc_ativ = dict_escritorios_ativ[esc_nome_ativ]
            with st.form("cadastro_atividade"):
                desc_atividade = st.text_input("Descrição", key="desc_atividade")
                data_atividade = st.date_input("Data", key="data_atividade")
                status_atividade = st.checkbox("Ativo?", value=True, key="status_atividade_cadastro")
                submit_cadastro_ativ = st.form_submit_button("Cadastrar Atividade")
            if submit_cadastro_ativ:
                status_val = "Ativo" if status_atividade else "Inativo"
                insert_res = supabase.table("atividades").insert({
                    "descricao": desc_atividade,
                    "data": data_atividade.isoformat(),
                    "status": status_val,
                    "escritorio_id": chosen_esc_ativ
                }).execute()
                if insert_res.data:
                    st.success("Atividade cadastrada com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro ao cadastrar a atividade: {insert_res.error}")
            st.write("---")
            st.subheader("Editar Atividade Existente")
            if unidade_id:
                res_edit_ativ = supabase.table("atividades").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_edit_ativ = supabase.table("atividades").select("*").execute()
            atividades_edit = res_edit_ativ.data if res_edit_ativ.data else []
            if atividades_edit:
                atividade_escolhida = st.selectbox(
                    "Selecione a Atividade para editar",
                    options=atividades_edit,
                    format_func=lambda x: x["descricao"],
                    key="select_atividade_editar"
                )
                if atividade_escolhida:
                    nova_desc_edit = st.text_input("Nova Descrição", value=atividade_escolhida["descricao"], key=f"desc_edit_{atividade_escolhida['id']}")
                    # data_atv_edit = st.date_input("Data", value=atividade_escolhida.get("data",""), key=f"data_edit_{atividade_escolhida['id']}")
                    data_str = atividade_escolhida.get("data", "")
                    if isinstance(data_str, str) and data_str:
                        try:
                            valor_data = datetime.strptime(data_str, "%Y-%m-%d").date()
                        except ValueError:
                            valor_data = date.today()
                    elif isinstance(data_str, date):
                        valor_data = data_str
                    else:
                        valor_data = date.today()

                    data_atv_edit = st.date_input(
                        "Data",
                        value=valor_data,
                        key=f"data_edit_{atividade_escolhida['id']}"
                    )
                                    
                   
                   
                    status_padrao_ativ = (atividade_escolhida.get("status","Inativo") == "Ativo")
                    status_edit_ativ = st.checkbox("Ativo?", value=status_padrao_ativ, key=f"status_ativ_{atividade_escolhida['id']}")
                    if unidade_id:
                        st.write(f"Escritório: {st.session_state.get('selected_unidade')}")
                        chosen_esc_edit = unidade_id
                    else:
                        esc_nome_edit = st.selectbox("Escritório", nomes_escritorios_ativ,
                                                    index=nomes_escritorios_ativ.index(atividade_escolhida["escritorio_id"]) if atividade_escolhida["escritorio_id"] in nomes_escritorios_ativ else 0,
                                                    key=f"esc_edit_ativ_{atividade_escolhida['id']}")
                        chosen_esc_edit = dict_escritorios_ativ[esc_nome_edit]
                    if st.button("Atualizar Atividade", key=f"btn_atualizar_ativ_{atividade_escolhida['id']}"):
                        status_val_edit = "Ativo" if status_edit_ativ else "Inativo"
                        update_res = supabase.table("atividades").update({
                            "descricao": nova_desc_edit,
                            "data": str(data_atv_edit),
                            "status": status_val_edit,
                            "escritorio_id": chosen_esc_edit
                        }).eq("id", atividade_escolhida["id"]).execute()
                        if update_res.data:
                            st.success("Atividade atualizada com sucesso!")
                            st.rerun()
                        else:
                            st.error("Erro ao atualizar a atividade!")
            else:
                st.info("Não há atividades para editar.")

        # -------- ABA 3: Veículos --------
        with tabs_crud[2]:
            st.header("Gerenciamento de Veículos")
            if unidade_id:
                res_veic = supabase.table("veiculos").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_veic = supabase.table("veiculos").select("*").execute()
            if res_veic.data:
                st.subheader("Veículos Cadastrados")
                st.dataframe(res_veic.data)
            else:
                st.info("Nenhum veículo cadastrado.")
            st.write("---")
            st.subheader("Cadastrar Novo Veículo")
            lista_escritorios_veic = get_escritorios()
            dict_escritorios_veic = {esc["nome"]: esc["id"] for esc in lista_escritorios_veic}
            nomes_escritorios_veic = list(dict_escritorios_veic.keys())
            if unidade_id:
                st.write(f"Escritório: {st.session_state.get('selected_unidade')}")
                chosen_esc_veic = unidade_id
            else:
                esc_nome_veic = st.selectbox("Escritório", nomes_escritorios_veic, key="esc_veic_cadastro")
                chosen_esc_veic = dict_escritorios_veic[esc_nome_veic]
            with st.form("cadastro_veiculo"):
                nome_veic = st.text_input("Nome do Veículo", key="nome_veiculo")
                status_veic = st.checkbox("Ativo?", value=True, key="status_veiculo_cadastro")
                submit_cadastro_veic = st.form_submit_button("Cadastrar Veículo")
            if submit_cadastro_veic:
                status_val = "Ativo" if status_veic else "Inativo"
                insert_veic = supabase.table("veiculos").insert({
                    "veiculo": nome_veic,
                    "status": status_val,
                    "escritorio_id": chosen_esc_veic
                }).execute()
                if insert_veic.data:
                    st.success("Veículo cadastrado com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro ao cadastrar o veículo: {insert_veic.error}")
            st.write("---")
            st.subheader("Editar Veículo Existente")
            if unidade_id:
                res_edit_veic = supabase.table("veiculos").select("*").eq("escritorio_id", unidade_id).execute()
            else:
                res_edit_veic = supabase.table("veiculos").select("*").execute()
            veiculos_edit = res_edit_veic.data if res_edit_veic.data else []
            if veiculos_edit:
                veic_escolhido = st.selectbox(
                    "Selecione o Veículo para editar",
                    options=veiculos_edit,
                    format_func=lambda x: x["veiculo"],
                    key="select_veic_editar"
                )
                if veic_escolhido:
                    novo_nome_veic = st.text_input("Novo Nome do Veículo", value=veic_escolhido["veiculo"], key=f"nome_veic_{veic_escolhido['id']}")
                    status_padrao_veic = (veic_escolhido.get("status", "Inativo") == "Ativo")
                    status_ativo_veic_edit = st.checkbox("Ativo?", value=status_padrao_veic, key=f"status_veic_{veic_escolhido['id']}")
                    st.write(f"Escritório atual (ID): {veic_escolhido.get('escritorio_id')}")
                    if st.button("Atualizar Veículo", key=f"btn_atualizar_veic_{veic_escolhido['id']}"):
                        status_val_edit = "Ativo" if status_ativo_veic_edit else "Inativo"
                        update_veic = supabase.table("veiculos").update({
                            "veiculo": novo_nome_veic,
                            "status": status_val_edit
                            # Não atualizamos o 'escritorio_id'
                        }).eq("id", veic_escolhido["id"]).execute()
                        if update_veic.data:
                            st.success("Veículo atualizado com sucesso!")
                            st.rerun()
                        else:
                            st.error("Erro ao atualizar o veículo!")
            else:
                st.info("Não há veículos para editar.")
    # ------------------------------------------------------------------------------
    # Aba 2: Programação
    # ------------------------------------------------------------------------------
    # ======================================================
    # FUNÇÕES AUXILIARES PARA IMPRESSÃO
    # ======================================================
    def build_cards_list(week_dates):
        """
        Monta a lista de cards (dia a dia) para a impressão,
        filtrando as atividades e servidores com base no estado dos checkboxes.
        """
        cards_list = []
        for day_date in week_dates:
            date_str = day_date.strftime("%d/%m/%Y")
            day_name_en = day_date.strftime("%A")
            day_label = f"{dias_semana.get(day_name_en, day_name_en)} ({date_str})"
            
            day_acts = st.session_state["atividades_dia"].get(date_str, [])
            filtered_acts = []
            for act_idx, act in enumerate(day_acts):
                # Para atividades diferentes de "Expediente Administrativo",
                # verificamos se o checkbox da atividade está marcado.
                if act["atividade"] != "Expediente Administrativo":
                    act_key = f"checkbox_atividade_{date_str}_{act_idx}"
                    if not st.session_state.get(act_key, True):
                        continue  # ignora atividade desmarcada
                
                # Filtra servidores: inclui apenas os que estiverem marcados.
                filtered_servers = []
                for s in act["servidores"]:
                    server_key = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                    if st.session_state.get(server_key, True):
                        filtered_servers.append(s)
                # Se não for Expediente e não houver servidores, ignora a atividade
                if act["atividade"] != "Expediente Administrativo" and not filtered_servers:
                    continue

                new_act = {
                    "atividade": act["atividade"],
                    "servidores": filtered_servers,
                    "veiculo": act["veiculo"]
                }
                filtered_acts.append(new_act)
            cards_list.append({
                "Dia": day_label,
                "Activities": filtered_acts
            })
        return cards_list


    def build_atividades_por_servidor(week_dates):
        """
        Monta um dicionário {servidor: [lista de atividades]} para a impressão,
        considerando somente atividades e servidores com checkbox marcado.
        """
        atividades_por_servidor = {}
        for day_date in week_dates:
            date_str = day_date.strftime("%d/%m/%Y")
            day_acts = st.session_state["atividades_dia"].get(date_str, [])
            for act_idx, act in enumerate(day_acts):
                if act["atividade"] != "Expediente Administrativo":
                    act_key = f"checkbox_atividade_{date_str}_{act_idx}"
                    if not st.session_state.get(act_key, True):
                        continue  # atividade desmarcada
                    for s in act["servidores"]:
                        server_key = f"checkbox_servidor_{date_str}_{act_idx}_{s}"
                        if st.session_state.get(server_key, True):
                            if s not in atividades_por_servidor:
                                atividades_por_servidor[s] = []
                            atividades_por_servidor[s].append({
                                "Data": date_str,
                                "Atividade": act["atividade"]
                            })
        return atividades_por_servidor


    # ===================== INÍCIO DA ABA 2 =====================
    with tab2:
        col1, col2, col3,col4 = st.columns([2,2,1,1])
        # --- Coluna 1: Servidores Programação de Atividades ---
        with col1:
            unidade_id = st.session_state.get("selected_unidade_id", None)
            if unidade_id:
                res_serv = supabase.table("servidores").select("nome").eq("escritorio_id", unidade_id).execute()
                if res_serv.data:
                    # Extrai o primeiro nome de cada servidor
                    # nomes_servidores = [server["nome"].split()[0] for server in res_serv.data]
                    nomes_servidores = [server["nome"] for server in res_serv.data]


                else:
                    nomes_servidores = []
            else:
                nomes_servidores = []
            
            st.write("### 🧑‍💼 Servidores")
            sel_serv = st.multiselect(
                "Selecione os Servidores",
                nomes_servidores,
                default=nomes_servidores,
                key="multiselect_servidores_programacao_dados"
            )
            st.session_state["servidores"] = sel_serv

        # --- Coluna 2: Atividades ---
        with col2:
            unidade_id = st.session_state.get("selected_unidade_id", None)
            if unidade_id:
                res_ativ = supabase.table("atividades").select("descricao").eq("escritorio_id", unidade_id).execute()
                if res_ativ.data:
                    atividades_list = [atividade["descricao"] for atividade in res_ativ.data]
                else:
                    atividades_list = []
            else:
                atividades_list = []

            st.write("### 🗂️ Atividades")
            sel_ativ = st.multiselect(
                "Selecione as Atividades",
                atividades_list,
                default=atividades_list,
                key="multiselect_atividades"
            )
            st.session_state["atividades"] = sel_ativ

        # --- Coluna 3: Veículos ---
        with col3:
            unidade_id = st.session_state.get("selected_unidade_id", None)
            if unidade_id:
                res_veic = supabase.table("veiculos").select("veiculo").eq("escritorio_id", unidade_id).execute()
                if res_veic.data:
                    veiculos_list = [veic["veiculo"] for veic in res_veic.data]
                else:
                    veiculos_list = []
            else:
                veiculos_list = []

            st.write("### 🚗 Veículos")
            sel_veic = st.multiselect(
                "Selecione os Veículos",
                veiculos_list,
                default=veiculos_list,
                key="multiselect_veiculos"
            )
            st.session_state["veiculos"] = sel_veic

        # # --- Coluna 4: ULSAV e Supervisão ---
        with col4:
            unidade_id = st.session_state.get("selected_unidade_id", None)
            if unidade_id:
                res_unidade = supabase.table("unidades").select("nome, supervisao").eq("id", unidade_id).execute()
                if res_unidade.data and len(res_unidade.data) > 0:
                    row = res_unidade.data[0]
                    st.session_state["all_ul_sups"] = [row["nome"], row["supervisao"]]
                else:
                    st.session_state["all_ul_sups"] = []
            else:
                st.session_state["all_ul_sups"] = []

            st.write("### 📝ULSAV e Supervisão")

            sel_ul_sups = st.multiselect(
                "Selecione ULSAV/ Supervisão",
                st.session_state["all_ul_sups"],
                default=st.session_state["all_ul_sups"],
                key="multiselect_ul_sups"
            )
            st.session_state["ul_sups"] = sel_ul_sups

        st.header("📋 Programação de Atividades")
        if (not st.session_state["servidores"]) or (not st.session_state["atividades"]) or (not st.session_state["veiculos"]):
            st.warning("Carregue e selecione Servidores, Atividades e Veículos na aba 'Dados'.")
        else:
            # Atualiza os cartões de "Expediente Administrativo" (mantém apenas os servidores ativos)
            for ds, atividades in st.session_state.get("atividades_dia", {}).items():
                for atividade in atividades:
                    if atividade["atividade"] == "Expediente Administrativo":
                        atividade["servidores"] = [s for s in atividade["servidores"] if s in st.session_state["servidores"]]

            st.write("📅 Selecione uma data para criar (ou visualizar) a semana correspondente:")

            selected_date = st.date_input("Data para a semana:", value=date.today())

            colA, colB = st.columns(2)
            with colA:
                include_saturday = st.checkbox("Incluir Sábado", value=False)
            with colB:
                include_sunday = st.checkbox("Incluir Domingo", value=False)

            if st.button("🗓️Adicionar Semana"):
                add_week_if_not_exists(selected_date, include_saturday, include_sunday)
                st.session_state["recarregar"] = True
                st.rerun()

            st.markdown("---")

            if st.session_state["week_order"]:
                # Gera os rótulos das semanas
                labels = []
                if st.session_state["week_order"]:
                    for wid in st.session_state["week_order"]:
                        week_dates = st.session_state["semanas"].get(wid, [])
                        if not week_dates:
                            labels.append("Semana vazia")
                            continue

                        first_date = week_dates[0]
                        year = first_date.year
                        month = first_date.month
                        _, week_number = first_date.isocalendar()[:2]
                        first_day_of_month = date(year, month, 1)
                        _, first_week_number = first_day_of_month.isocalendar()[:2]
                        week_position_in_month = week_number - first_week_number + 1
                        if week_position_in_month < 1:
                            week_position_in_month = 1
                        ordinal_name = get_ordinal_week_in_month(week_position_in_month)
                        month_name_pt = month_map_pt[month]
                        labels.append(f"{ordinal_name} semana do mês de {month_name_pt}")

                weeks_tabs = st.tabs(labels)

                for idx, wid in enumerate(st.session_state["week_order"]):
                    with weeks_tabs[idx]:
                        st.markdown(f"##### {labels[idx]}")
                        # Linha superior: Excluir Semana | Formulário para adicionar atividade | Resumo visual
                        top_col1, top_col2, top_col3 = st.columns([1,1,1])

                        with top_col1:
                            if st.button("🗑️Excluir Semana", key=f"excluir_{wid}"):
                                remove_week(wid)
                                st.warning(f"Semana {wid} excluída!")
                                st.rerun()

                        week_dates = st.session_state["semanas"][wid]
                        day_options = [f"{dias_semana[d.strftime('%A')]} - {d.strftime('%d/%m/%Y')}" for d in week_dates]
                        option_to_date = {option: d for option, d in zip(day_options, week_dates)}

                        with top_col2:
                            chosen_day = st.selectbox("Selecione o dia", day_options, key=f"dia_select_{wid}")
                            chosen_date = option_to_date[chosen_day]
                            st.write(f"#### ➕ Adicionar Nova Atividade ({chosen_day})")

                            # Função para obter os servidores já alocados no dia (exceto Expediente)
                            def get_alocados_no_dia(chosen_date):
                                ds = chosen_date.strftime("%d/%m/%Y")
                                alocados = set()
                                if ds in st.session_state["atividades_dia"]:
                                    for act in st.session_state["atividades_dia"][ds]:
                                        if act["atividade"] != "Expediente Administrativo":
                                            for s in act["servidores"]:
                                                alocados.add(s)
                                return alocados

                            alocados_hoje = get_alocados_no_dia(chosen_date)
                            _, servers_summary, _ = get_summary_details_for_week(wid)

                            def format_server_name(server: str) -> str:
                                count = servers_summary.get(server, 0)
                                if server in alocados_hoje:
                                    return f"{server} (já alocado, {count})"
                                else:
                                    return f"{server} ({count})"

                            with st.form(key=f"form_nova_atividade_{wid}"):
                                atividade_escolhida = st.selectbox("Atividade", st.session_state["atividades"])
                                available_servers = st.session_state["servidores"]
                                servidores_escolhidos = st.multiselect(
                                    "Servidores (semana atual: contagem de alocações)",
                                    options=available_servers,
                                    default=[],
                                    format_func=format_server_name,
                                    placeholder="Selecione um ou mais servidores..."
                                )
                                veiculo_escolhido = st.selectbox("Veículo", st.session_state["veiculos"])
                                if st.form_submit_button("➕Adicionar Atividade"):
                                    ds = chosen_date.strftime("%d/%m/%Y")
                                    if ds in st.session_state["atividades_dia"]:
                                        for a_idx, act in enumerate(st.session_state["atividades_dia"][ds]):
                                            if act["atividade"] == "Expediente Administrativo":
                                                act["servidores"] = [s for s in act["servidores"] if s not in servidores_escolhidos]
                                                break
                                    add_activity_to_date(chosen_date, atividade_escolhida, servidores_escolhidos, veiculo_escolhido)
                                    st.rerun()

                        # with top_col3:
                        with top_col3:
                       # Resumo visual da semana
                            dias_com_atividades = []
                            for d in week_dates:
                                ds = d.strftime("%d/%m/%Y")
                                day_name_pt = dias_semana.get(d.strftime("%A"), d.strftime("%A"))
                                acts = st.session_state["atividades_dia"].get(ds, [])
                                if any(act["atividade"] != "Expediente Administrativo" for act in acts):
                                    dias_com_atividades.append(day_name_pt)
                            dias_label = "<br>".join(dias_com_atividades) if dias_com_atividades else "Nenhum"

                            activities_summary, servers_summary, vehicles_summary = get_summary_details_for_week(wid)

                            # CSS customizado do card
                            st.markdown(
                                """
                                <style>
                                .summary-card {
                                    border: 1px solid #ccc;
                                    padding: 10px;
                                    border-radius: 5px;
                                    margin-bottom: 10px;
                                    background: #f9f9f9;
                                }
                                .summary-flex {
                                    display: flex;
                                    flex-direction: row;
                                    justify-content: space-between;
                                }
                                .summary-column {
                                    flex: 1;
                                    padding: 5px;
                                    margin-right: 10px;
                                }
                                .summary-column:last-child {
                                    margin-right: 0;
                                }
                                </style>
                                """,
                                unsafe_allow_html=True
                            )

                            # Monta o HTML do card com 4 colunas
                            summary_html = f"""
                            <div class="summary-card">
                            <strong>📊 Resumo da Semana</strong>
                            <div class="summary-flex">
                                <div class="summary-column">
                                <u>📅 Dia:</u><br>{dias_label}
                                </div>
                                <div class="summary-column">
                                <u>🗂️ Atividades:</u><br>"""
                            if activities_summary:
                                for act, count in activities_summary.items():
                                    summary_html += f"{act}: {count}<br>"
                            else:
                                summary_html += "Nenhuma<br>"

                            summary_html += """</div>
                                <div class="summary-column">
                                <u>👥Servidores:</u><br>"""
                            if servers_summary:
                                for serv, count in servers_summary.items():
                                    primeiro_nome = serv.split()[0]
                                    summary_html += f"{primeiro_nome}: {count}<br>"
                            else:
                                summary_html += "Nenhum<br>"

                            summary_html += """</div>
                                <div class="summary-column">
                                <u>🚗Veículos:</u><br>"""
                            if vehicles_summary:
                                for veic, count in vehicles_summary.items():
                                    summary_html += f"{veic}: {count}<br>"
                            else:
                                summary_html += "Nenhum<br>"

                            summary_html += """</div>
                            </div>
                            </div>"""

                            # Exibe o card de resumo
                            st.markdown(summary_html, unsafe_allow_html=True)

                        st.markdown("---")

                        # =========== Listagem das atividades (um bloco por dia) ===========
                        cols = st.columns(len(week_dates))
                        for j, current_date in enumerate(week_dates):
                            with cols[j]:
                                ds = current_date.strftime("%d/%m/%Y")
                                day_name_en = current_date.strftime("%A")
                                day_name_pt = dias_semana.get(day_name_en, day_name_en)

                                # Exibe o título do dia
                                st.markdown(f"##### {day_name_pt} - {ds}")

                                day_acts = st.session_state["atividades_dia"].get(ds, [])
                                if day_acts:
                                    for act_idx, atividade in enumerate(day_acts):
                                        st.markdown(f"##### Atividade: {atividade['atividade']}")
                                        if atividade["atividade"] != "Expediente Administrativo":
                                            activity_checked = st.checkbox(
                                                f"Marcar atividade: {atividade['atividade']}",
                                                value=True,
                                                key=f"checkbox_atividade_{ds}_{act_idx}",
                                                help="Desmarque para remover essa atividade."
                                            )
                                            if not activity_checked:
                                                remove_activity_card(ds, act_idx)
                                                st.rerun()

                                            st.write("👥 Servidores: (❌ desmarque para remover da atividade e retornar para 🗂️ Expediente Administrativo)")

                                            for s in atividade["servidores"][:]:
                                                key_server = f"checkbox_servidor_{ds}_{act_idx}_{s}"
                                                server_checked = st.checkbox(
                                                    s,
                                                    value=True,
                                                    key=key_server,
                                                    help="Desmarque para remover da atividade e retornar ao Expediente Administrativo."
                                                )
                                                if not server_checked:
                                                    remove_server_from_card(ds, act_idx, s)
                                                    st.rerun()
                                        else:
                                            st.write("👥 Servidores: (❌ desmarque para não incluir na 🖨️ impressão)")
                                            for s in atividade["servidores"]:
                                                key_server = f"checkbox_servidor_{ds}_{act_idx}_{s}"
                                                st.checkbox(
                                                    s,
                                                    value=True,
                                                    key=key_server,
                                                    help="Desmarque para não incluir este servidor na impressão."
                                                )

                                        st.write(f"**🚗 Veículo:** {atividade['veiculo']}")
                                        st.markdown("---")
                                else:
                                    st.write("📭 Nenhuma atividade para este dia.")

                        st.markdown('<hr class="full-width-hr">', unsafe_allow_html=True)

                        # ===================== IMPRESSÃO: Semana Atual =====================
                      # ===================== IMPRESSÃO: Semana Atual =====================
                        report_col1, report_col2, report_col3 = st.columns([1,2,1])
                        with report_col2:
                            st.write("#### 🖨️ Impressões")
                            st.markdown("""
                            <style>
                            button[data-testid="stButton"] {
                                width: 100% !important;
                                font-size: 1rem !important;
                                text-align: left !important;
                            }
                            </style>
                            """, unsafe_allow_html=True)

                            plantao = st.selectbox(
                                "Plantão para recebimento de vacinas e agrotóxicos",
                                options=st.session_state["servidores"],
                                key=f"plantao_{wid}"
                            )

                            colA, colB = st.columns([1,1])
                            with colA:
                                # Usa a função build_cards_list para filtrar somente itens marcados
                                cards_list = build_cards_list(week_dates)
                                pdf_bytes_programacao = generate_pdf_for_week(
                                    cards_list,
                                    labels[idx],
                                    st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada",
                                    st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada",
                                    plantao
                                )
                                st.download_button(
                                    label="📄 Imprimir Programação",
                                    data=pdf_bytes_programacao,
                                    file_name="programacao_semana.pdf",
                                    mime="application/pdf",
                                    key=f"download_prog_{wid}_{idx}_prog"
                                )
                            with colB:
                                # Usa a função build_atividades_por_servidor para filtrar atividades por servidor
                                atividades_por_servidor = build_atividades_por_servidor(week_dates)
                                pdf_bytes_relatorio = pdf_relatorio.generate_pdf_for_atividades(
                                    atividades_por_servidor,
                                    labels[idx],
                                    st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada",
                                    st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada"
                                )
                                st.download_button(
                                    label="📝 Imprimir relatório de atividades",
                                    data=pdf_bytes_relatorio,
                                    file_name="relatorio_semana.pdf",
                                    mime="application/pdf",
                                    key=f"download_relatorio_{wid}_{idx}_rel"
                                )
                        st.markdown("---")
                  
                # ===================== IMPRESSÕES - Todas as Semanas =====================
                st.subheader("🖨️ Impressões - Todas as Semanas")
                col_global1, col_global2 = st.columns(2)
                st.markdown("---")

                with col_global1:
                    if st.button("📄 Gerar Programação (Todas as Semanas)"):
                        cards_list_all = []
                        for w_index, w_id in enumerate(st.session_state["week_order"]):
                            week_dates_all = st.session_state["semanas"][w_id]
                            cards_list_all.append({
                                "Dia": f"--- {labels[w_index]} ---",
                                "Activities": []
                            })
                            filtered = build_cards_list(week_dates_all)
                            cards_list_all.extend(filtered)

                        all_weeks_label = "Programação de Todas as Semanas"
                        pdf_bytes_all_prog = generate_pdf_for_week(
                            cards_list_all,
                            all_weeks_label,
                            st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada",
                            st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada",
                            ""
                        )
                        st.download_button(
                            label="📥 Baixar Programação (Todas as Semanas)",
                            data=pdf_bytes_all_prog,
                            file_name="programacao_todas_semanas.pdf",
                            mime="application/pdf",
                            key="download_prog_all"
                        )

                with col_global2:
                    if st.button("📝 Gerar Relatório (Todas as Semanas)"):
                        atividades_por_servidor_all = {}
                        for w_index, w_id in enumerate(st.session_state["week_order"]):
                            week_dates_all = st.session_state["semanas"][w_id]
                            parcial = build_atividades_por_servidor(week_dates_all)
                            for servidor, lista_ativ in parcial.items():
                                if servidor not in atividades_por_servidor_all:
                                    atividades_por_servidor_all[servidor] = []
                                atividades_por_servidor_all[servidor].extend(lista_ativ)

                        all_weeks_label = "Relatório de Atividades (Todas as Semanas)"
                        pdf_bytes_all_rel = pdf_relatorio.generate_pdf_for_atividades(
                            atividades_por_servidor_all,
                            all_weeks_label,
                            st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada",
                            st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada"
                        )
                        st.download_button(
                            label="📥 Baixar Relatório (Todas as Semanas)",
                            data=pdf_bytes_all_rel,
                            file_name="relatorio_todas_semanas.pdf",
                            mime="application/pdf",
                            key="download_relatorio_all"
                        )

                       


    # ===== Início da aba 3: Plantão =====
    with tab3:
        # Variável global para nomes dos meses
        NOME_MESES = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }

        # st.title("💉 Plantão - Recebimento de Vacinas, Agrotóxicos e Produtos Biológicos")
        

        # --- Parte: Plantão (Servidores para Plantão) ---
        unidade_id = st.session_state.get("selected_unidade_id", None)
        if unidade_id:
            res = supabase.table("servidores").select("nome, telefone").eq("escritorio_id", unidade_id).execute()
            if res.data:
                st.session_state["plantao_itens"] = [(row["nome"], row["telefone"]) for row in res.data]
            else:
                st.session_state["plantao_itens"] = []
        else:
            st.session_state["plantao_itens"] = []

        if st.session_state["plantao_itens"]:
            # Extrai os nomes disponíveis para seleção
            nomes_disponiveis = [item[0] for item in st.session_state["plantao_itens"]]
            st.write("### 👥 Servidores para o Plantão")
            # Aqui o multiselect utiliza a chave "selected_plantao_names"
            selected = st.multiselect(
                "Selecione os servidores:",
                nomes_disponiveis,
                default=nomes_disponiveis,
                key="selected_plantao_names"
            )
        else:
            st.info("ℹ️ Nenhum 👥 servidor encontrado para o plantão.")
        # Usa a mesma chave para recuperar os nomes selecionados
        itens = st.session_state.get("plantao_itens", [])
        selected_names = st.session_state.get("selected_plantao_names", [])

        st.write("### 📊 Dados Carregados para o Plantão")
        with st.expander("Ver tabela selecionada"):
            col1, col2 = st.columns(2)
            col1.header("🧑 Nome")
            col2.header("📞 Telefone")
            for nome, telefone in itens:
                if nome in selected_names:
                    col1.write(nome)
                    col2.write(telefone)

        st.divider()

        # Seção de indisponibilidades
        with st.expander("Indisponibilidades", expanded=False):
            st.subheader("❌ Indisponibilidades")
            if selected_names:
                tabs_inner = st.tabs(selected_names)
                for i, tab in enumerate(tabs_inner):
                    with tab:
                        nome_tab = selected_names[i]
                        tel_tab = next((tel for nm, tel in itens if nm == nome_tab), "Sem Telefone")
                        st.write(f"**🧑Nome:** {nome_tab}")
                        st.write(f"**📞Telefone:** {tel_tab}")

                        # Inicializa a lista de períodos, se necessário
                        if nome_tab not in st.session_state["unavailable_periods"]:
                            st.session_state["unavailable_periods"][nome_tab] = []

                        st.subheader("➕❌ Adicionar Período de Indisponibilidade")
 
                        col_dt1, col_dt2 = st.columns(2)
                        with col_dt1:
                            inicio = st.date_input("Data de Início", key=f"inicio_{nome_tab}", value=date.today())
                        with col_dt2:
                            fim = st.date_input("Data de Fim", key=f"fim_{nome_tab}", value=date.today())

                        if st.button("Adicionar Período", key=f"btn_{nome_tab}"):
                            st.session_state["unavailable_periods"][nome_tab].append((inicio, fim))
                            st.success(f"Período adicionado para {nome_tab}.")

                        st.write("### 📋 Períodos de Indisponibilidade Registrados")

                        if st.session_state["unavailable_periods"][nome_tab]:
                            for idx, (start_dt, end_dt) in enumerate(st.session_state["unavailable_periods"][nome_tab]):
                                colA, colB, colC = st.columns([3, 3, 1])
                                colA.write(f"**Início:** {start_dt}")
                                colB.write(f"**Fim:** {end_dt}")
                                if colC.button("Remover", key=f"remover_{nome_tab}_{idx}"):
                                    st.session_state["unavailable_periods"][nome_tab].pop(idx)
                                    st.rerun()
                        else:
                            st.info("📭 Nenhum período cadastrado até o momento.")


        st.divider()
        st.subheader("🗓️ Gerar Escala de Plantão (Sábado a Sexta)")
        col_cronograma1, col_cronograma2 = st.columns(2)
        with col_cronograma1:
            data_cronograma_inicio = st.date_input("Data inicial do cronograma", value=date.today(), key="cronograma_inicio")
        with col_cronograma2:
            data_cronograma_fim = st.date_input("Data final do cronograma", value=date.today(), key="cronograma_fim")
        
        if st.button("⚙️ Gerar Escala"):

            if data_cronograma_inicio > data_cronograma_fim:
                st.error("A data inicial deve ser anterior ou igual à data final.")
            else:
                blocos = gerar_blocos_sabado_sexta(
                    data_cronograma_inicio,
                    data_cronograma_fim,
                    selected_names,
                    itens,
                    st.session_state["unavailable_periods"]
                )
                if not blocos:
                    st.warning("⚠️ Não foi possível gerar escala (todos indisponíveis ou sem intervalos).")
                else:
                    ano_escalado = data_cronograma_inicio.year
                    html_iframe = gerar_html_para_iframe(
                            blocos,
                            ano=ano_escalado,
                            NOME_MESES=NOME_MESES,
                            titulo_pagina="Relatório de Plantão"
                        )

                    components.html(html_iframe, height=600, scrolling=True)

if __name__ == "__main__":
    main_app()
