import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import math
from pyproj import Transformer
import geopandas as gpd
from shapely.geometry import Polygon, Point
import json
import os

# 1. KONFIGURASI HALAMAN
st.set_page_config(page_title="PUO Geomatics Pro", layout="wide")

LOGO_URL = "https://th.bing.com/th/id/R.7845becf994d6c6a0b2afe8147ecbbf4?rik=l%2bMV7v5yBzHn5g&riu=http%3a%2f%2f1.bp.blogspot.com%2f-wQXM8Oe-ImA%2fTXrQ7Npc7uI%2fAAAAAAAAE34%2f2ref_vtbT5k%2fs1600%2fPoliteknik%252BUngku%252BOmar.png&ehk=IjCxLkjx3O7Lb2LSgWsvprPJ5Dvm%2fAHQVB35yucEm6Q%3d&risl=&pid=ImgRaw&r=0"

# 2. SISTEM LOGIN (3 USER - 1 PASSWORD)
def load_users():
    # Password yang sama untuk semua 3 user
    password_kongsi = "ADMIN1234" 
    return {
        "01DGU24F1059": password_kongsi,
        "01DGU24F1060": password_kongsi,
        "01DGU24F1061": password_kongsi
    }

if "user_db" not in st.session_state:
    st.session_state["user_db"] = load_users()
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = ""

def auth_interface():
    _, col2, _ = st.columns([1, 1.8, 1])
    with col2:
        st.markdown(f"<div style='text-align: center;'><br><img src='{LOGO_URL}' width='80'><h2>Sistem Geomatik PUO</h2></div>", unsafe_allow_html=True)
        tab1, _ = st.tabs(["🔒 Log Masuk", "📝 Daftar Akaun"])
        with tab1:
            with st.form("login_form"):
                u_id = st.text_input("ID Pengguna")
                u_pw = st.text_input("Kata Laluan", type="password")
                if st.form_submit_button("Masuk", use_container_width=True):
                    if u_id in st.session_state["user_db"] and st.session_state["user_db"][u_id] == u_pw:
                        st.session_state["logged_in"] = True
                        st.session_state["current_user"] = u_id
                        st.rerun()
                    else: st.error("ID atau Kata Laluan salah!")

if not st.session_state["logged_in"]:
    auth_interface(); st.stop()

# --- FUNGSI GEOMETRI ---
@st.cache_resource
def get_transformer(epsg):
    try: return Transformer.from_crs(f"epsg:{epsg}", "epsg:4326", always_xy=True)
    except: return None

def kira_bering(e1, n1, e2, n2):
    angle = math.degrees(math.atan2(e2 - e1, n2 - n1))
    if angle < 0: angle += 360
    return f"{int(angle)}°{int((angle%1)*60):02d}'{int(((angle%1)*60%1)*60):02d}\""

# 3. SIDEBAR
st.sidebar.markdown(f"**Sesi:** `{st.session_state['current_user']}`")
if st.sidebar.button("🚪 Log Keluar"):
    st.session_state["logged_in"] = False; st.rerun()

st.sidebar.divider()
st.sidebar.subheader("🎯 Penentukuran (Offset)")
off_n = st.sidebar.slider("Utara/Selatan (m)", -30.0, 30.0, 0.0)
off_e = st.sidebar.slider("Timur/Barat (m)", -30.0, 30.0, 0.0)

st.sidebar.divider()
epsg_input = st.sidebar.text_input("Kod EPSG", value="4390")
swap_en = st.sidebar.checkbox("Swap E/N", value=False)
show_labels = st.sidebar.checkbox("Label STN", value=True)
show_dist_brg = st.sidebar.checkbox("Bering & Jarak", value=True)

