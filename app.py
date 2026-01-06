import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURATION ---
# Sign up at https://rapidapi.com/aedbx-aedbx/api/aerodatabox to get this key
# The free tier allows ~200 requests/month.
RAPIDAPI_KEY = st.sidebar.text_input("416956a8bamsh507d8f32cf06bafp1d6cb6jsnb33935a8efc1",)
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"

# Wizz Air Logic
WIZZ_ICAO_CODES = ['WZZ', 'WUK', 'WMT', 'WAZ'] # Hungary, UK, Malta, Abu Dhabi
AYCF_WINDOW_HOURS = 72
MIN_LAYOVER_HOURS = 3

st.set_page_config(page_title="Wizz AYCF Planner", page_icon="✈️", layout="wide")
st.title("💖 All You Can Fly: Connection Finder")
st.caption("Finds flights within the 72h booking window with valid layovers.")

# --- HELPER FUNCTIONS ---
def get_departures(airport_icao, date_from, date_to):
    """Fetches departures from a specific airport for a time window."""
    if not RAPIDAPI_KEY:
        st.error("Please enter your RapidAPI Key in the sidebar.")
        return []

    # --- THE FIX IS HERE ---
    # We changed the URL to include '/airports/icao/{airport_icao}'
    url = f"https://aerodatabox.p.rapidapi.com/flights/airports/icao/{airport_icao}/{date_from}/{date_to}"
    
    querystring = {
        "withLeg": "true",
        "direction": "Departure",
        "withCancelled": "false",
        "withCodeshared": "true",
        "withCargo": "false",
        "withPrivate": "false"
    }
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status() # Checks if the API returned an error (like 404)
        data = response.json()
        
        # The API returns 'departures' list directly
        return data.get('departures', [])
    except Exception as e:
        st.error(f"API Error: {e}")
        return []


def filter_wizz(flights):
    """Filters a list of flights for only Wizz Air aircraft."""
    wizz_flights = []
    for f in flights:
        # Check airline code
        airline = f.get('airline', {}).get('name', 'Unknown')
        flight_num = f.get('number', 'Unknown')
        
        # Some data providers put the ICAO code in the number (e.g., WZZ123)
        is_wizz = any(code in flight_num for code in WIZZ_ICAO_CODES) or "Wizz" in airline
        
        if is_wizz:
            wizz_flights.append(f)
    return wizz_flights

# --- APP INTERFACE ---

# 1. INPUTS
col1, col2 = st.columns(2)
with col1:
    origin_icao = st.text_input("Origin Airport (ICAO Code)", value="EGGW", help="E.g., EGGW for London Luton, LROP for Bucharest").upper()
with col2:
    travel_date = st.date_input("Travel Date", datetime.now())

if st.button("Find First Leg (Departures)"):
    # Define the 12-hour window for the selected day
    start_time = travel_date.strftime("%Y-%m-%d") + "T06:00"
    end_time = travel_date.strftime("%Y-%m-%d") + "T23:59"
    
    with st.spinner(f"Scanning departures from {origin_icao}..."):
        raw_flights = get_departures(origin_icao, travel_date.strftime("%Y-%m-%d"), travel_date.strftime("%Y-%m-%d"))
        wizz_flights = filter_wizz(raw_flights)

    if not wizz_flights:
        st.warning("No Wizz Air flights found for this date/time window.")
    else:
        st.success(f"Found {len(wizz_flights)} Wizz Air departures!")
        
        # Prepare data for display
        flight_options = []
        for f in wizz_flights:
            dest = f.get('movement', {}).get('airport', {}).get('name', 'Unknown')
            dest_icao = f.get('movement', {}).get('airport', {}).get('icao', '')
            dep_time_str = f.get('movement', {}).get('scheduledTimeLocal', '')
            arr_time_str = f.get('movement', {}).get('scheduledTimeLocal', '') # Note: Arrival time usually in 'arrival' object, simplified here
            
            # Extract actual arrival time from the 'arrival' section if available, otherwise estimate
            # (AeroDataBox usually provides arrival details in the departure object if 'withLeg' is true)
            # For simplicity in this demo, we store the full object to process later
            
            flight_options.append({
                "Flight": f.get('number'),
                "Destination": dest,
                "Dest ICAO": dest_icao,
                "Departure": dep_time_str,
                "Raw Data": f
            })
        
        df = pd.DataFrame(flight_options)
        st.dataframe(df[["Flight", "Destination", "Dest ICAO", "Departure"]])

        # 2. SELECT LEG 2
        st.divider()
        st.subheader("Plan Leg 2 (The Connection)")
        selected_index = st.selectbox("Select your first flight to find connections:", df.index, format_func=lambda x: f"{df.iloc[x]['Flight']} to {df.iloc[x]['Destination']}")
        
        if st.button("Find Connections"):
            selected_flight = df.iloc[selected_index]
            hub_icao = selected_flight["Dest ICAO"]
            
            # Calculate Arrival Time (Estimated)
            # In a real app, you'd parse the 'arrival' time from the API. 
            # We will assume a 3 hour flight time for estimation if data missing.
            dep_time = datetime.fromisoformat(selected_flight["Departure"][:16])
            est_arrival = dep_time + timedelta(hours=3) 
            min_connect_time = est_arrival + timedelta(hours=MIN_LAYOVER_HOURS)
            
            st.info(f"You land in {selected_flight['Destination']} around {est_arrival.strftime('%H:%M')}. Searching for flights after {min_connect_time.strftime('%H:%M')}...")
            
            # Search departures from the HUB
            # Note: We might need to check the NEXT day if the layover pushes past midnight
            search_date_str = min_connect_time.strftime("%Y-%m-%d")
            
            with st.spinner(f"Checking flights from {hub_icao}..."):
                hub_flights = get_departures(hub_icao, search_date_str, search_date_str)
                hub_wizz = filter_wizz(hub_flights)
            
            valid_connections = []
            for f in hub_wizz:
                hub_dep_str = f.get('movement', {}).get('scheduledTimeLocal', '')
                if hub_dep_str:
                    hub_dep_time = datetime.fromisoformat(hub_dep_str[:16])
                    
                    if hub_dep_time > min_connect_time:
                         valid_connections.append({
                            "Connect Flight": f.get('number'),
                            "Final Dest": f.get('movement', {}).get('airport', {}).get('name'),
                            "Depart Hub": hub_dep_str
                        })
            
            if valid_connections:
                st.balloons()
                st.write(f"### Valid Connections found from {selected_flight['Destination']}:")
                st.table(pd.DataFrame(valid_connections))
            else:
                st.error("No connecting Wizz Air flights found with >3h layover today.")

