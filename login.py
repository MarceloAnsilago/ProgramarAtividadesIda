import streamlit as st
from supabase import create_client, Client
import streamlit_authenticator as stauth
import os
import bcrypt
import p


st.set_page_config(layout="wide")


# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wlbvahpkcaksqkzdhnbv.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndsYnZhaHBrY2Frc3FremRobmJ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDMyODMxMTUsImV4cCI6MjA1ODg1OTExNX0.Cph86UhT8Q67-1x2oVfTFyELgQqWRgJ3yump1JpHSc8")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --- Estado da Sessão ---
def init_session_state():
    st.session_state.setdefault("logged_in", False)
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("view", "dashboard")
    st.session_state.setdefault("selected_unidade", None)
    st.session_state.setdefault("selected_unidade_id", None)
    
    # Novas chaves usadas em p.main_app()
    st.session_state.setdefault("week_order", [])
    st.session_state.setdefault("atividades_dia", {})
    st.session_state.setdefault("checklist", {})
    st.session_state.setdefault("all_servidores", [])
    st.session_state.setdefault("all_atividades", [])
    st.session_state.setdefault("all_veiculos", [])
    st.session_state.setdefault("all_ul_sups", [])
    st.session_state.setdefault("unavailable_periods", {})

init_session_state()
def login_form():
    st.title("🔐 Login - Usuário e Unidade")
    login = st.text_input("👤 Login")
    senha = st.text_input("🔒 Senha", type="password")

    unidades = supabase.table("unidades").select("nome").execute().data or []
    nomes_unidades = [u["nome"] for u in unidades]
    unidade = st.selectbox("🏢 Unidade", nomes_unidades)

    if st.button("🔐 Login", key="btn_login"):
        # Busca o usuário
        resposta = supabase.table("usuarios").select("*")\
            .eq("login", login)\
            .eq("unidade", unidade)\
            .execute()

        if not resposta.data:
            st.error("❌ Usuário não encontrado.")
            return

        user = resposta.data[0]

        if user["status"] != "Ativo":
            st.warning("⚠️ Usuário inativo. Contate o administrador.")
            return

        if not bcrypt.checkpw(senha.encode(), user["hashed_password"].encode()):
            st.error("❌ Senha incorreta.")
            return

        # Login válido
        st.success("✅ Login realizado com sucesso!")
        st.session_state.logged_in = True
        st.session_state.user = user
        st.session_state.view = "dashboard" if user.get("role") == "admin" else "app"
        st.session_state["is_admin"] = user.get("role") == "admin"

        # Resolve ID da unidade
        res_unidade = supabase.table("unidades").select("id").eq("nome", unidade).execute()
        if res_unidade.data:
            unidade_id = res_unidade.data[0]["id"]
            st.session_state["selected_unidade"] = unidade
            st.session_state["selected_unidade_id"] = unidade_id

            # Para usuários comuns, tentar buscar o servidor correspondente
            if user.get("role") != "admin":
                res_serv = supabase.table("servidores").select("*")\
                    .eq("nome", login).eq("escritorio_id", unidade_id).execute()

                if res_serv.data:
                    servidor = res_serv.data[0]
                    st.session_state["usuario_logado"] = servidor["nome"]
                    st.session_state["servidor_matricula"] = servidor["matricula"]
                    st.session_state["servidor_id"] = servidor["id"]
                else:
                    st.warning("⚠️ Nenhum servidor correspondente encontrado na unidade.")
        else:
            st.warning("⚠️ Unidade não encontrada.")

        st.rerun()


# --- Admin: Gerenciamento de Unidades ---
def gerenciar_unidades():
    st.header("🏢 Unidades Cadastradas")
    res = supabase.table("unidades").select("*").execute()
    unidades = res.data or []
    if unidades:
        st.dataframe(unidades)
    else:
        st.info("ℹ️ Nenhuma unidade cadastrada.")

    st.subheader("➕ Cadastrar Nova Unidade")
    with st.form("form_nova_unidade"):
        nome = st.text_input("📍 Nome da Unidade")
        supervisao = st.text_input("🧑‍💼 Supervisão")
        status = st.checkbox("✅ Ativo?", value=True, key="status_nova_unidade")
        if st.form_submit_button("➕ Cadastrar"):
            if nome:
                supabase.table("unidades").insert({
                    "nome": nome,
                    "supervisao": supervisao,
                    "status": "Ativo" if status else "Inativo"
                }).execute()
                st.success("✅ Unidade cadastrada com sucesso.")
                st.rerun()
            else:
                st.error("❌ Nome obrigatório.")

    st.subheader("✏️ Editar Unidade")
    if unidades:
        unidade = st.selectbox("Selecione a unidade", unidades, format_func=lambda x: x["nome"], key="selectbox_editar_unidade")
        uid = unidade["id"]
        novo_nome = st.text_input("📍 Novo nome", value=unidade["nome"], key=f"novo_nome_{uid}")
        nova_supervisao = st.text_input("🧑‍💼 Nova supervisão", value=unidade.get("supervisao", ""), key=f"nova_supervisao_{uid}")
        status_edit = st.checkbox("✅ Ativo?", value=unidade["status"] == "Ativo", key=f"status_edit_{uid}")
        if st.button("🔄 Atualizar Unidade", key=f"btn_update_unidade_{uid}"):
            supabase.table("unidades").update({
                "nome": novo_nome,
                "supervisao": nova_supervisao,
                "status": "Ativo" if status_edit else "Inativo"
            }).eq("id", unidade["id"]).execute()
            st.success("✅ Unidade atualizada.")
            st.rerun()

