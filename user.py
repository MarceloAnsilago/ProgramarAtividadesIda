import streamlit as st

def main_app():
    st.title("Aplicação Comum")
    unidade = st.session_state.get("selected_unidade", None)
    if unidade:
        st.write(f"Aplicação filtrada para a Unidade: {unidade}")
    else:
        st.write("Nenhuma unidade selecionada.")
    st.write("Aqui vai o conteúdo da aplicação comum.")
    
if __name__ == "__main__":
    main_app()
