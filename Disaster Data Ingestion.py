import pandas as pd
import requests
import networkx as nx
import folium
from datetime import datetime, timedelta
from geopy.distance import geodesic

# --------------------------------------------
# 1. Load Supply Chain Nodes from CSV
# --------------------------------------------
nodes_df = pd.read_csv("supply_nodes.csv")
G = nx.DiGraph()

# Add nodes to graph with lat/lon
for _, row in nodes_df.iterrows():
    node_id = row["id"]
    G.add_node(node_id, name=row["name"], lat=row["lat"], lon=row["lon"])

# --------------------------------------------
# 2. Auto-connect nodes based on proximity
# --------------------------------------------
for id1 in G.nodes:
    for id2 in G.nodes:
        if id1 == id2:
            continue
        lat1, lon1 = G.nodes[id1]['lat'], G.nodes[id1]['lon']
        lat2, lon2 = G.nodes[id2]['lat'], G.nodes[id2]['lon']
        distance_km = geodesic((lat1, lon1), (lat2, lon2)).km
        if distance_km <= 600:  # connect if within 600 km
            G.add_edge(id1, id2, weight=round(distance_km, 1))

# --------------------------------------------
# 3. Fetch real-time earthquake data
# --------------------------------------------
def fetch_earthquake_data(min_magnitude=4.5, hours=24):
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query"
        f"?format=geojson&starttime={start_time.isoformat()}&endtime={end_time.isoformat()}"
        f"&minmagnitude={min_magnitude}"
    )
    response = requests.get(url)
    data = response.json()
    earthquakes = [
        {
            "place": f["properties"]["place"],
            "time": datetime.utcfromtimestamp(f["properties"]["time"] / 1000),
            "magnitude": f["properties"]["mag"],
            "longitude": f["geometry"]["coordinates"][0],
            "latitude": f["geometry"]["coordinates"][1],
        }
        for f in data["features"]
    ]
    return pd.DataFrame(earthquakes)

df = fetch_earthquake_data()
print("\n🛰️  Recent Earthquakes:\n", df[["place", "magnitude", "latitude", "longitude"]].head())

# --------------------------------------------
# 4. Check for risky supply chain nodes
# --------------------------------------------
def is_node_near_disaster(node_lat, node_lon, quake_lat, quake_lon, threshold_km=200):
    return geodesic((node_lat, node_lon), (quake_lat, quake_lon)).km <= threshold_km

risky_nodes = set()
for _, quake in df.iterrows():
    for node in G.nodes:
        lat, lon = G.nodes[node]['lat'], G.nodes[node]['lon']
        if is_node_near_disaster(lat, lon, quake['latitude'], quake['longitude']):
            risky_nodes.add(node)

print("\n⚠️  Risky Nodes:", risky_nodes)

# --------------------------------------------
# 5. Safe Routing (Dijkstra with risk filtering)
# --------------------------------------------
source = "A"
destination = "E"
path_nodes = []

try:
    if not risky_nodes:
        path_nodes = nx.dijkstra_path(G, source, destination)
        print("\n✅ Shortest Path:", " → ".join(path_nodes))
    else:
        safe_nodes = [n for n in G.nodes if n not in risky_nodes]
        safe_G = G.subgraph(safe_nodes)
        path_nodes = nx.dijkstra_path(safe_G, source, destination)
        print("\n🚨 Rerouted Safe Path:", " → ".join(path_nodes))
except nx.NetworkXNoPath:
    print("\n❌ No safe path available.")
    path_nodes = []

# --------------------------------------------
# 6. Visualize on Folium Map
# --------------------------------------------
m = folium.Map(location=[30.0, -82.0], zoom_start=6)

# Supply nodes (red = risky, blue = safe)
for node in G.nodes:
    lat = G.nodes[node]['lat']
    lon = G.nodes[node]['lon']
    name = G.nodes[node]['name']
    color = "red" if node in risky_nodes else "blue"
    folium.CircleMarker(
        location=(lat, lon),
        radius=7,
        color=color,
        fill=True,
        fill_opacity=0.9,
        popup=f"{name} ({node})"
    ).add_to(m)

# Earthquakes
for _, quake in df.iterrows():
    folium.Marker(
        location=[quake['latitude'], quake['longitude']],
        icon=folium.Icon(color='orange', icon='info-sign'),
        popup=f"{quake['place']} (M{quake['magnitude']})"
    ).add_to(m)

# Route
if path_nodes:
    path_coords = [(G.nodes[n]['lat'], G.nodes[n]['lon']) for n in path_nodes]
    folium.PolyLine(locations=path_coords, color='green', weight=4).add_to(m)

# Save map
m.save("disaster_supply_chain_map.html")
print("\n🗺️  Map saved as 'disaster_supply_chain_map.html'")
