# Mapping Mangroves and Urban Development in the Sundarbans

import os
import geopandas as gpd
import rioxarray as rxr
import rasterio
from rasterio import features
from shapely.geometry import box, shape
import folium
import numpy as np
import requests, zipfile, io

# --- Step 1: Create data directory ---
data_dir = 'data'
os.makedirs(data_dir, exist_ok=True)

# --- Step 2: Define URLs ---
figshare_url = 'https://figshare.com/ndownloader/files/41881913'  # AnnualMangrove_2022.tif
ghsl_url = 'https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_LDS2020/GHS_BUILT_LDS2020_GLOBE_R2023A/GHS_BUILT_LDS2020_GLOBE_R2023A_3857_30ss/V1-0/GHS_BUILT_LDS2020_GLOBE_R2023A_3857_30ss_V1_0.zip'

mangrove_tif = os.path.join(data_dir, 'AnnualMangrove_2022.tif')
ghsl_zip = os.path.join(data_dir, 'GHSL_BUILT_2020.zip')
ghsl_tif = os.path.join(data_dir, 'GHS_BUILT_LDS2020_GLOBE_R2023A_3857_30ss_V1_0.tif')

# --- Step 3: Download files if not present ---
def download_file(url, dest):
    if not os.path.exists(dest):
        print(f"Downloading {url}...")
        r = requests.get(url)
        with open(dest, 'wb') as f:
            f.write(r.content)
        print(f"Saved to {dest}")

# Download mangrove GeoTIFF
download_file(figshare_url, mangrove_tif)

# Download GHSL zip and unzip
if not os.path.exists(ghsl_tif):
    print("Downloading GHSL built-up dataset...")
    r = requests.get(ghsl_url)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(data_dir)
    print("Unzipped GHSL data.")

# --- Step 4: Define Sundarbans bounding box (transboundary region) ---
bbox = box(87.8, 21.5, 90.0, 22.8)
aoi = gpd.GeoDataFrame({'geometry': [bbox]}, crs='EPSG:4326')

# --- Step 5: Load rasters and clip ---
print("Loading and clipping rasters...")
mangrove = rxr.open_rasterio(mangrove_tif, masked=True).rio.clip_box(*bbox.bounds)
builtup = rxr.open_rasterio(ghsl_tif, masked=True).rio.clip_box(*bbox.bounds)

# --- Step 6: Threshold and vectorize ---
print("Vectorizing rasters (this may take a minute)...")
mangrove_mask = (mangrove.squeeze() == 1)
builtup_mask = (builtup.squeeze() > 0)

mangrove_shapes = features.shapes(mangrove_mask.astype(np.uint8), transform=mangrove.rio.transform())
builtup_shapes = features.shapes(builtup_mask.astype(np.uint8), transform=builtup.rio.transform())

def shapes_to_gdf(shapes_gen, crs):
    geoms = []
    for s, v in shapes_gen:
        if v == 1:
            try:
                geoms.append(shape(s))
            except Exception:
                continue
    return gpd.GeoDataFrame(geometry=geoms, crs=crs)

gdf_mangrove = shapes_to_gdf(mangrove_shapes, mangrove.rio.crs)
gdf_builtup = shapes_to_gdf(builtup_shapes, builtup.rio.crs)

# --- Step 7: Simplify, reproject, and buffer ---
print("Preparing geometries for mapping...")
gdf_mangrove = gdf_mangrove.to_crs(epsg=4326)
gdf_builtup = gdf_builtup.to_crs(epsg=4326)

mangrove_buffer = gdf_mangrove.copy()
mangrove_buffer['geometry'] = mangrove_buffer.buffer(0.05)  # approx 5 km buffer

overlap = gpd.overlay(gdf_builtup, mangrove_buffer, how='intersection')

# --- Step 8: Create interactive Folium map ---
print("Creating Folium map...")
m = folium.Map(location=[22.0, 88.8], zoom_start=8, tiles='CartoDB positron')

folium.GeoJson(gdf_mangrove, name='Mangroves',
               style_function=lambda x: {'color':'green','fillOpacity':0.5}).add_to(m)
folium.GeoJson(gdf_builtup, name='Built-up areas',
               style_function=lambda x: {'color':'red','fillOpacity':0.4}).add_to(m)
folium.GeoJson(mangrove_buffer, name='5 km buffer',
               style_function=lambda x: {'color':'blue','fillOpacity':0.2}).add_to(m)
folium.GeoJson(overlap, name='Built-up within 5 km',
               style_function=lambda x: {'color':'purple','fillOpacity':0.6}).add_to(m)

folium.LayerControl().add_to(m)

m.save('sundarbans_mangrove_builtup_map.html')
print("Map saved as sundarbans_mangrove_builtup_map.html")

# --- Step 9: Compute area statistics ---
print("Computing area statistics...")
equal_area_crs = 'EPSG:6933'
gdf_mangrove_eq = gdf_mangrove.to_crs(equal_area_crs)
gdf_builtup_eq = gdf_builtup.to_crs(equal_area_crs)
overlap_eq = overlap.to_crs(equal_area_crs)

stats = {
    'Mangrove area (km²)': gdf_mangrove_eq.area.sum()/1e6,
    'Built-up area (km²)': gdf_builtup_eq.area.sum()/1e6,
    'Built-up within 5 km (km²)': overlap_eq.area.sum()/1e6
}

print("\nArea statistics (approx):")
for k, v in stats.items():
    print(f"  {k}: {v:.2f}")

print("\nAll done! Open 'sundarbans_mangrove_builtup_map.html' to view the interactive map.")
