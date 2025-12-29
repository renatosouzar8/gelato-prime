import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Gelato Prime",
    page_icon="🍦",
    layout="centered", # Melhor para mobile
    initial_sidebar_state="collapsed"
)

# --- CSS PERSONALIZADO (Mobile First) ---
st.markdown("""
<style>
    /* Esconder Menu Hamburger e Footer padrão para visual mais limpo */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Aumentar botões para toque */
    .stButton > button {
        height: 3.5rem;
        font-size: 1.2rem;
        font-weight: bold;
        border-radius: 12px;
    }
    
    /* Melhorar visual das Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 3rem;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 8px 8px 0 0;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
        flex: 1; /* Tabs com largura igual */
    }
    .stTabs [aria-selected="true"] {
        background-color: #FF4B4B; /* Cor destaque */
        color: white;
    }

    /* Cards de Metricas */
    div[data-testid="metric-container"] {
        background-color: #f9f9f9;
        border: 1px solid #e0e0e0;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- DADOS E CONEXÃO ---

# GERENCIAMENTO DE ESTADO (SESSION STATE)
if 'df_transacoes' not in st.session_state:
    st.session_state.df_transacoes = pd.DataFrame()
if 'df_catalog' not in st.session_state:
    st.session_state.df_catalog = pd.DataFrame()

def refresh_data(ttl_val=0):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # Puxamos com ttl variável (0 para forçar, TTL_DURATION para cache)
        # Se ttl_val > 0, o Streamlit usa o cache se não tiver expirado
        st.session_state.df_catalog = conn.read(worksheet="Produtos", ttl=ttl_val)
        st.session_state.df_transacoes = conn.read(worksheet="Transacoes", ttl=ttl_val)
        
        # Converter datas
        if not st.session_state.df_transacoes.empty and 'data' in st.session_state.df_transacoes.columns:
             st.session_state.df_transacoes['data'] = pd.to_datetime(st.session_state.df_transacoes['data'], format='mixed')
             
        st.toast("Dados atualizados do Google Sheets!", icon="🔄")
    except Exception as e:
        # Fallback silencioso ou toast de erro, mas mantém o estado anterior se possível
        st.error(f"Erro ao buscar dados: {e}")

# Função para inicializar dados na primeira carga
def ensure_data_loaded():
    if not st.session_state.data_loaded:
        # Na primeira carga (frio ou wake up), tentamos usar cache se possível para responder rápido
        # e evitar timeout de conexão inicial.
        refresh_data(ttl_val=TTL_DURATION)
        st.session_state.data_loaded = True # Marca como carregado para não tentar de novo no próximo rerun
        
        # Se após refresh o catálogo estiver vazio, criar estrutura básica na memória para não quebrar UI
        if st.session_state.df_catalog.empty:
             st.session_state.df_catalog = pd.DataFrame(columns=['produto', 'custo', 'venda'])

# Funções de Salvamento com Atualização Local (Otimista)
def save_catalog_state(df_new):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # 1. Update Remote
        conn.update(worksheet="Produtos", data=df_new)
        # 2. Update Local State (Imediato)
        st.session_state.df_catalog = df_new
        st.cache_data.clear() # Limpar cache global só por garantia
        return True
    except Exception as e:
        st.error(f"Erro ao salvar catálogo remoto: {e}")
        return False

def save_transaction_state(new_row_dict):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # 1. Update Local State (Instantâneo)
        new_df = pd.DataFrame([new_row_dict])
        if st.session_state.df_transacoes.empty:
             st.session_state.df_transacoes = new_df
        else:
             st.session_state.df_transacoes = pd.concat([st.session_state.df_transacoes, new_df], ignore_index=True)
            
        # 2. Update Remote
        conn.update(worksheet="Transacoes", data=st.session_state.df_transacoes)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar transação remota: {e}")
        return False

# Função auxiliar para calcular inventário
def calculate_inventory(df_transacoes, products_list):
    inventory = {p: 0 for p in products_list}
    if df_transacoes.empty:
        return inventory
        
    for idx, row in df_transacoes.iterrows():
        prod = row['produto']
        tipo = row['tipo_movimento']
        q = row['quantidade']
        
        # Se produto não existe mais no catálogo, ainda conta se tiver histórico
        if prod not in inventory:
            inventory[prod] = 0
            
        if tipo == "Compra Estoque":
            inventory[prod] += q
        else:
            inventory[prod] -= q
    return inventory

# Salvar ajuste de estoque (usando o novo save state)
def save_adjustment(produto, delta_qtd, custo_unitario):
    tipo = "Compra Estoque" if delta_qtd > 0 else "Quebra/Perda"
    qtd_abs = abs(delta_qtd)
    total_monetario = 0 
    
    new_row = {
        "data": datetime.now().isoformat(),
        "produto": produto,
        "tipo_movimento": tipo,
        "quantidade": qtd_abs,
        "valor_unitario": custo_unitario,
        "total_monetario": total_monetario
    }
    return save_transaction_state(new_row)

# --- UI APP ---

# Header com Logo
col_logo, col_title = st.columns([1, 4])
with col_logo:
    try:
        st.image("logo.jpg", width=60)
    except:
        st.write("🍦")
with col_title:
    st.markdown("### Gelato Prime")

# Garantir dados carregados ao iniciar
ensure_data_loaded()

# Alias para facilitar uso no código UI (apontando para Session State)
df_catalog = st.session_state.df_catalog
products_list = df_catalog['produto'].tolist() if not df_catalog.empty else []

# Botão de Refresh Manual
if st.button("🔄 Atualizar Dados da Nuvem", help="Força baixar dados novos do Google Sheets"):
    refresh_data(ttl_val=0) # Força reload
    st.rerun()

# Tabs de Navegação
tab_registrar, tab_gestao, tab_config = st.tabs(["📝 Registrar", "📊 Gestão", "⚙️ Config"])

# --- ABA 1: REGISTRAR ---
with tab_registrar:
    st.markdown("##### Movimentação Rápida")
    
    with st.container():
        with st.form("transaction_form"):
            # Input 1: Produto
            if not products_list:
                st.warning("Cadastre produtos na aba Configuração!")
                produto = None
            else:
                produto = st.selectbox("Produto", products_list, label_visibility="collapsed", placeholder="Selecione o produto")
            
            col_form_1, col_form_2 = st.columns([1, 1])
            
            with col_form_1:
                # Input 2: Quantidade
                qtd = st.number_input("Qtd", min_value=1, value=1, step=1)
                
            with col_form_2:
                # Input 3: Tipo
                tipo_map = {
                    "🔴 Venda": "Venda",
                    "🏠 Família": "Consumo Família",
                    "🟢 Compra": "Compra Estoque",
                    "☠️ Quebra": "Quebra/Perda"
                }
                tipo_display = st.radio("Tipo", list(tipo_map.keys()), horizontal=True, label_visibility="visible") 
                tipo_movimento = tipo_map[tipo_display]
            
            # Botão Confirmar
            submitted = st.form_submit_button("✅ CONFIRMAR MOVIMENTO", use_container_width=True)
            
            if submitted:
                if not produto:
                    st.error("Selecione um produto!")
                else:
                    # Buscar preços no DF do catálogo (Usando session state)
                    try:
                        item_data = df_catalog[df_catalog['produto'] == produto].iloc[0]
                        custo_item = float(item_data['custo'])
                        venda_item = float(item_data['venda'])
                    except:
                        custo_item = 0.0
                        venda_item = 0.0
                    
                    if tipo_movimento == "Venda":
                        valor_unitario = venda_item
                        total_monetario = valor_unitario * qtd
                    elif tipo_movimento in ["Consumo Família", "Compra Estoque", "Quebra/Perda"]:
                        valor_unitario = custo_item
                        if tipo_movimento == "Compra Estoque":
                            total_monetario = valor_unitario * qtd * -1
                        elif tipo_movimento == "Consumo Família":
                            total_monetario = valor_unitario * qtd
                        else:
                            total_monetario = 0 

                    # Preparar linha
                    new_row = {
                        "data": datetime.now().isoformat(),
                        "produto": produto,
                        "tipo_movimento": tipo_movimento,
                        "quantidade": qtd,
                        "valor_unitario": valor_unitario,
                        "total_monetario": total_monetario
                    }
                    
                    if save_transaction_state(new_row):
                        st.toast(f"✅ {produto} ({qtd}x) registrado!", icon="🍦")

# --- ABA 2: GESTÃO ---
with tab_gestao:
    df = st.session_state.df_transacoes
    
    if df.empty:
        st.info("Nenhuma transação registrada.")
    else:
        # Filtros de Período
        st.markdown("##### 📅 Filtros")
        periodo = st.selectbox("Período", ["Hoje", "Últimos 7 Dias", "Este Mês", "Personalizado"], label_visibility="collapsed")
        
        hoje = pd.Timestamp.now().normalize()
        # Garantir que temos coluna de data convertida
        if 'data_dt' not in df.columns:
             df['data_dt'] = pd.to_datetime(df['data'], errors='coerce')
        
        if periodo == "Hoje":
            start_date = hoje
            end_date = hoje + pd.Timedelta(days=1)
        elif periodo == "Últimos 7 Dias":
            start_date = hoje - pd.Timedelta(days=7)
            end_date = hoje + pd.Timedelta(days=1)
        elif periodo == "Este Mês":
            start_date = hoje.replace(day=1)
            end_date = (start_date + pd.offsets.MonthEnd(0)) + pd.Timedelta(days=1)
        else:
            c1, c2 = st.columns(2)
            d1 = c1.date_input("Início", hoje)
            d2 = c2.date_input("Fim", hoje)
            start_date = pd.to_datetime(d1)
            end_date = pd.to_datetime(d2) + pd.Timedelta(days=1)
            
        # Filtrar DF para KPIs
        df_filtered = df[(df['data_dt'] >= start_date) & (df['data_dt'] < end_date)]
        
        # 1. Faturamento
        vendas_periodo = df_filtered[df_filtered['tipo_movimento'] == 'Venda']
        faturamento = vendas_periodo['total_monetario'].sum()
        
        # 2. Custo Família
        custo_familia = df_filtered[df_filtered['tipo_movimento'] == 'Consumo Família']['total_monetario'].sum()
        
        # 3. Lucro Bruto
        receita = faturamento
        cmv = 0
        for idx, row in vendas_periodo.iterrows():
            p_nome = row['produto']
            q = row['quantidade']
            try:
                c_item = float(df_catalog[df_catalog['produto'] == p_nome].iloc[0]['custo'])
            except:
                c_item = 0
            cmv += (q * c_item)
            
        lucro = receita - cmv
        
        # Exibir KPIs
        c1, c2, c3 = st.columns(3)
        c1.metric("Faturamento", f"R$ {faturamento:.2f}")
        c2.metric("Custo Família", f"R$ {custo_familia:.2f}")
        c3.metric("Lucro Estimado", f"R$ {lucro:.2f}")
        
        st.markdown("---")
        
        # Estoque Atual (Calculado sobre TODO o histórico, não filtrado)
        st.markdown("##### 📦 Estoque Atual")
        
        # IMPORTANTE: Calcular estoque em cima de df completo, não df_filtered
        inventory = calculate_inventory(df, products_list)
        
        inv_data = []
        for p, saldo in inventory.items():
            if p in products_list or saldo != 0:
                if saldo < 5:
                    status = "🚨"
                else:
                    status = "✅"
                inv_data.append({"Status": status, "Produto": p, "Saldo": saldo})
            
        st.dataframe(
            pd.DataFrame(inv_data),
            use_container_width=True,
            column_config={
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Saldo": st.column_config.NumberColumn("Qtd", format="%d")
            },
            hide_index=True
        )

# --- ABA 3: CONFIG ---
with tab_config:
    st.markdown("##### ⚙️ Gerenciar Produtos")
    
    # Check de Erro no Catálogo
    # Se estiver vazio mas não tiver erro, ok. Se tiver erro attrs, mostra botão.
    # Como mudamos a lógica de load, o erro vem no Exception do refresh_data.
    # Vamos checar se o df_catalog está vazio.
    if df_catalog.empty:
         st.warning("Catálogo vazio ou não carregado.")
         st.info("Se você ainda não criou a aba 'Produtos', clique abaixo.")
         if st.button("🛠️ CRIAR ABA 'Produtos' AGORA"):
             initial_data = pd.DataFrame([
                {"produto": "Paleta Morango", "custo": 3.40, "venda": 12.00},
                {"produto": "Picolé Morango", "custo": 1.20, "venda": 4.50},
             ])
             if save_catalog_state(initial_data):
                 st.success("Criado com sucesso! Atualizando...")
                 st.rerun()

    # Form para Adicionar
    with st.expander("Novo Produto", expanded=True):
        with st.form("new_product_form"): # FORMULÁRIO PARA EVITAR RERUNS
            new_prod_name = st.text_input("Nome do Produto")
            c1, c2 = st.columns(2)
            new_custo = c1.number_input("Preço de Custo", min_value=0.0, step=0.1, format="%.2f")
            new_venda = c2.number_input("Preço de Venda", min_value=0.0, step=0.1, format="%.2f")
            
            submitted = st.form_submit_button("✚ Adicionar Produto")
            
            if submitted:
                if new_prod_name and new_prod_name not in products_list:
                    new_item = pd.DataFrame([{"produto": new_prod_name, "custo": new_custo, "venda": new_venda}])
                    if df_catalog.empty:
                        df_updated = new_item
                    else:
                        df_updated = pd.concat([df_catalog, new_item], ignore_index=True)
                    
                    if save_catalog_state(df_updated):
                        st.success("Produto adicionado!")
                        st.rerun()
                elif new_prod_name in products_list:
                    st.error("Produto já existe!")
    
    st.markdown("---")
    st.markdown("##### Lista de Produtos")
    
    if not df_catalog.empty:
        # Calcular estoque atual para exibir no editor
        # Usamos df transacoes completo do session state
        current_inventory = calculate_inventory(st.session_state.df_transacoes, products_list)
        
        for index, row in df_catalog.iterrows():
            p_nome = row['produto']
            estoque_atual = current_inventory.get(p_nome, 0)
            
            with st.expander(f"{p_nome} (Estoque: {estoque_atual})"):
                with st.form(key=f"edit_{index}"):
                    c1, c2 = st.columns(2)
                    edit_nome = c1.text_input("Nome", p_nome)
                    
                    c_price, c_sell = st.columns(2)
                    edit_custo = c_price.number_input("Custo", value=float(row['custo']), step=0.10)
                    edit_venda = c_sell.number_input("Venda", value=float(row['venda']), step=0.50)
                    
                    st.divider()
                    st.markdown("**Ajuste de Estoque**")
                    c_stock_1, c_stock_2 = st.columns([1, 2])
                    new_stock_val = c_stock_2.number_input("Estoque Real", value=int(estoque_atual), step=1, key=f"stock_{index}")
                    
                    cols_btn = st.columns([1, 1])
                    update_btn = cols_btn[0].form_submit_button("💾 Salvar")
                    delete_check = cols_btn[1].checkbox("🗑️ Excluir")

                    if update_btn:
                        if delete_check:
                            df_updated = df_catalog[df_catalog['produto'] != p_nome]
                            save_catalog_state(df_updated)
                            st.success(f"Excluído: {p_nome}")
                            st.rerun()
                        else:
                            # 1. Update Catalog State
                            df_catalog.at[index, 'produto'] = edit_nome
                            df_catalog.at[index, 'custo'] = edit_custo
                            df_catalog.at[index, 'venda'] = edit_venda
                            save_catalog_state(df_catalog) # Salva estado atualizado
                            
                            # 2. Update Stock
                            if new_stock_val != estoque_atual:
                                delta = new_stock_val - estoque_atual
                                save_adjustment(edit_nome, delta, edit_custo)
                                st.toast(f"Estoque ajustado!", icon="📦")
                            
                            st.success("Atualizado!")
                            st.rerun()

st.success("Sistema Carregado")
