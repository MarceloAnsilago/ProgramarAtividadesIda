import streamlit as st
from datetime import date, timedelta
from io import BytesIO
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
import pdf_relatorio
from pdf_utils import generate_pdf_for_week
import streamlit.components.v1 as components
import pandas as pd
# ------------------------------------------------------------------------------
# Configuração inicial e título
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Programação de Atividades IDARON", 
    page_icon="🗓️",  # Pode ser um emoji ou caminho para uma imagem
    layout="wide"
)
st.title("Progamação de Atividades IDARON")

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
if "all_servidores" not in st.session_state:
    st.session_state["all_servidores"] = []
if "all_atividades" not in st.session_state:
    st.session_state["all_atividades"] = []
if "all_veiculos" not in st.session_state:
    st.session_state["all_veiculos"] = []
if "all_ul_sups" not in st.session_state:
    st.session_state["all_ul_sups"] = []

if "servidores" not in st.session_state:
    st.session_state["servidores"] = []
if "atividades" not in st.session_state:
    st.session_state["atividades"] = []
if "veiculos" not in st.session_state:
    st.session_state["veiculos"] = []
if "ul_sups" not in st.session_state:
    st.session_state["ul_sups"] = []

if "semanas" not in st.session_state:
    st.session_state["semanas"] = {}  # chave: "YYYY-WW" -> lista de datas
if "week_order" not in st.session_state:
    st.session_state["week_order"] = []  # ordem de criação das semanas
if "atividades_dia" not in st.session_state:
    st.session_state["atividades_dia"] = {}  # chave: "dd/mm/yyyy" -> lista de atividades

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
# Função para ler arquivos TXT com fallback
# ------------------------------------------------------------------------------
def read_text_file(uploaded_file):
    content = uploaded_file.getvalue()
    try:
        return content.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return content.decode("latin-1").splitlines()

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
        for day_date in st.session_state["semanas"][wid]:
            add_activity_to_date(
                day_date,
                atividade="Expediente Administrativo",
                servidores=[s for s in st.session_state["servidores"]],
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

def get_available_servers(day_date):
    date_str = day_date.strftime("%d/%m/%Y")
    if date_str in st.session_state["atividades_dia"]:
        for act in st.session_state["atividades_dia"][date_str]:
            if act["atividade"] == "Expediente Administrativo":
                return act["servidores"]
    return []

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

# ------------------------------------------------------------------------------
# Layout com Abas
# ------------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["Dados", "Programação", "Programação para recebimento"])

# ------------------------------------------------------------------------------
# Aba 1: Dados
# ------------------------------------------------------------------------------
with tab1:
    st.header("Gerenciar Dados")
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        # Upload de servidores
        up_serv = st.file_uploader("Arquivo de Servidores (txt)", type="txt", key="upload_servidores")
        if up_serv is not None:
            lines = read_text_file(up_serv)
            st.session_state["all_servidores"] = [l.strip() for l in lines if l.strip()]
        st.write("### Buscar txt Servidores")
        sel_serv = st.multiselect("Selecione os Servidores", st.session_state["all_servidores"],
                                  default=st.session_state["all_servidores"])
        st.session_state["servidores"] = sel_serv

        st.divider()

        # Upload de atividades
        up_ativ = st.file_uploader("Arquivo de Atividades (txt)", type="txt", key="upload_atividades")
        if up_ativ is not None:
            lines = read_text_file(up_ativ)
            st.session_state["all_atividades"] = [l.strip() for l in lines if l.strip()]
        st.write("### Buscar txt Atividades")
        sel_ativ = st.multiselect("Selecione as Atividades", st.session_state["all_atividades"],
                                  default=st.session_state["all_atividades"])
        st.session_state["atividades"] = sel_ativ

        st.divider()

        # Upload de veículos
        up_veic = st.file_uploader("Arquivo de Veículos (txt)", type="txt", key="upload_veiculos")
        if up_veic is not None:
            lines = read_text_file(up_veic)
            st.session_state["all_veiculos"] = [l.strip() for l in lines if l.strip()]
        st.write("### Buscar txt Veículos")
        sel_veic = st.multiselect("Selecione os Veículos", st.session_state["all_veiculos"],
                                  default=st.session_state["all_veiculos"])
        st.session_state["veiculos"] = sel_veic

        st.divider()

        # Upload de ULSAV e Supervisão
        up_ul_sups = st.file_uploader("Arquivo de ULSAV e Supervisão (txt)", type="txt", key="upload_ul_sups")
        if up_ul_sups is not None:
            lines = read_text_file(up_ul_sups)
            st.session_state["all_ul_sups"] = [l.strip() for l in lines if l.strip()]
        st.write("### Buscar txt ULSAV e Supervisão")
        sel_ul_sups = st.multiselect("Selecione ULSAV/ Supervisão", st.session_state["all_ul_sups"],
                                     default=st.session_state["all_ul_sups"])
        st.session_state["ul_sups"] = sel_ul_sups

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
    st.header("Programação de Atividades")
    if (not st.session_state["servidores"]) or (not st.session_state["atividades"]) or (not st.session_state["veiculos"]):
        st.warning("Carregue e selecione Servidores, Atividades e Veículos na aba 'Dados'.")
    else:
        # Atualiza os cartões de "Expediente Administrativo" (mantém apenas os servidores ativos)
        for ds, atividades in st.session_state.get("atividades_dia", {}).items():
            for atividade in atividades:
                if atividade["atividade"] == "Expediente Administrativo":
                    atividade["servidores"] = [s for s in atividade["servidores"] if s in st.session_state["servidores"]]

        st.write("Selecione uma data para criar (ou visualizar) a semana correspondente:")
        selected_date = st.date_input("Data para a semana:", value=date.today())

        colA, colB = st.columns(2)
        with colA:
            include_saturday = st.checkbox("Incluir Sábado", value=False)
        with colB:
            include_sunday = st.checkbox("Incluir Domingo", value=False)

        if st.button("🗓️Adicionar Semana"):
            add_week_if_not_exists(selected_date, include_saturday, include_sunday)
            st.success("Semana adicionada!")
            st.rerun()

        st.markdown("---")

        if st.session_state["week_order"]:
            # Gera os rótulos das semanas
            labels = []
            for wid in st.session_state["week_order"]:
                week_dates = st.session_state["semanas"][wid]
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
                        st.write(f"#### Adicionar Nova Atividade ({chosen_day})")

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

                        summary_html = f"""
                        <div class="summary-card">
                          <strong>Resumo da Semana</strong>
                          <div class="summary-flex">
                            <div class="summary-column">
                              <u>Dia:</u><br>{dias_label}
                            </div>
                            <div class="summary-column">
                              <u>Atividades:</u><br>"""
                        if activities_summary:
                            for act, count in activities_summary.items():
                                summary_html += f"{act}: {count}<br>"
                        else:
                            summary_html += "Nenhuma<br>"
                        summary_html += """</div>
                            <div class="summary-column">
                              <u>Servidores:</u><br>"""
                        if servers_summary:
                            for serv, count in servers_summary.items():
                                summary_html += f"{serv}: {count}<br>"
                        else:
                            summary_html += "Nenhum<br>"
                        summary_html += """</div>
                            <div class="summary-column">
                              <u>Veículos:</u><br>"""
                        if vehicles_summary:
                            for veic, count in vehicles_summary.items():
                                summary_html += f"{veic}: {count}<br>"
                        else:
                            summary_html += "Nenhum<br>"
                        summary_html += """</div>
                          </div>
                        </div>"""
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

                                        st.write("Servidores: (desmarque para remover da atividade e voltar para Expediente Administrativo)")
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
                                        st.write("Servidores: (desmarque para não incluir na impressão)")
                                        for s in atividade["servidores"]:
                                            key_server = f"checkbox_servidor_{ds}_{act_idx}_{s}"
                                            st.checkbox(
                                                s,
                                                value=True,
                                                key=key_server,
                                                help="Desmarque para não incluir este servidor na impressão."
                                            )

                                    st.write(f"**Veículo:** {atividade['veiculo']}")
                                    st.markdown("---")
                            else:
                                st.write("Nenhuma atividade para este dia.")

                    st.markdown('<hr class="full-width-hr">', unsafe_allow_html=True)

                    # ===================== IMPRESSÃO: Semana Atual =====================
                    report_col1, report_col2, report_col3 = st.columns([1,2,1])
                    with report_col2:
                        st.write("#### Impressões")
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
        else:
            st.info("Programação não cadastrada ainda. Selecione uma data e clique em 'Adicionar Semana'.")

    # ===================== IMPRESSÕES - Todas as Semanas =====================
    st.subheader("Impressões - Todas as Semanas")
    col_global1, col_global2 = st.columns(2)

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
                label="Baixar Programação (Todas as Semanas)",
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
                label="Baixar Relatório (Todas as Semanas)",
                data=pdf_bytes_all_rel,
                file_name="relatorio_todas_semanas.pdf",
                mime="application/pdf",
                key="download_relatorio_all"
            )