# 4. MAIN LOGIC
uploaded_file = st.sidebar.file_uploader("Muat naik CSV (STN, E, N)", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    tf = get_transformer(epsg_input)
    
    if tf:
        df_mod = df.copy()
        df_mod['E_adj'] = df_mod['E'] + off_e
        df_mod['N_adj'] = df_mod['N'] + off_n
        
        if swap_en:
            lons, lats = tf.transform(df_mod['N_adj'].values, df_mod['E_adj'].values)
        else:
            lons, lats = tf.transform(df_mod['E_adj'].values, df_mod['N_adj'].values)
        
        df['lat'], df['lon'] = lats, lons
        
        # --- PENGIRAAN LUAS & PERIMETER ---
        coords = list(zip(df['E'], df['N']))
        if len(coords) >= 3:
            poly_calc = Polygon(coords)
            area_m2 = poly_calc.area
            perimeter_m = poly_calc.length
        else:
            area_m2, perimeter_m = 0.0, 0.0

        berings, dists = [], []
        for i in range(len(df)):
            p1, p2 = df.iloc[i], df.iloc[(i+1)%len(df)]
            dist_val = math.sqrt((p2['E']-p1['E'])**2 + (p2['N']-p1['N'])**2)
            dists.append(round(dist_val, 3))
            berings.append(kira_bering(p1['E'], p1['N'], p2['E'], p2['N']))
        df['Jarak_Seterusnya'] = dists
        df['Bering_Seterusnya'] = berings

        # --- FUNGSI GEOJSON LENGKAP (STESEN, GARISAN, LOT) ---
        features = []
        for i in range(len(df)):
            # 1. Point Feature (Stesen)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [df.iloc[i]['lon'], df.iloc[i]['lat']]},
                "properties": {"Jenis": "Stesen", "STN": int(df.iloc[i]['STN']), "E": df.iloc[i]['E'], "N": df.iloc[i]['N']}
            })
            # 2. Line Feature (Sempadan)
            p1, p2 = df.iloc[i], df.iloc[(i+1)%len(df)]
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[p1['lon'], p1['lat']], [p2['lon'], p2['lat']]]},
                "properties": {"Jenis": "Sempadan", "Dari": int(p1['STN']), "Ke": int(p2['STN']), "Bering": berings[i], "Jarak": dists[i]}
            })
        # 3. Polygon Feature (Lot)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[ [df.iloc[i]['lon'], df.iloc[i]['lat']] for i in range(len(df)) ] + [[df.iloc[0]['lon'], df.iloc[0]['lat']]]]},
            "properties": {"Jenis": "Lot Utama", "Luas_m2": round(area_m2, 3), "Perimeter_m": round(perimeter_m, 3)}
        })
        geojson_str = json.dumps({"type": "FeatureCollection", "features": features})

        st.sidebar.divider()
        st.sidebar.subheader("📂 Eksport Data QGIS")
        st.sidebar.download_button(label="💾 Muat Turun GeoJSON Lengkap", data=geojson_str, file_name="lot_lengkap_puo.geojson", mime="application/geo+json")

        # 5. PETA
        m = folium.Map(location=[df['lat'].mean(), df['lon'].mean()], zoom_start=21, max_zoom=24)
        folium.TileLayer(tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", attr="Google Satellite", name="Google Satellite", max_zoom=24).add_to(m)
        
        # Polygon dengan Pop-up Luas
        folium.Polygon(
            df[['lat', 'lon']].values.tolist(), 
            color="#0000FF", fill=True, fill_opacity=0.1, weight=4,
            popup=f"<b>INFO LOT</b><br>Luas: {area_m2:.3f} m²<br>Perimeter: {perimeter_m:.3f} m"
        ).add_to(m)

        for i in range(len(df)):
            stn_info = df.iloc[i]
            popup_html = f"<b>STN: {int(stn_info['STN'])}</b><br>E: {stn_info['E']:.3f}<br>N: {stn_info['N']:.3f}"
            
            if show_labels:
                folium.Marker(
                    [stn_info['lat'], stn_info['lon']],
                    popup=folium.Popup(popup_html, max_width=150),
                    icon=folium.DivIcon(html=f"<div style='color: white; background: #FF0000; border-radius: 50%; width: 24px; height: 24px; text-align: center; font-weight: bold; line-height: 24px; border: 2px solid white;'>{int(stn_info['STN'])}</div>")
                ).add_to(m)
            
            if show_dist_brg:
                p1, p2 = df.iloc[i], df.iloc[(i+1)%len(df)]
                mid_lat, mid_lon = (p1['lat']+p2['lat'])/2, (p1['lon']+p2['lon'])/2
                folium.Marker([mid_lat, mid_lon],
                    icon=folium.DivIcon(html=f"<div style='font-size: 8pt; color: #FF0000; font-weight: bold; width: 140px; text-align: center; text-shadow: 1px 1px 0 #FFF; margin-top: -12px; margin-left: -70px;'>{berings[i]}<br><span style='color: black;'>{dists[i]}m</span></div>")
                ).add_to(m)

        st_folium(m, width="100%", height=600, returned_objects=[])
        
        # --- PAPARAN METRIK ---
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="📏 LUAS KESELURUHAN", value=f"{area_m2:.3f} m²")
            st.write(f"*(Persamaan: {(area_m2/4046.86):.4f} Ekar / {(area_m2/10000):.4f} Hektar)*")
        with col2:
            st.metric(label="🛣️ PERIMETER KESELURUHAN", value=f"{perimeter_m:.3f} m")

    else: st.error("Ralat EPSG.")
else: st.info("Sila muat naik fail CSV.")
