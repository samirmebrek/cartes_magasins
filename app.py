import pandas as pd
import folium
import googlemaps
import time
import json
import itertools
import streamlit as st
from streamlit_folium import folium_static
from urllib.parse import quote

# ----------------------------------------------------------------------------------------------------------------------
#                                             🔐 AUTHENTIFICATION                                                      #
# ----------------------------------------------------------------------------------------------------------------------
def login():
    st.title("🔐 Connexion à l'application")
    username = st.text_input("Nom d'utilisateur")
    password = st.text_input("Mot de passe", type="password")

    if st.button("Se connecter"):
        valid_user = st.secrets["auth"]["username"]
        valid_pass = st.secrets["auth"]["password"]
        if username == valid_user and password == valid_pass:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Identifiants incorrects.")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if not st.session_state.authenticated:
    login()
    st.stop()

# ----------------------------------------------
# CONFIGURATION
# ----------------------------------------------
st.set_page_config(page_title="Carte Kingfisher", layout="wide")

API_KEY = st.secrets["google"]["api_key"]
gmaps = googlemaps.Client(key=API_KEY)

# ----------------------------------------------
# INIT PAGE STATE
# ----------------------------------------------
if 'page' not in st.session_state:
    st.session_state.page = 'upload'  # 'upload' = page 1, 'map' = page 2

# Variable pour stocker cache en session
if 'geocode_cache' not in st.session_state:
    st.session_state.geocode_cache = {}

# Variable pour stocker données
if 'df' not in st.session_state:
    st.session_state.df = None
if 'magasins_df' not in st.session_state:
    st.session_state.magasins_df = None

# ----------------------------------------------
# FONCTION DE GÉOCODAGE AVEC CACHE
# ----------------------------------------------
def geocode_address(addr, geocode_cache):
    if addr in geocode_cache:
        return geocode_cache[addr]
    try:
        result = gmaps.geocode(addr)
        if result:
            location = result[0]['geometry']['location']
            city, postal_code = None, None
            for comp in result[0]['address_components']:
                if 'locality' in comp['types']:
                    city = comp['long_name']
                if 'postal_code' in comp['types']:
                    postal_code = comp['long_name']
            geocode_cache[addr] = {
                'latitude': location['lat'],
                'longitude': location['lng'],
                'ville': city or '',
                'code_postal': postal_code or ''
            }
            time.sleep(0.15)
            return geocode_cache[addr]
        else:
            return {'latitude': None, 'longitude': None, 'ville': None, 'code_postal': None}
    except Exception as e:
        st.error(f"Erreur pour {addr}: {e}")
        return {'latitude': None, 'longitude': None, 'ville': None, 'code_postal': None}


# ----------------------------------------------------------------------------------------------------------------------
#                                               PAGE 1 : UPLOAD + TRAITEMENT                                           #
# ----------------------------------------------------------------------------------------------------------------------
def page_upload():
    st.header("📁 Chargement des fichiers")

    # 📂 Uploader manuellement le fichier cache
    cache_upload = st.file_uploader("🔁 Charger un fichier cache JSON", type="json")
    if cache_upload:
        try:
            geocode_cache = json.load(cache_upload)
            st.sidebar.success("✅ Cache chargé depuis le fichier uploadé.")
        except Exception as e:
            geocode_cache = {}
            st.sidebar.error("❌ Erreur de lecture du cache : " + str(e))
    else:
        geocode_cache = {}
        st.sidebar.warning("⚠️ Aucun cache chargé. Un nouveau sera créé.")

    st.session_state.geocode_cache = geocode_cache

    livraisons_path = st.file_uploader("📄 Fichier des livraisons (CSV)", type="csv")
    magasins_path = st.file_uploader("🏪 Fichier des magasins (XLSX)", type="xlsx")


    if livraisons_path and magasins_path:
        if st.button("Lancer le géocodage et traitement"):

            with st.spinner("🔄 Chargement des données..."):

                # Chargement CSV livraisons
                df = pd.read_csv(livraisons_path)
                df.columns = df.columns.str.strip()
                if 'addresse_livraison' in df.columns:
                    df['adresse_livraison'] = df['addresse_livraison'].str.strip()
                else:
                    df['adresse_livraison'] = df['adresse_livraison'].str.strip()

                st.info("🔍 Démarrage du géocodage des adresses...")
                progress = st.progress(0)
                status_text = st.empty()

                livraisons_result = []
                unique_addrs = df['adresse_livraison'].unique()
                for i, addr in enumerate(unique_addrs):
                    status_text.text(f"📦 Géocodage livraison {i+1}/{len(unique_addrs)} : {addr}")
                    info = geocode_address(addr, st.session_state.geocode_cache)
                    livraisons_result.append({'adresse_livraison': addr, **info})
                    progress.progress((i + 1) / len(unique_addrs))

                livraisons_geo = pd.DataFrame(livraisons_result)
                df = df.merge(livraisons_geo, on='adresse_livraison', how='left')

                # Chargement Excel magasins
                magasins_df = pd.read_excel(magasins_path)
                magasins_df['addresse_collecte'] = magasins_df['addresse_collecte'].str.strip()

                st.info("🏪 Géocodage des adresses des magasins...")
                progress = st.progress(0)
                status_text = st.empty()
                unique_magasins = magasins_df['addresse_collecte'].unique()
                magasins_result = []

                for i, addr in enumerate(unique_magasins):
                    status_text.text(f"🏪 Magasin {i+1}/{len(unique_magasins)} : {addr}")
                    info = geocode_address(addr, st.session_state.geocode_cache)
                    magasins_result.append({'addresse_collecte': addr, **info})
                    progress.progress((i + 1) / len(unique_magasins))

                magasins_geo = pd.DataFrame(magasins_result)
                magasins_df = magasins_df.merge(magasins_geo, on='addresse_collecte', how='left')

                # ----------------------------------------------
                # 📥 Télécharger le cache mis à jour
                st.sidebar.download_button(
                    label="📅 Télécharger le cache mis à jour",
                    data=json.dumps(st.session_state.geocode_cache, indent=2),
                    file_name="geocode_cache_updated.json",
                    mime="application/json"
                )

                # Stocker les données dans session_state
                st.session_state.df = df
                st.session_state.magasins_df = magasins_df

                st.success("✅ Géocodage terminé et cache mis à jour.")

                # Passer à la page carte
                st.session_state.page = 'map'
                st.rerun()