# --- Admin: Gerenciamento de Usuários ---
def gerenciar_usuarios():
    st.header("👥 Usuários Cadastrados")
    res = supabase.table("usuarios").select("*").execute()
    usuarios = res.data or []
    if usuarios:
        st.dataframe(usuarios)
    else:
        st.info("ℹ️ Nenhum usuário encontrado.")

    st.subheader("➕ Cadastrar Novo Usuário")
    unidades = [u["nome"] for u in supabase.table("unidades").select("nome").execute().data]

    with st.form("form_novo_usuario"):
        login = st.text_input("👤 Login")
        senha = st.text_input("🔒 Senha", type="password")
        unidade = st.selectbox("🏢 Unidade", unidades, key="unidade_cadastro_usuario")
        status = st.checkbox("✅ Ativo?", value=True, key="checkbox_novo_user")
        if st.form_submit_button("➕ Cadastrar Usuário"):
            if login and senha:
                hash_senha = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
                supabase.table("usuarios").insert({
                    "login": login,
                    "hashed_password": hash_senha,
                    "unidade": unidade,
                    "status": "Ativo" if status else "Inativo",
                    "role": "user"
                }).execute()
                st.success("✅ Usuário cadastrado.")
                st.rerun()
            else:
                st.error("❌ Preencha todos os campos.")

    st.subheader("✏️ Editar Usuário")
    if usuarios:
        usuario = st.selectbox("Usuário para editar", usuarios, format_func=lambda x: x["login"], key="select_usuario_edicao")
        uid = usuario["id"]
        prefix = f"user_edit_{uid}"

        novo_login = st.text_input("👤 Novo login", value=usuario["login"], key=f"{prefix}_login")
        status_user = st.checkbox("✅ Ativo?", value=usuario["status"] == "Ativo", key=f"{prefix}_checkbox")

        if st.button("🔄 Atualizar Usuário", key=f"{prefix}_btn"):
            supabase.table("usuarios").update({
                "login": novo_login,
                "status": "Ativo" if status_user else "Inativo"
            }).eq("id", uid).execute()
            st.success("✅ Usuário atualizado.")
            st.rerun()

# --- Admin: Seleção de Unidade e Navegação para Aplicação ---
def seletor_unidade_aplicacao():
    st.divider()
    st.subheader("🚀 Unidade para Aplicação")

    unidades = supabase.table("unidades").select("*").execute().data or []
    nomes = [u["nome"] for u in unidades]
    dict_ids = {u["nome"]: u["id"] for u in unidades}

    if nomes:
        selecionada = st.selectbox("📍 Selecione a Unidade", nomes, key="selectbox_unidade_app")
        st.session_state["selected_unidade"] = selecionada
        st.session_state["selected_unidade_id"] = dict_ids[selecionada]

        if st.button("🚀 Ir para Aplicação", key="btn_entrar_app"):
            st.session_state["view"] = "app"
            st.rerun()
    else:
        st.info("ℹ️ Nenhuma unidade cadastrada.")

# --- View Admin Completa ---
def dashboard_admin():
    tabs = st.tabs(["🏢 Gerenciar Unidades", "👥 Gerenciar Usuários"])
    with tabs[0]:
        gerenciar_unidades()
    with tabs[1]:
        gerenciar_usuarios()
    seletor_unidade_aplicacao()


# --- View Principal ---
def main_view():
    if not st.session_state["logged_in"]:
        login_form()
        return

    usuario = st.session_state["user"]
    role = usuario.get("role", "user")
    view = st.session_state["view"]

    if view == "dashboard" and role == "admin":
        dashboard_admin()
    elif view == "app":
        p.init_plantao_session_state()  # <- ESSA LINHA ADICIONADA
        p.main_app()
        if role == "admin" and st.button("🔙 Voltar ao Dashboard", key="btn_voltar_dash"):
            st.session_state["view"] = "dashboard"
            st.rerun()

    if st.button("🚪 Logout", key="btn_logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()




# --- Execução Principal ---
main_view()
