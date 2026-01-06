import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Wizz AYCF Planner", page_icon="✈️", layout="wide")
st.title("💖 All You Can Fly: Connection Finder")
st.caption("Finds Wizz Air flights within the 72h booking window.")

# Sidebar for Key
RAPIDAPI_KEY = st.sidebar.text_input("Enter RapidAPI Key", type="password")
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"

# Constants
WIZZ_ICAO_CODES = ['WZZ', 'WUK', 'WMT', 'WAZ'] 
MIN_LAYOVER_HOURS = 3

# --- API FUNCTION ---
def get_departures(airport_icao, start_time_str, end_time_str):
    """
    Fetches departures for a specific time range.
    Expected format for times: YYYY-MM-DDTHH:MM (e.g., 2026-01-06T08:00)
    """
    if not RAPIDAPI_KEY:
        st.error("Please enter your RapidAPI Key in the sidebar.")
        return []

    # API Endpoint for specific airport departures
    url = f"https://aerodatabox.p.rapidapi.com/flights/airports/icao/{airport_icao}/{start_time_str}/{end_time_str}"
    
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
        response.raise_for_status()
        data = response.json()
        return data.get('departures', [])
    except Exception as e:
        # Only show error if it's not a simple 'no flights found' empty list
        if "404" not in str(e): 
            st.error(f"API Error: {e}")
        return []

def filter_wizz(flights):
    """Filters for Wizz Air flights only."""
    wizz_flights = []
    for f in flights:
        airline_name = f.get('airline', {}).get('name', 'Unknown')
        flight_num = f.get('number', 'Unknown')
        
        # Check if Wizz is in the name or the flight number matches Wizz codes
        is_wizz = any(code in flight_num for code in WIZZ_ICAO_CODES) or "Wizz" in airline_name
        
        if is_wizz:
            wizz_flights.append(f)
    return wizz_flights

# --- MAIN APP LOGIC ---

col1, col2 = st.columns(2)
with col1:
    origin_icao = st.text_input("Origin Airport (ICAO Code)", value="EPWA", help="Use 4-letter codes: EPWA (Warsaw), EGGW (Luton), LROP (Bucharest)").upper().strip()
with col2:
    travel_date = st.date_input("Travel Date", datetime.now())

if st.button("Find First Leg (Departures)"):
    if not RAPIDAPI_KEY:
        st.warning("⚠️ Don't forget to paste your API Key in the sidebar on the left!")
    else:
        # FIX: We now define a precise 12-hour window (Morning to Night)
        # The API limits data size, so we look from 06:00 AM to 06:00 PM for the best results
        date_str = travel_date.strftime("%Y-%m-%d")
        start_full = f"{date_str}T06:00"
        end_full = f"{date_str}T23:59"
        
        with st.spinner(f"Scanning flights from {origin_icao} ({start_full} to {end_full})..."):
            # Call the API with the CORRECT time format now
            raw_flights = get_departures(origin_icao, start_full, end_full)
            wizz_flights = filter_wizz(raw_flights)

        if not wizz_flights:
            st.warning(f"No Wizz Air flights found from {origin_icao} between 06:00 and 23:59 on this date.")
        else:
            st.success(f"Found {len(wizz_flights)} Wizz Air departures!")
            
            # Display Data
            flight_list = []
            for f in wizz_flights:
                dest = f.get('movement', {}).get('airport', {}).get('name', 'Unknown')
                dep_time = f.get('movement', {}).get('scheduledTimeLocal', 'Unknown')
                flight_num = f.get('number', 'Unknown')
                
                flight_list.append({
                    "Flight": flight_num,
                    "Destination": dest,
                    "Departure Time": dep_time.replace("T", " ")[:16]
                })
            
            st.dataframe(pd.DataFrame(flight_list))
