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

# Funções de Dados

def load_catalog():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(worksheet="Produtos", ttl=0)
        if df.empty or 'produto' not in df.columns:
             return pd.DataFrame([
                {"produto": "Paleta Morango", "custo": 3.40, "venda": 12.00},
                {"produto": "Picolé Morango", "custo": 1.20, "venda": 4.50},
             ])
        return df
    except:
        return pd.DataFrame([
            {"produto": "Paleta Morango", "custo": 3.40, "venda": 12.00},
            {"produto": "Picolé Morango", "custo": 1.20, "venda": 4.50},
        ])

def save_catalog(df):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        conn.update(worksheet="Produtos", data=df)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar catálogo: {e}")
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
            # Qualquer saída (Venda, Família, Quebra)
            inventory[prod] -= q
    return inventory

# Salvar ajuste de estoque
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
    return save_transaction(new_row)


# Função para carregar dados (com cache para performance)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # Verifica se secrets existem antes de tentar conectar
        if "connections" not in st.secrets or "gsheets" not in st.secrets["connections"]:
            st.warning("⚠️ Configuração pendente: Adicione as credenciais do Google Sheets em `.streamlit/secrets.toml`.")
            return pd.DataFrame(columns=['data', 'produto', 'tipo_movimento', 'quantidade', 'valor_unitario', 'total_monetario'])

        # Lê a aba 'Transacoes'. TTL reduzido para refletir atualizações
        df = conn.read(worksheet="Transacoes", ttl=0)
        
        # Converter coluna de data para datetime se existir, senão cria DF vazio
        if not df.empty and 'data' in df.columns:
             df['data'] = pd.to_datetime(df['data'], format='mixed')
        else:
            # Estrutura base caso a planilha esteja vazia
            df = pd.DataFrame(columns=['data', 'produto', 'tipo_movimento', 'quantidade', 'valor_unitario', 'total_monetario'])
        return df
    except Exception as e:
        st.error(f"Erro ao conectar com Google Sheets: {e}")
        return pd.DataFrame(columns=['data', 'produto', 'tipo_movimento', 'quantidade', 'valor_unitario', 'total_monetario'])

# Função para salvar transação
def save_transaction(new_row):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = load_data()
        if df.empty:
            updated_df = pd.DataFrame([new_row])
        else:
            updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        conn.update(worksheet="Transacoes", data=updated_df)
        st.cache_data.clear() # Limpa cache para recarregar dados novos
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

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

# Carregar dados
df_catalog = load_catalog()
products_list = df_catalog['produto'].tolist() if not df_catalog.empty else []

# Tabs de Navegação
tab_registrar, tab_gestao, tab_config = st.tabs(["📝 Registrar", "📊 Gestão", "⚙️ Config"])

# --- ABA 1: REGISTRAR ---
with tab_registrar:
    st.markdown("##### Movimentação Rápida")
    
    with st.container():
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
        if st.button("✅ CONFIRMAR MOVIMENTO", use_container_width=True):
            if not produto:
                st.error("Selecione um produto!")
            else:
                # Buscar preços no DF do catálogo
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
                
                if save_transaction(new_row):
                    st.toast(f"✅ {produto} ({qtd}x) registrado!", icon="🍦")
                # Não faz rerun total para manter fluidez, toast é suficiente

