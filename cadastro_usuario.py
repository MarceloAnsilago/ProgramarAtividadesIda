import streamlit as st
from supabase import create_client, Client
import streamlit_authenticator as stauth
import os
import bcrypt

# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://wlbvahpkcaksqkzdhnbv.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndsYnZhaHBrY2Frc3FremRobmJ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDMyODMxMTUsImV4cCI6MjA1ODg1OTExNX0.Cph86UhT8Q67-1x2oVfTFyELgQqWRgJ3yump1JpHSc8")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("Cadastro de Usuário")

with st.form("cadastro_form"):
    email = st.text_input("Email")
    password = st.text_input("Senha", type="password")
    confirm_password = st.text_input("Confirme a Senha", type="password")
    # Caso deseje enviar metadados, como o escritório, defina aqui:
    escritorio_id = st.number_input("ID do Escritório", min_value=1, step=1, value=3)
    submit = st.form_submit_button("Cadastrar")

if submit:
    if password != confirm_password:
        st.error("As senhas não coincidem!")
    else:
        try:
            response = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "data": {
                    "escritorio_id": escritorio_id  # Dados adicionais no cadastro
                }
            })
            if response.user:
                st.success("Usuário cadastrado com sucesso!")
                st.info("Verifique seu email para confirmar a conta (se a verificação estiver habilitada).")
            else:
                st.error("Falha no cadastro. Confira as informações e tente novamente.")
        except Exception as e:
            st.error(f"Erro ao cadastrar: {e}")