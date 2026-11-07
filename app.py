import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Analyse des Combinaisons", page_icon="📦", layout="wide")

st.title("📦 Analyse des Combinaisons de Commandes")
st.markdown("Analyse des paniers, gestion des fichiers, classement des SKU et recherche par référence.")

# Dossier de stockage persistant sur le serveur / dépôt
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# --- GESTION DES FICHIERS ---
st.sidebar.header("📁 Gestion des Fichiers")

fichiers_persistants = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.csv')])

uploaded_files = st.sidebar.file_uploader(
    "Ajouter de nouveaux fichiers CSV", 
    type=["csv"], 
    accept_multiple_files=True
)

if uploaded_files:
    for uploaded_file in uploaded_files:
        file_path = os.path.join(DATA_DIR, uploaded_file.name)
        if not os.path.exists(file_path):
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
    fichiers_persistants = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.csv')])

if fichiers_persistants:
    st.sidebar.markdown("**Fichiers enregistrés en mémoire :**")
    for f in fichiers_persistants:
        col_f1, col_f2 = st.sidebar.columns([0.8, 0.2])
        col_f1.text(f)
        if col_f2.button("🗑️", key=f"del_{f}", help=f"Supprimer {f}"):
            os.remove(os.path.join(DATA_DIR, f))
            st.rerun()
else:
    st.sidebar.info("Aucun fichier en mémoire. Veuillez en uploader un ci-dessus.")

