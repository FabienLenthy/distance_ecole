import streamlit as st
import pandas as pd
import requests
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Calcul Distances Ecoles", layout="wide")
st.title("🚗 Calculateur de distance pour mutations")

# --- FONCTIONS CACHÉES POUR OPTIMISER LES PERFORMANCES ---
@st.cache_data
def charger_donnees(uploaded_file):
    """Charge le fichier CSV ou Excel de l'utilisateur."""
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

def obtenir_coordonnees(adresse, tentative=1):
    """Géocode l'adresse saisie par l'utilisateur."""
    geolocator = Nominatim(user_agent="mon_app_streamit_mutations")
    try:
        location = geolocator.geocode(adresse, timeout=10)
        if location:
            return location.latitude, location.longitude
        return None, None
    except GeocoderTimedOut:
        if tentative <= 3:
            time.sleep(2)
            return obtenir_coordonnees(adresse, tentative + 1)
        return None, None

def calculer_distance_osrm(lat1, lon1, lat2, lon2):
    """Calcule la distance en voiture via l'API publique OSRM."""
    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
        return None
        
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("code") == "Ok":
            return round(data["routes"][0]["distance"] / 1000.0, 2)
    except:
        pass
    return None

def extraire_lat_lon(coords_str):
    """Extrait la latitude et longitude depuis une chaîne '(lat, lon)' ou 'lat, lon'."""
    try:
        # Nettoyage de la chaîne et séparation
        coords_str = str(coords_str).replace('(', '').replace(')', '').strip()
        parts = coords_str.split(',')
        return float(parts[0].strip()), float(parts[1].strip())
    except:
        return None, None

# --- INTERFACE UTILISATEUR ---

# 1. Chargement du fichier
st.sidebar.header("1. Charger les données")
fichier_upload = st.sidebar.file_uploader("Importez votre table avec coordonnées (CSV ou Excel)", type=['csv', 'xlsx', 'xls'])

if fichier_upload is not None:
    df = charger_donnees(fichier_upload)
    
    # 2. Options de filtrage et saisie
    st.sidebar.header("2. Vos critères")
    adresse_utilisateur = st.sidebar.text_input("Votre adresse complète :", placeholder="ex: 12 avenue Jean-Baptiste Corot, Roissy-en-Brie")
    
    # Création d'une liste multisélection (plus pratique qu'une longue liste de checkboxes)
    types_postes_dispos = df['Nature'].dropna().unique().tolist()
    natures_selectionnees = st.sidebar.multiselect(
        "Sélectionnez le ou les types de poste :",
        options=types_postes_dispos,
        default=types_postes_dispos # Par défaut, tout est sélectionné
    )
    
    # 3. Lancement du calcul
    if st.sidebar.button("🚀 Lancer le calcul", type="primary"):
        if not adresse_utilisateur:
            st.error("Veuillez saisir une adresse.")
        elif not natures_selectionnees:
            st.warning("Veuillez sélectionner au moins un type de poste.")
        else:
            with st.spinner("Recherche de votre adresse..."):
                lat_domicile, lon_domicile = obtenir_coordonnees(adresse_utilisateur)
            
            if lat_domicile is None:
                st.error("❌ Adresse introuvable. Veuillez vérifier votre saisie.")
            else:
                st.success(f"📍 Adresse trouvée ! Coordonnées : {lat_domicile}, {lon_domicile}")
                
                # --- TRAITEMENT DES DONNÉES ---
                # A. Filtrage
                df_filtre = df[df['Nature'].isin(natures_selectionnees)].copy()
                
                # B. Dédoublonnage
                df_unique = df_filtre.drop_duplicates(subset=['Commune', 'Etablissement', 'Coords']).copy()
                
                # C. Calcul des distances pour les écoles uniques
                distances = []
                barre_progression = st.progress(0)
                status_text = st.empty()
                
                total_ecoles = len(df_unique)
                
                for i, row in enumerate(df_unique.itertuples()):
                    status_text.text(f"Calcul de l'itinéraire {i+1} sur {total_ecoles}...")
                    lat_ecole, lon_ecole = extraire_lat_lon(row.Coords)
                    
                    dist = calculer_distance_osrm(lat_domicile, lon_domicile, lat_ecole, lon_ecole)
                    distances.append(dist)
                    
                    # Pause pour ne pas saturer l'API gratuite OSRM
                    time.sleep(0.5)
                    barre_progression.progress((i + 1) / total_ecoles)
                
                status_text.text("Calcul terminé !")
                df_unique['Distance (km)'] = distances
                
                # D. Jointure avec la table filtrée d'origine
                colonnes_jointure = ['Commune', 'Etablissement', 'Coords']
                df_final = pd.merge(df_filtre, df_unique[colonnes_jointure + ['Distance (km)']], 
                                    on=colonnes_jointure, 
                                    how='left')
                
                # E. Tri par distance (ascendant)
                df_final = df_final.sort_values(by='Distance (km)')
                
                # --- AFFICHAGE ET TÉLÉCHARGEMENT ---
                st.subheader(f"Résultats : {len(df_final)} postes correspondants")
                st.dataframe(df_final, use_container_width=True)
                
                csv = df_final.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Télécharger le tableau (CSV)",
                    data=csv,
                    file_name='postes_triees_par_distance.csv',
                    mime='text/csv',
                )
else:
    st.info("👈 Veuillez commencer par charger votre fichier dans le menu de gauche.")