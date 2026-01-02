#!/usr/bin/env python
# coding: utf-8

# In[3]:


import streamlit as st
import pandas as pd
import numpy as np
import time
from math import radians, sin, cos, atan2, sqrt
import pydeck as pdk
from geopy.geocoders import Nominatim

st.set_page_config(page_title="Localizador de Endereços", layout="wide")

# -------------------------------
# Centro de Distribuição
# -------------------------------
st.sidebar.header("📍 Centro de distribuição")
cd_endereco = st.sidebar.text_input(
    "Endereço do Centro de Distribuição",
    "Travessa Francisco Marrocos Portela, Alto Alegre I, Maracanaú - CE, Brasil, 61922-120"
)

# Função para geocodificação via Nominatim (OpenStreetMap)
def geocode_osm(endereco):
    geolocator = Nominatim(user_agent="localizador_enderecos")
    try:
        location = geolocator.geocode(endereco)
        if location:
            return location.latitude, location.longitude
        else:
            return None, None
    except Exception as e:
        st.write(f"Erro na geocodificação: {e}")
        return None, None

cd_lat, cd_lon = None, None
lat, lon = geocode_osm(cd_endereco)
if lat and lon:
    cd_lat, cd_lon = lat, lon
    st.sidebar.success(f"CD localizado: {cd_lat:.6f}, {cd_lon:.6f}")
else:
    st.sidebar.error("Não foi possível geocodificar o endereço do CD.")

# -------------------------------
# Upload de clientes
# -------------------------------
st.sidebar.header("📂 Importar clientes (.xlsx)")
arquivo = st.sidebar.file_uploader("Selecione um arquivo Excel", type=["xlsx"])

st.title("📍 Localizador de Endereços")
st.write("Carregue um Excel com os clientes e endereços para geocodificar e traçar rotas a partir do Centro de Distribuição.")

@st.cache_data
def geocode_dataframe_osm(df, endereco_col="Endereco"):
    results = []
    geolocator = Nominatim(user_agent="localizador_enderecos")
    for _, row in df.iterrows():
        if "Latitude" in df.columns and "Longitude" in df.columns and not pd.isna(row.get("Latitude")) and not pd.isna(row.get("Longitude")):
            results.append((row["Latitude"], row["Longitude"]))
            continue

        addr = str(row.get(endereco_col, "")).strip()
        if not addr:
            results.append((np.nan, np.nan))
            continue

        try:
            location = geolocator.geocode(addr)
            if location:
                results.append((location.latitude, location.longitude))
            else:
                results.append((np.nan, np.nan))
        except Exception as e:
            st.write(f"Erro na geocodificação: {e}")
            results.append((np.nan, np.nan))
        time.sleep(1)  # respeitar limite de 1 requisição/segundo
    return results

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(p1)*cos(p2)*sin(dlambda/2)**2
    return 2*R*atan2(sqrt(a), sqrt(1-a))

def nearest_neighbor_route(start_lat, start_lon, points):
    unvisited = points.copy()
    route = [{"lat": start_lat, "lon": start_lon, "name": "Centro de Distribuição"}]
    current_lat, current_lon = start_lat, start_lon

    while unvisited:
        distances = [
            (idx, haversine(current_lat, current_lon, p["lat"], p["lon"]))
            for idx, p in enumerate(unvisited)
        ]
        distances = [d for d in distances if not np.isnan(d[1])]
        if not distances:
            break
        next_idx = min(distances, key=lambda x: x[1])[0]
        next_point = unvisited.pop(next_idx)
        route.append(next_point)
        current_lat, current_lon = next_point["lat"], next_point["lon"]

    return route