with tab3:
    # Variável global para nomes dos meses (pode ser definida fora, se preferir)
    NOME_MESES = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    
    def main_tab3():
        st.title("Plantão - Recebimento de Vacinas, agrotóxicos e produtos biológicos")
    
        if "unavailable_periods" not in st.session_state:
            st.session_state["unavailable_periods"] = {}
    
        # Upload do TXT (nome;telefone)
        uploaded_file = st.file_uploader("Carregue seu arquivo TXT (nome;telefone)", type=["txt"])
        itens = []
        if uploaded_file is not None:
            content_bytes = uploaded_file.read()
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = content_bytes.decode("latin-1")
    
            lines = content.strip().split("\n")
            for line in lines:
                parts = line.split(";")
                if len(parts) == 2:
                    nome, telefone = parts
                    itens.append((nome.strip(), telefone.strip()))
    
        # Se temos itens, exibir multiselect
        if itens:
            nomes = [item[0] for item in itens]
            selected_names = st.multiselect("Selecione os nomes:", nomes, default=nomes)
        else:
            selected_names = []
    
        # Expander com a lista geral (opcional)
        if itens and selected_names:
            with st.expander("Ver tabela selecionada"):
                st.write("Nomes e Telefones selecionados:")
                col1, col2 = st.columns(2)
                col1.header("Nome")
                col2.header("Telefone")
                for nome, telefone in itens:
                    if nome in selected_names:
                        col1.write(nome)
                        col2.write(telefone)
    
        # Tabs para indisponibilidades
        if selected_names:
            tabs_inner = st.tabs(selected_names)
            for i, tab in enumerate(tabs_inner):
                with tab:
                    nome_tab = selected_names[i]
                    tel_tab = next((tel for nm, tel in itens if nm == nome_tab), "")
    
                    st.write(f"**Nome:** {nome_tab}")
                    st.write(f"**Telefone:** {tel_tab}")
    
                    if nome_tab not in st.session_state["unavailable_periods"]:
                        st.session_state["unavailable_periods"][nome_tab] = []
    
                    st.subheader("Adicionar Período de Indisponibilidade")
                    col_dt1, col_dt2 = st.columns(2)
                    with col_dt1:
                        inicio = st.date_input("Data de Início", key=f"inicio_{nome_tab}", value=date.today())
                    with col_dt2:
                        fim = st.date_input("Data de Fim", key=f"fim_{nome_tab}", value=date.today())
    
                    if st.button("Adicionar Período", key=f"btn_{nome_tab}"):
                        st.session_state["unavailable_periods"][nome_tab].append((inicio, fim))
                        st.success(f"Período adicionado para {nome_tab}.")
    
                    st.write("### Períodos de Indisponibilidade Registrados")
                    if st.session_state["unavailable_periods"][nome_tab]:
                        for idx, (start_dt, end_dt) in enumerate(st.session_state["unavailable_periods"][nome_tab]):
                            colA, colB, colC = st.columns([3, 3, 1])
                            colA.write(f"**Início:** {start_dt}")
                            colB.write(f"**Fim:** {end_dt}")
                            if colC.button("Remover", key=f"remover_{nome_tab}_{idx}"):
                                st.session_state["unavailable_periods"][nome_tab].pop(idx)
                                st.rerun()
                    else:
                        st.info("Nenhum período cadastrado até o momento.")
    
        st.divider()
        st.subheader("Gerar Escala de Plantão (Sábado a Sexta)")
    
        col_cronograma1, col_cronograma2 = st.columns(2)
        with col_cronograma1:
            data_cronograma_inicio = st.date_input("Data inicial do cronograma", value=date.today())
        with col_cronograma2:
            data_cronograma_fim = st.date_input("Data final do cronograma", value=date.today())
    
        if st.button("Gerar Escala"):
            if not selected_names:
                st.error("Nenhum nome foi selecionado para a escala.")
                return
            if data_cronograma_inicio > data_cronograma_fim:
                st.error("A data inicial deve ser anterior ou igual à data final.")
                return
    
            blocos = gerar_blocos_sabado_sexta(
                data_cronograma_inicio,
                data_cronograma_fim,
                selected_names,
                itens,
                st.session_state["unavailable_periods"]
            )
    
            if not blocos:
                st.warning("Não foi possível gerar escala (todos indisponíveis ou sem intervalos).")
                return
    
            # Captura o ano da data inicial para usar no título
            ano_escalado = data_cronograma_inicio.year
    
            # Gera HTML para imprimir só no iframe
            html_iframe = gerar_html_para_iframe(blocos, ano=ano_escalado)
    
            components.html(
                html_iframe,
                height=600,
                scrolling=True
            )
    
    # Funções definidas para uso em main_tab3()
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
            if not (fim_bloco < ini_indisp or ini_bloco > fim_indisp):
                return True
        return False
    
    def gerar_html_para_iframe(blocos, ano):
        grupos = agrupar_blocos_mensalmente(blocos)
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
        <h3>Escala de Plantão ({ano})</h3>
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
    
    def agrupar_blocos_mensalmente(blocos):
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
    
    # Chama a função principal para Tab3
    main_tab3()


    