# --- ABA 2: GESTÃO ---
with tab_gestao:
    df = load_data()
    
    if df.empty:
        st.info("Nenhuma transação registrada.")
    else:
        # Filtros de Período
        st.markdown("##### 📅 Filtros")
        periodo = st.selectbox("Período", ["Hoje", "Últimos 7 Dias", "Este Mês", "Personalizado"], label_visibility="collapsed")
        
        hoje = pd.Timestamp.now().normalize()
        df['data_dt'] = pd.to_datetime(df['data'])
        
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
            end_date = pd.to_datetime(d2) + pd.Timedelta(days=1) # Incluir o dia final
            
        # Filtrar DF para KPIs
        df_filtered = df[(df['data_dt'] >= start_date) & (df['data_dt'] < end_date)]
        
        # 1. Faturamento (Vendas no período)
        vendas_periodo = df_filtered[df_filtered['tipo_movimento'] == 'Venda']
        faturamento = vendas_periodo['total_monetario'].sum()
        
        # 2. Custo Família
        custo_familia = df_filtered[df_filtered['tipo_movimento'] == 'Consumo Família']['total_monetario'].sum()
        
        # 3. Lucro Bruto
        receita = faturamento
        cmv = 0
        for idx, row in vendas_periodo.iterrows():
            # Buscar custo atual do catálogo (simplificação) - Ideal seria histórico ou salvo na transação
            # fallback para valor_unitario caso seja Venda (mas venda tem preço de venda)
            # Tentar pegar do catalogo atual
            p_nome = row['produto']
            q = row['quantidade']
            try:
                # Se tiver no catalogo
                c_item = float(df_catalog[df_catalog['produto'] == p_nome].iloc[0]['custo'])
            except:
                # Se não, tenta estimar algo ou 0
                c_item = 0
            cmv += (q * c_item)
            
        lucro = receita - cmv
        
        # Exibir KPIs
        c1, c2, c3 = st.columns(3)
        c1.metric("Faturamento", f"R$ {faturamento:.2f}")
        c2.metric("Custo Família", f"R$ {custo_familia:.2f}")
        c3.metric("Lucro Estimado", f"R$ {lucro:.2f}")
        
        st.markdown("---")
        
        # Estoque Atual
        st.markdown("##### 📦 Estoque Atual")
        
        inventory = calculate_inventory(df, products_list)
        
        
        inv_data = []
        for p, saldo in inventory.items():
            # Só mostra produtos ativos ou com saldo != 0
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
    
    # Form para Adicionar
    with st.expander("Novo Produto", expanded=True):
        new_prod_name = st.text_input("Nome do Produto")
        c1, c2 = st.columns(2)
        new_custo = c1.number_input("Preço de Custo", min_value=0.0, step=0.1, format="%.2f")
        new_venda = c2.number_input("Preço de Venda", min_value=0.0, step=0.1, format="%.2f")
        
        if st.button("✚ Adicionar Produto"):
            if new_prod_name and new_prod_name not in products_list:
                new_item = pd.DataFrame([{"produto": new_prod_name, "custo": new_custo, "venda": new_venda}])
                if df_catalog.empty:
                    df_updated = new_item
                else:
                    df_updated = pd.concat([df_catalog, new_item], ignore_index=True)
                save_catalog(df_updated)
                st.success("Produto adicionado!")
                st.rerun()
            elif new_prod_name in products_list:
                st.error("Produto já existe!")
    
    st.markdown("---")
    st.markdown("---")
    st.markdown("##### Lista de Produtos")
    
    if not df_catalog.empty:
        # Calcular estoque atual para exibir no editor
        current_inventory = calculate_inventory(load_data(), products_list)
        
        # Usar expanders para edição
        for index, row in df_catalog.iterrows():
            p_nome = row['produto']
            
            # Expander com Título = Nome do Produto + Estoque
            estoque_atual = current_inventory.get(p_nome, 0)
            with st.expander(f"{p_nome} (Estoque: {estoque_atual})"):
                
                # Form de Edição
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
                    c_stock_1.info(f"Atual: {estoque_atual}")
                    
                    st.divider()
                    
                    cols_btn = st.columns([1, 1])
                    update_btn = cols_btn[0].form_submit_button("💾 Salvar Alterações")
                    
                    # Para deletar, precisamos de um botão fora do form ou lógica com checkbox dentro do form (submit único)
                    # Streamlit forms não suportam multiplos botões de submit com lógicas diferentes facilmente
                    delete_check = cols_btn[1].checkbox("🗑️ Excluir Produto")

                    if update_btn:
                        if delete_check:
                            # Lógica de Exclusão Robusta
                            # O drop pelo index pode falhar se o DF mudou. Vamos filtrar
                            df_updated = df_catalog[df_catalog['produto'] != p_nome]
                            save_catalog(df_updated)
                            st.success(f"Produto {p_nome} excluído!")
                            st.rerun()
                        else:
                            # Lógica de Atualização
                            # 1. Atualizar Catálogo
                            df_catalog.at[index, 'produto'] = edit_nome
                            df_catalog.at[index, 'custo'] = edit_custo
                            df_catalog.at[index, 'venda'] = edit_venda
                            save_catalog(df_catalog)
                            
                            # 2. Ajuste de Estoque (Se mudou)
                            if new_stock_val != estoque_atual:
                                delta = new_stock_val - estoque_atual
                                save_adjustment(edit_nome, delta, edit_custo)
                                st.toast(f"Estoque ajustado: {delta:+d}", icon="📦")
                            
                            st.success("Produto atualizado!")
                            st.rerun()

st.success("Sistema Carregado (Modo de Demonstração)")