# ----------------------------------------------------------------------------------------------------------------------
#                                                PAGE 2 : FILTRE + CARTE                                               #
# ----------------------------------------------------------------------------------------------------------------------
def page_map():

    st.set_page_config(page_title="Carte Kingfisher", layout="wide")

    st.header("🗺️ Carte des livraisons Kingfisher")

    df = st.session_state.df
    magasins_df = st.session_state.magasins_df

    if df is None or magasins_df is None:
        st.error("Aucune donnée disponible. Veuillez retourner à la page de chargement.")
        if st.button("Retour au chargement"):
            st.session_state.page = 'upload'
            st.experimental_rerun()
        return

    magasins_disponibles = sorted(df['magasin'].dropna().unique())

    # Création carte
    m = folium.Map(
        location=[46.603354, 1.888334],
        zoom_start=6,
        max_bounds=True
    )
    m.fit_bounds([[41.0, -5.0], [51.5, 9.5]])

    from folium.plugins import Fullscreen
    Fullscreen(position='topright').add_to(m)

    # Couleurs par magasin
    folium_colors = itertools.cycle([
        'red', 'green', 'orange', 'purple', 'cadetblue', 'darkred', 'blue',
        'lightgreen', 'lightblue', 'pink', 'black', 'gray', 'beige',
        'lightred', 'darkgreen', 'darkblue', 'lightgray', 'darkpurple'
    ])
    magasin_couleurs = {mag: next(folium_colors) for mag in magasins_disponibles}

    # Filtres dans la sidebar
    with st.sidebar:
        st.markdown("### 🛍️ Filtrer par magasins")
        magasins_selection = st.multiselect(
            label="Sélectionner un ou plusieurs magasins :",
            options=magasins_disponibles,
            default=magasins_disponibles,
            key="sidebar_magasins"
        )

    # Filtrage des données
    df_filtered = df[df['magasin'].isin(magasins_selection)]
    magasins_df_filtered = magasins_df[magasins_df['magasin'].isin(magasins_selection)]

    # Ajout des cercles de livraisons
    grouped = df_filtered.groupby(['magasin', 'code_postal']).agg({
        'latitude': 'mean',
        'longitude': 'mean',
        'adresse_livraison': 'count'
    }).reset_index().rename(columns={'adresse_livraison': 'nb_livraisons'})

    for _, row in grouped.iterrows():
        couleur = magasin_couleurs.get(row['magasin'], 'blue')
        folium.Circle(
            location=[row['latitude'], row['longitude']],
            radius=row['nb_livraisons'] * 200,
            color=couleur,
            fill=True,
            fill_color=couleur,
            fill_opacity=0.6,
            popup=folium.Popup(
                f"<b>Code postal:</b> {row['code_postal']}<br><b>Magasin:</b> {row['magasin']}<br><b>Livraisons:</b> {row['nb_livraisons']}",
                max_width=250
            )
        ).add_to(m)

        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=7,
            color=couleur,
            fill=True,
            fill_color=couleur,
            fill_opacity=1
        ).add_to(m)

    # Ajout des marqueurs magasins
    for _, row in magasins_df_filtered.iterrows():
        couleur = magasin_couleurs.get(row['magasin'], 'black')
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color=couleur, icon='plus', prefix='fa'),
            popup=f"<b>{row['magasin']}</b><br>{row['addresse_collecte']}"
        ).add_to(m)

    # ✅ Générer HTML complet APRÈS avoir ajouté tout à la carte
    map_html = m.get_root().render().encode("utf-8")
    cache_json = json.dumps(st.session_state.geocode_cache, indent=2)

    # Affichage carte dans l'app
    folium_static(m, width=1100, height=700)

    # Sidebar suite : boutons de téléchargement
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 💾 Télécharger")

        st.download_button(
            label="🌍 Carte HTML",
            data=map_html,
            file_name="carte_livraisons.html",
            mime="text/html"
        )
        st.download_button(
            label="📂 Cache JSON",
            data=cache_json,
            file_name="../geocode_cache.json",
            mime="application/json"
        )

        if st.button("Retour au chargement"):
            st.session_state.page = 'upload'
            st.rerun()





# ----------------------------------------------------------------------------------------------------------------------
#                                                      MAIN                                                            #
# ----------------------------------------------------------------------------------------------------------------------
if st.session_state.page == 'upload':
    page_upload()
elif st.session_state.page == 'map':
    page_map()