if arquivo:
    df = pd.read_excel(arquivo)
    df.columns = [c.strip() for c in df.columns]

    if "Cliente_ID" not in df.columns or "Endereco" not in df.columns:
        st.error("Arquivo inválido. É necessário conter as colunas 'Cliente_ID' e 'Endereco'.")
        st.stop()

    st.success(f"{len(df)} clientes carregados.")

    with st.spinner("Geocodificando endereços com OpenStreetMap..."):
        coords = geocode_dataframe_osm(df, endereco_col="Endereco")
    df["Latitude"], df["Longitude"] = zip(*coords)

    total = len(df)
    validos = df["Latitude"].notna().sum()
    st.info(f"Coordenadas obtidas para {validos}/{total} clientes.")

    # -------------------------------
    # ✏️ Inserção manual de coordenadas
    # -------------------------------
    df_faltantes = df[df["Latitude"].isna() | df["Longitude"].isna()]
    if not df_faltantes.empty:
        st.subheader("✏️ Inserir coordenadas manualmente")
        for i, row in df_faltantes.iterrows():
            st.markdown(f"**{row['Cliente_ID']} - {row['Cliente']}**")
            lat = st.number_input(f"Latitude para {row['Cliente_ID']}", key=f"lat_{i}", value=0.0)
            lon = st.number_input(f"Longitude para {row['Cliente_ID']}", key=f"lon_{i}", value=0.0)
            if st.button(f"Salvar coordenadas de {row['Cliente_ID']}", key=f"btn_{i}"):
                df.at[i, "Latitude"] = lat
                df.at[i, "Longitude"] = lon
                st.success(f"Coordenadas salvas para {row['Cliente_ID']}")

    # -------------------------------
    # Download dos resultados
    # -------------------------------
    st.subheader("📥 Baixar resultado geocodificado")
    st.dataframe(df.head(10))
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV geocodificado", data=csv_bytes, file_name="clientes_geocodificados.csv", mime="text/csv")

    # -------------------------------
    # Mapa e rota
    # -------------------------------
    if cd_lat is not None and cd_lon is not None:
        st.subheader("🗺️ Mapa de clientes e rota")
        pontos = [
            {"lat": r["Latitude"], "lon": r["Longitude"], "name": f"{r['Cliente_ID']} - {r['Cliente']}"}
            for _, r in df.iterrows() if not pd.isna(r["Latitude"]) and not pd.isna(r["Longitude"])
        ]

        rota = nearest_neighbor_route(cd_lat, cd_lon, pontos)
        path_data = [{
            "path": [[p["lon"], p["lat"]] for p in rota],
            "name": "Rota CD -> Clientes"
        }]

        scatter = pdk.Layer(
            "ScatterplotLayer",
            data=pontos + [{"lat": cd_lat, "lon": cd_lon, "name": "Centro de Distribuição"}],
            get_position='[lon, lat]',
            get_fill_color='[255, 99, 71]',
            get_radius=60,
            pickable=True
        )
        path_layer = pdk.Layer(
            "PathLayer",
            data=path_data,
            get_path="path",
            get_width=4,
            get_color=[0, 128, 255],
            width_min_pixels=2
        )
        view_state = pdk.ViewState(latitude=cd_lat, longitude=cd_lon, zoom=11)
        st.pydeck_chart(pdk.Deck(layers=[scatter, path_layer], initial_view_state=view_state, tooltip={"text": "{name}"}))
    else:
        st.warning("Defina um endereço válido para o Centro de Distribuição.")
else:
    st.warning("Importe um arquivo Excel (.xlsx) com as colunas 'Cliente_ID', 'Cliente' e 'Endereco'.")

# -------------------------------
# Teste manual de geocodificação
# -------------------------------
st.subheader("🔍 Teste de geocodificação manual")
endereco_teste = st.text_input("Digite um endereço para testar", "Rua São Paulo II Etapa, Maracanaú - CE, Brasil")
if st.button("Testar geocodificação"):
    lat, lon = geocode_osm(endereco_teste)
    st.write(f"Latitude: {lat}, Longitude: {lon}")


# In[ ]:




