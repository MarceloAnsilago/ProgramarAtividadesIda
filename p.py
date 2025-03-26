import streamlit as st
from datetime import date, timedelta
from io import BytesIO
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

import pdf_relatorio
from pdf_utils import generate_pdf_for_week

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
                servidores=st.session_state["servidores"],
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
        for act in day_acts:
            if act["atividade"] != "Expediente Administrativo":
                activities[act["atividade"]] = activities.get(act["atividade"], 0) + 1
                for s in act["servidores"]:
                    servers[s] = servers.get(s, 0) + 1
                if act["veiculo"] and act["veiculo"] != "Nenhum":
                    vehicles[act["veiculo"]] = vehicles.get(act["veiculo"], 0) + 1
    return activities, servers, vehicles


# ------------------------------------------------------------------------------
# Layout com Abas
# ------------------------------------------------------------------------------
tab1, tab2 = st.tabs(["Dados", "Programação"])

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
with tab2:
    st.header("Programação de Atividades")
    if (not st.session_state["servidores"]) or (not st.session_state["atividades"]) or (not st.session_state["veiculos"]):
        st.warning("Carregue e selecione Servidores, Atividades e Veículos na aba 'Dados'.")
    else:
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
            # Gera rótulos no formato "Primeira semana do mês de março" etc.
            month_weeks_count = {}
            labels = []
            for wid in st.session_state["week_order"]:
                week_dates = st.session_state["semanas"][wid]
                if not week_dates:
                    labels.append("Semana vazia")
                    continue
                first_date = week_dates[0]
                year_str = first_date.strftime("%Y")
                month_num = int(first_date.strftime("%m"))
                key_mes = (year_str, month_num)
                month_weeks_count[key_mes] = month_weeks_count.get(key_mes, 0) + 1
                ordinal_name = get_ordinal_week_in_month(month_weeks_count[key_mes])
                month_name_pt = month_map_pt[month_num]
                label = f"{ordinal_name} semana do mês de {month_name_pt}"
                labels.append(label)

            weeks_tabs = st.tabs(labels)

            for idx, wid in enumerate(st.session_state["week_order"]):
                with weeks_tabs[idx]:
                    st.markdown(f"## {labels[idx]}")

                    # Linha superior: 3 colunas -> Excluir Semana | Formulário | Resumo
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
                        st.write(f"### Adicionar Nova Atividade ({chosen_day})")

                        # Servidores já alocados no dia (exceto Expediente)
                        def get_alocados_no_dia(chosen_date):
                            date_str = chosen_date.strftime("%d/%m/%Y")
                            alocados = set()
                            if date_str in st.session_state["atividades_dia"]:
                                for act in st.session_state["atividades_dia"][date_str]:
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
                                date_str = chosen_date.strftime("%d/%m/%Y")
                                if date_str in st.session_state["atividades_dia"]:
                                    for a_idx, act in enumerate(st.session_state["atividades_dia"][date_str]):
                                        if act["atividade"] == "Expediente Administrativo":
                                            # Remove esses servidores do Expediente
                                            act["servidores"] = [s for s in act["servidores"] if s not in servidores_escolhidos]
                                            break
                                add_activity_to_date(chosen_date, atividade_escolhida, servidores_escolhidos, veiculo_escolhido)
                                st.rerun()

                    with top_col3:
                        # Resumo da semana
                        dias_com_atividades = []
                        for d in week_dates:
                            date_str = d.strftime("%d/%m/%Y")
                            day_name_pt = dias_semana.get(d.strftime("%A"), d.strftime("%A"))
                            acts = st.session_state["atividades_dia"].get(date_str, [])
                            if any(act["atividade"] != "Expediente Administrativo" for act in acts):
                                dias_com_atividades.append(day_name_pt)
                        dias_label = "<br>".join(dias_com_atividades) if dias_com_atividades else "Nenhum"

                        activities_summary, servers_summary, vehicles_summary = get_summary_details_for_week(wid)
                        summary_html = f"""
                        <div class="summary-card">
                          <strong>Resumo da Semana</strong>
                          <div class="summary-flex">
                            <div class="summary-column">
                              <u>Dia:</u><br>
                              {dias_label}
                            </div>
                            <div class="summary-column">
                              <u>Atividades:</u><br>
                        """
                        if activities_summary:
                            for act, count in activities_summary.items():
                                summary_html += f"{act}: {count}<br>"
                        else:
                            summary_html += "Nenhuma<br>"
                        summary_html += """
                            </div>
                            <div class="summary-column">
                              <u>Servidores:</u><br>
                        """
                        if servers_summary:
                            for serv, count in servers_summary.items():
                                summary_html += f"{serv}: {count}<br>"
                        else:
                            summary_html += "Nenhum<br>"
                        summary_html += """
                            </div>
                            <div class="summary-column">
                              <u>Veículos:</u><br>
                        """
                        if vehicles_summary:
                            for veic, count in vehicles_summary.items():
                                summary_html += f"{veic}: {count}<br>"
                        else:
                            summary_html += "Nenhum<br>"
                        summary_html += """
                            </div>
                          </div>
                        </div>
                        """
                        st.markdown(summary_html, unsafe_allow_html=True)

                    st.markdown("---")

                    # Listagem das atividades de cada dia
                    cols = st.columns(len(week_dates))
                    for j, current_date in enumerate(week_dates):
                        with cols[j]:
                            day_name_en = current_date.strftime("%A")
                            day_name_pt = dias_semana.get(day_name_en, day_name_en)
                            date_str = current_date.strftime("%d/%m/%Y")

                            st.markdown(f"<div class='day-title'>{day_name_pt} - {date_str}</div>", unsafe_allow_html=True)

                            day_acts = st.session_state["atividades_dia"].get(date_str, [])
                            if day_acts:
                                for act_idx, atividade in enumerate(day_acts):
                                    form_key = f"form_{date_str}_{act_idx}"
                                    with st.form(key=form_key):
                                        if atividade["atividade"] == "Expediente Administrativo":
                                            st.write("**Atividade: Expediente Administrativo**")
                                            activity_checked = True
                                        else:
                                            activity_checked = st.checkbox(
                                                f"Atividade: {atividade['atividade']}",
                                                value=True,
                                                key=f"checkbox_{date_str}_{act_idx}"
                                            )

                                        st.write("Servidores: (desmarque para remover)")
                                        server_states = {}
                                        for s in atividade["servidores"]:
                                            server_states[s] = st.checkbox(
                                                s, value=True, key=f"{date_str}_{act_idx}_{s}"
                                            )

                                        st.write(f"**Veículo:** {atividade['veiculo']}")

                                        if st.form_submit_button("🔄Atualizar"):
                                            if atividade["atividade"] != "Expediente Administrativo":
                                                if not activity_checked:
                                                    remove_activity_card(date_str, act_idx)
                                                    st.rerun()

                                            for s_name, checked in server_states.items():
                                                if not checked:
                                                    remove_server_from_card(date_str, act_idx, s_name)
                                            st.rerun()

                    st.markdown('<hr class="full-width-hr">', unsafe_allow_html=True)

                    # Impressões individuais (semana)
                    report_col1, report_col2, report_col3 = st.columns([1,2,1])
                    with report_col2:
                        st.write("### Impressões")
                        st.markdown("""
                        <style>
                        button[data-testid="stButton"] {
                            width: 100% !important;
                            font-size: 1rem !important;
                            text-align: left !important;
                        }
                        </style>
                        """, unsafe_allow_html=True)

                        # Campo de plantão
                        plantao = st.selectbox(
                            "Plantão para recebimento de vacinas e agrotóxicos",
                            options=st.session_state["servidores"],
                            key=f"plantao_{wid}"
                        )

                        colA, colB = st.columns([1,1])

                        with colA:
                            # Gera E BAIXA o PDF no mesmo clique (Programação)
                            cards_list = []
                            for day_date in week_dates:
                                date_str = day_date.strftime("%d/%m/%Y")
                                day_name_en = day_date.strftime("%A")
                                day_label = f"{dias_semana.get(day_name_en, day_name_en)} ({date_str})"
                                day_acts = st.session_state["atividades_dia"].get(date_str, [])
                                cards_list.append({
                                    "Dia": day_label,
                                    "Activities": day_acts
                                })

                            label_da_semana = labels[idx]
                            ulsav_name = st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada"
                            supervisao_name = st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada"
                            pdf_bytes_programacao = generate_pdf_for_week(
                                cards_list,
                                label_da_semana,
                                ulsav_name,
                                supervisao_name,
                                plantao
                            )

                            st.download_button(
                                label="📄 Imprimir Programação",
                                data=pdf_bytes_programacao,
                                file_name="programacao_semana.pdf",
                                mime="application/pdf",
                                key=f"download_prog_{wid}_{idx}_prog"  # chave única
                            )

                        with colB:
                            # Gera E BAIXA o PDF de relatório no mesmo clique
                            atividades_por_servidor = {}
                            for date_str, acts in st.session_state["atividades_dia"].items():
                                for act in acts:
                                    if act["atividade"] != "Expediente Administrativo":
                                        for servidor in act["servidores"]:
                                            if servidor not in atividades_por_servidor:
                                                atividades_por_servidor[servidor] = []
                                            atividades_por_servidor[servidor].append({
                                                "Data": date_str,
                                                "Atividade": act["atividade"]
                                            })

                            label_da_semana = labels[idx]
                            ulsav_name = st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada"
                            supervisao_name = st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada"
                            pdf_bytes_relatorio = pdf_relatorio.generate_pdf_for_atividades(
                                atividades_por_servidor,
                                label_da_semana,
                                ulsav_name,
                                supervisao_name
                            )

                            st.download_button(
                                label="📝 Imprimir relatório de atividades",
                                data=pdf_bytes_relatorio,
                                file_name="relatorio_semana.pdf",
                                mime="application/pdf",
                                key=f"download_relatorio_{wid}_{idx}_rel"  # chave única
                            )

                    st.markdown("---")
        else:
            st.info("Programação não cadastrada ainda. Selecione uma data e clique em 'Adicionar Semana'.")

        # ----------------------------------------------------------------------
        # Impressões Globais - Fora do loop
        # ----------------------------------------------------------------------
        st.subheader("Impressões - Todas as Semanas")
        col_global1, col_global2 = st.columns(2)

        with col_global1:
            # Gera e Baixa PDF Programação (Todas as Semanas)
            if st.button("📄 Gerar Programação (Todas as Semanas)"):
                cards_list_all = []
                for w_index, w_id in enumerate(st.session_state["week_order"]):
                    week_dates = st.session_state["semanas"][w_id]
                    cards_list_all.append({
                        "Dia": f"--- {labels[w_index]} ---",
                        "Activities": []
                    })
                    for day_date in week_dates:
                        date_str = day_date.strftime("%d/%m/%Y")
                        day_name_en = day_date.strftime("%A")
                        day_label = f"{dias_semana.get(day_name_en, day_name_en)} ({date_str})"
                        day_acts = st.session_state["atividades_dia"].get(date_str, [])
                        cards_list_all.append({
                            "Dia": day_label,
                            "Activities": day_acts
                        })

                all_weeks_label = "Programação de Todas as Semanas"
                ulsav_name = st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada"
                supervisao_name = st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada"

                pdf_bytes_all_prog = generate_pdf_for_week(
                    cards_list_all,
                    all_weeks_label,
                    ulsav_name,
                    supervisao_name,
                    ""
                )

                st.download_button(
                    label="Baixar Programação (Todas as Semanas)",
                    data=pdf_bytes_all_prog,
                    file_name="programacao_todas_semanas.pdf",
                    mime="application/pdf",
                    key="download_prog_all"  # Chave única para global
                )

        with col_global2:
            # Gera e Baixa PDF Relatório (Todas as Semanas)
            if st.button("📝 Gerar Relatório (Todas as Semanas)"):
                atividades_por_servidor_all = {}
                for w_index, w_id in enumerate(st.session_state["week_order"]):
                    week_dates = st.session_state["semanas"][w_id]
                    for day_date in week_dates:
                        date_str = day_date.strftime("%d/%m/%Y")
                        day_acts = st.session_state["atividades_dia"].get(date_str, [])
                        for act in day_acts:
                            if act["atividade"] != "Expediente Administrativo":
                                for servidor in act["servidores"]:
                                    if servidor not in atividades_por_servidor_all:
                                        atividades_por_servidor_all[servidor] = []
                                    atividades_por_servidor_all[servidor].append({
                                        "Data": date_str,
                                        "Atividade": act["atividade"]
                                    })

                all_weeks_label = "Relatório de Atividades (Todas as Semanas)"
                ulsav_name = st.session_state["ul_sups"][0] if st.session_state["ul_sups"] else "ULSAV não informada"
                supervisao_name = st.session_state["ul_sups"][1] if len(st.session_state["ul_sups"]) > 1 else "Supervisão não informada"

                pdf_bytes_all_rel = pdf_relatorio.generate_pdf_for_atividades(
                    atividades_por_servidor_all,
                    all_weeks_label,
                    ulsav_name,
                    supervisao_name
                )

                st.download_button(
                    label="Baixar Relatório (Todas as Semanas)",
                    data=pdf_bytes_all_rel,
                    file_name="relatorio_todas_semanas.pdf",
                    mime="application/pdf",
                    key="download_relatorio_all"  # Chave única para global
                )
