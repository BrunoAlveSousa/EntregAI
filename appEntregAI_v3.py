# app.py - ENTREGAI FINAL - Com OTIF % e TMA formatados
import streamlit as st
import pandas as pd
import math

st.set_page_config(page_title="EntregAI", page_icon="https://img.icons8.com/fluency/48/bot.png", layout="wide")

# Título com robô
st.markdown("""
<div style="display: flex; align-items: center; justify-content: center; margin: 40px 0;">
    <img src="https://img.icons8.com/fluency/180/bot.png" width="160" style="margin-right: 25px;">
    <div>
        <h1 style="margin:0; font-size:4.5rem; font-weight:bold;
                   background:linear-gradient(90deg,#1E90FF,#00CED1);
                   -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
            EntregAI
        </h1>
        <p style="margin:5px 0 0 0; font-size:1.5rem; color:#555;">
            Otimização de Cartas Frete • Postes de Concreto
        </p>
    </div>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

with st.sidebar:
    st.header("Upload das Tabelas")
    t1 = st.file_uploader("Tabela 1 – Carga Limite", type=["xlsx"])
    t2 = st.file_uploader("Tabela 2 – Requisições", type=["xlsx"])
    t3 = st.file_uploader("Tabela 3 – Peso", type=["xlsx"])
    t4 = st.file_uploader("Tabela 4 – Saldo OCM", type=["xlsx"])
    t5 = st.file_uploader("Tabela 5 – KPIs", type=["xlsx"])

# ===================== FUNÇÕES =====================
def allocate_from_ocms(credor, sku, qty, weight, balances):
    allocations = []
    ocm_df = balances[(balances['cod_credor'] == credor) &
                      (balances['cod_material'] == sku) &
                      (balances['saldo_disponivel'] > 0)].sort_values('num_ocm')
    remaining = qty
    for idx, row in ocm_df.iterrows():
        if remaining <= 0: break
        take = min(remaining, row['saldo_disponivel'])
        balances.at[idx, 'saldo_disponivel'] -= take
        allocations.append((row['num_ocm'], take, weight, take * weight))
        remaining -= take
    return allocations

all_fulfilled = []  # Variável global para coletar tudo

def try_fill_carta(option, pending_items, balances, carta_num, scenario_name):
    credor = option['cod_credor']
    branch = option['cod_estabelecimento_credor']
    min_load = option['Carga Mínima']
    max_load = option['Carga máxima']

    # Pesos
    weight_dict = {}
    for item in pending_items:
        if item['remaining'] <= 0: continue
        sku = item['sku']
        w = df3[(df3['cod_credor'] == credor) &
                (df3['cod_estabelecimento_credor'] == branch) &
                (df3['cod_material'] == sku)]
        if not w.empty:
            weight_dict[sku] = w['pes_material_credor'].iloc[0]

    viable = [it for it in pending_items if it['remaining'] > 0 and it['sku'] in weight_dict]
    if not viable: return False, carta_num, {}

    viable.sort(key=lambda x: x['remaining'] * weight_dict[x['sku']], reverse=True)

    current_load = 0
    planned = []
    for item in viable:
        if current_load >= min_load: break
        weight = weight_dict[item['sku']]
        avail = balances[(balances['cod_credor'] == credor) & (balances['cod_material'] == item['sku'])]['saldo_disponivel'].sum()
        take = min(item['remaining'], avail, math.floor((max_load - current_load) / weight))
        if take > 0:
            planned.append((item, take))
            current_load += take * weight

    if current_load < min_load:
        return False, carta_num, {}

    # ====== ALOCAÇÃO REAL ======
    for item, take in planned:
        weight = weight_dict[item['sku']]
        allocs = allocate_from_ocms(credor, item['sku'], take, weight, balances)
        for ocm, qtd, pu, pt in allocs:
            all_fulfilled.append({
                'Nº Carta': carta_num,
                'Cenário': scenario_name,
                'Fornecedor': option['Fornecedor'],
                'Nº Requisição': item['req'],
                'SKU': item['sku'],
                'Quantidade': qtd,
                'OCM': ocm,
                'Peso Unitário (kg)': pu,
                'Peso Total (kg)': pt,
                'Carga Total Carta (kg)': current_load
            })
        item['remaining'] -= take

    return True, carta_num + 1, {}

# ===================== PROCESSAMENTO =====================
if t1 and t2 and t3 and t4 and t5:
    df1 = pd.read_excel(t1, sheet_name=0)
    df2 = pd.read_excel(t2, sheet_name=0)
    df3 = pd.read_excel(t3, sheet_name=0)
    df4 = pd.read_excel(t4, sheet_name=0)
    df5 = pd.read_excel(t5, sheet_name=0)

    st.success("Todas as tabelas carregadas!")

    if st.button("GERAR OTIMIZAÇÃO DE CARTAS FRETE", type="primary", use_container_width=True):
        with st.spinner("Gerando cartas por fornecedor..."):
            all_fulfilled = []
            all_unfulfilled = []
            summary = []

            for credor in df1['cod_credor'].unique():
                nome = df1[df1['cod_credor'] == credor]['Fornecedor'].iloc[0]
                scenario = f"Fornecedor: {nome} (cod_{credor})"

                options = df1[df1['cod_credor'] == credor]
                balances = df4.copy()
                carta_num = 1

                for destino in df2['dep_destino'].unique():
                    reqs = df2[df2['dep_destino'] == destino]
                    pending = [{'req': r['num_requisicao_puxada'], 'sku': r['cod_mat'], 'remaining': r['Quantidade']}
                               for _, r in reqs.iterrows()]

                    while any(x['remaining'] > 0 for x in pending):
                        filled = False
                        for _, opt in options.iterrows():
                            success, carta_num, _ = try_fill_carta(opt, pending, balances, carta_num, scenario)
                            if success:
                                filled = True
                                break
                        if not filled:
                            break

                    for it in pending:
                        if it['remaining'] > 0:
                            all_unfulfilled.append({
                                'Cenário': scenario,
                                'Requisição': it['req'],
                                'SKU': it['sku'],
                                'Qtd Não Atendida': it['remaining']
                            })

                df_f = pd.DataFrame(all_fulfilled)
                cartas = df_f[df_f['Cenário'] == scenario]['Nº Carta'].nunique() if not df_f.empty else 0
                atendido = df_f[df_f['Cenário'] == scenario]['Quantidade'].sum() if not df_f.empty else 0
                nao_atendido = sum(x.get('Qtd Não Atendida', 0) for x in all_unfulfilled if x['Cenário'] == scenario)
                summary.append({
                    'Supplier': f"{nome} (cod_credor: {credor})",
                    'Qtde Cartas': cartas,
                    'Postes Atendidos': atendido,
                    'Postes Não Atendidos': nao_atendido,
                    'cod_credor': credor  # temporário para merge
                })

        import time
        my_bar = st.progress(0, text="Finalizando...")
        for i in range(100):
            time.sleep(0.01)
            my_bar.progress(i + 1)
        my_bar.empty()

        st.success("Otimização concluída!")

        df_result = pd.DataFrame(all_fulfilled)
        df_nao = pd.DataFrame(all_unfulfilled)
        summary_df = pd.DataFrame(summary)

        # ===================== MERGE COM TABELA 5 (KPIs) =====================
        kpis = df5[['cod_credor', 'otif', 'tma']].copy()
        kpis = kpis.rename(columns={'otif': 'OTIF', 'tma': 'TMA'})

        summary_df = summary_df.merge(kpis, on='cod_credor', how='inner')
        summary_df = summary_df.drop(columns=['cod_credor'])

        # ===================== FORMATAÇÃO DOS INDICADORES =====================
        summary_df['OTIF'] = (summary_df['OTIF'] * 100).round(2).astype(str) + '%'
        summary_df['TMA'] = summary_df['TMA'].round(2)

        # Função de estilo para OTIF (aplica cor baseada no valor numérico antes da formatação)
        def style_otif(row):
            otif_val = float(row['OTIF'].replace('%', '')) / 100  # converte de volta para decimal
            color = '#ff1500' if otif_val < 0.7 else '#41b54a'
            return ['color: ' + color if col == 'OTIF' else '' for col in row.index]

        # ===================== EXIBIÇÃO =====================
        col1, col2 = st.columns([3.5, 1.5])

        with col2:
            st.markdown("### Resumo por Fornecedor")
            styled = summary_df.style.apply(style_otif, axis=1)
            st.dataframe(styled, use_container_width=True)

        with col1:
            st.markdown("### Cartas Geradas")
            if not df_result.empty:
                for scenario in df_result['Cenário'].unique():
                    df_sc = df_result[df_result['Cenário'] == scenario]
                    fornecedor = df_sc['Fornecedor'].iloc[0]
                    with st.expander(f"{scenario} – {fornecedor} – {df_sc['Nº Carta'].nunique()} carta(s) gerada(s)", expanded=False):
                        for carta in sorted(df_sc['Nº Carta'].unique()):
                            df_carta = df_sc[df_sc['Nº Carta'] == carta]
                            carga = df_carta['Carga Total Carta (kg)'].iloc[0]
                            st.markdown(f"**Carta {int(carta)}** – Carga total: **{carga:,.0f} kg**")
                            cols_display = ['Nº Requisição', 'SKU', 'Quantidade', 'OCM', 'Peso Total (kg)']
                            st.dataframe(df_carta[cols_display].sort_values('SKU'), use_container_width=True)
                            st.markdown("---")

                csv = df_result.to_csv(index=False).encode()
                st.download_button("Baixar Todas as Cartas (CSV)", csv, "cartas_geradas.csv", "text/csv")

            if not df_nao.empty:
                st.markdown("### Requisições Não Atendidas")
                st.dataframe(df_nao, use_container_width=True)

else:
    st.info("Faça upload das 5 tabelas para começar.")


st.markdown("<p style='text-align:center;color:#888;margin-top:50px'>EntregAI © GEPM 2026 – Otimização de Carga Inteligente</p>", unsafe_allow_html=True)