# --- CHARGEMENT ET TRAITEMENT DES DONNÉES ---
if fichiers_persistants:
    with st.spinner("Chargement et traitement des données en cours..."):
        dfs = []
        for f in fichiers_persistants:
            file_path = os.path.join(DATA_DIR, f)
            df_temp = pd.read_csv(file_path, low_memory=False)
            dfs.append(df_temp)
        
        raw_df = pd.concat(dfs, ignore_index=True)
        
    st.success(f"Données brutes chargées ({len(fichiers_persistants)} fichier(s)) : **{len(raw_df)} lignes au total**.")

    col_id = 'id' if 'id' in raw_df.columns else None
    col_date = 'originCreatedAt' if 'originCreatedAt' in raw_df.columns else None
    col_sku = 'orderItems.productRef' if 'orderItems.productRef' in raw_df.columns else None
    col_qty = 'orderItems.quantity' if 'orderItems.quantity' in raw_df.columns else None
    
    # La colonne F correspond usuellement à l'index 5 ou à une colonne spécifique (ex: 'weight' ou similaire si nommée, sinon on sécurise par index ou nom)
    # D'après les structures standard, on cherche une colonne de poids ou l'index 5 (colonne F)
    col_weight = None
    if 'weight' in raw_df.columns:
        col_weight = 'weight'
    elif len(raw_df.columns) > 5:
        col_weight = raw_df.columns[5] # Colonne F (index 5)

    if col_id and col_sku:
        if col_date:
            raw_df['parsed_date'] = pd.to_datetime(raw_df[col_date], errors='coerce').dt.date
            dates_dispo = sorted([d for d in raw_df['parsed_date'].dropna().unique()])
            
            st.sidebar.header("Filtre temporel")
            selected_dates = st.sidebar.multiselect("Sélectionner les jours à analyser", dates_dispo, default=dates_dispo)
            
            if selected_dates:
                df_work = raw_df[raw_df['parsed_date'].isin(selected_dates)].copy()
            else:
                df_work = raw_df.copy()
        else:
            df_work = raw_df.copy()

        df_filtered = df_work.dropna(subset=[col_id, col_sku]).copy()
        df_filtered = df_filtered.drop_duplicates(subset=[col_id, col_sku], keep='last')

        @st.cache_data
        def compute_order_combinations(dataframe, id_col, sku_col, qty_col, weight_col):
            order_groups = []
            for order_id, group in dataframe.groupby(id_col):
                items = []
                for _, row in group.iterrows():
                    sku = str(row[sku_col])
                    qty = int(row[qty_col]) if qty_col and pd.notna(row[qty_col]) else 1
                    
                    # Récupération et conversion du poids de la colonne F en kg (arrondi 1 décimale)
                    weight_val = 0.0
                    if weight_col and pd.notna(row[weight_col]):
                        try:
                            w_raw = float(str(row[weight_col]).replace(',', '.'))
                            weight_val = round(w_raw / 1000.0, 1)
                        except:
                            weight_val = 0.0

                    items.append({
                        'sku': sku,
                        'qty': qty,
                        'weight': weight_val,
                        'label': f"{sku} (x{qty})"
                    })
                
                # Tri alphabétique des SKU pour la combinaison
                items_sorted = sorted(items, key=lambda x: x['sku'])
                comb_str = " + ".join([i['label'] for i in items_sorted])
                
                order_groups.append({
                    'id': order_id,
                    'combinaison': comb_str,
                    'items_list': items_sorted,
                    'nb_articles_differents': len(items_sorted),
                    'lignes_raw': len(group)
                })
            return pd.DataFrame(order_groups)

        df_orders = compute_order_combinations(df_filtered, col_id, col_sku, col_qty, col_weight)

        if not df_orders.empty:
            # 3 onglets désormais : Combinaisons, Recherche SKU, Classement SKU
            tab1, tab2, tab3 = st.tabs([
                "📊 Toutes les Combinaisons", 
                "🔍 Recherche par Référence (SKU)", 
                "🏆 Classement des Ventes par SKU"
            ])

            with tab1:
                st.subheader("Classement des combinaisons de commandes uniques")
                comb_counts = df_orders['combinaison'].value_counts().reset_index()
                comb_counts.columns = ['Combinaison de SKU', 'Nombre de Commandes']
                
                col1, col2 = st.columns(2)
                col1.metric("Commandes uniques totales analysées", len(df_orders))
                col2.metric("Combinaisons uniques différentes", len(comb_counts))

                st.dataframe(comb_counts, use_container_width=True, hide_index=True)

            with tab2:
                st.subheader("Filtrer par produit spécifique")
                all_skus = sorted(df_filtered[col_sku].astype(str).unique())
                selected_sku = st.selectbox("Choisir ou taper une référence (SKU)", all_skus)

                if selected_sku:
                    matching_orders = df_orders[df_orders['items_list'].apply(lambda items: any(i['sku'] == selected_sku for i in items))]
                    
                    st.info(f"Le produit **{selected_sku}** apparaît dans **{len(matching_orders)}** commandes uniques.")
                    
                    sku_comb_counts = matching_orders['combinaison'].value_counts().reset_index()
                    sku_comb_counts.columns = ['Combinaison associée', 'Nombre de Commandes']
                    
                    st.markdown("#### Détail des combinaisons contenant ce produit :")
                    st.dataframe(sku_comb_counts, use_container_width=True, hide_index=True)

                    # Tableau récapitulatif avec le poids colis (colonne F convertie en kg)
                    st.markdown("#### ⚖️ Détail des commandes et poids colis associés :")
                    detailed_rows = []
                    for _, row in matching_orders.iterrows():
                        # Chercher le poids spécifique de ce SKU dans la commande
                        w_colis = next((i['weight'] for i in row['items_list'] if i['sku'] == selected_sku), 0.0)
                        detailed_rows.append({
                            'ID Commande': row['id'],
                            'Combinaison Complète': row['combinaison'],
                            'Poids Colis (kg)': f"{w_colis} kg"
                        })
                    df_details = pd.DataFrame(detailed_rows)
                    st.dataframe(df_details, use_container_width=True, hide_index=True)

            with tab3:
                st.subheader("Classement général des ventes par Référence (SKU)")
                st.markdown("Classement basé sur la quantité totale vendue et le nombre d'apparitions par SKU sur la plage sélectionnée.")
                
                # Agréger les données par SKU
                sku_stats = []
                for _, row in df_orders.iterrows():
                    for item in row['items_list']:
                        sku_stats.append({
                            'SKU': item['sku'],
                            'Quantite': item['qty']
                        })
                
                if sku_stats:
                    df_sku_stats = pd.DataFrame(sku_stats)
                    # Groupby pour sommer les quantités et compter le nombre de commandes
                    sku_summary = df_sku_stats.groupby('SKU').agg(
                        Commandes_Totales=('Quantite', 'count'),
                        Quantite_Totale_Vendue=('Quantite', 'sum')
                    ).reset_index()
                    
                    # Trier par quantité totale vendue décroissante
                    sku_summary = sku_summary.sort_values(by='Quantite_Totale_Vendue', ascending=False).reset_index(drop=True)
                    
                    st.dataframe(sku_summary, use_container_width=True, hide_index=True)
                else:
                    st.warning("Aucune statistique SKU disponible.")
        else:
            st.warning("Aucune commande valide trouvée après application des filtres.")
    else:
        st.error(f"Colonnes requises introuvables dans le CSV. Colonnes détectées : {list(raw_df.columns)}")
else:
    st.info("Veuillez uploader au moins un fichier CSV via le panneau latéral pour commencer.")
