import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Wizz AYCF Planner", page_icon="✈️", layout="wide")
st.title("💖 All You Can Fly: Connection Finder")
st.caption("Finds Wizz Air flights. (Note: API is limited to 12-hour windows)")

# Sidebar for Key
RAPIDAPI_KEY = st.sidebar.text_input("Enter RapidAPI Key", type="password")
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"

# Constants
WIZZ_ICAO_CODES = ['WZZ', 'WUK', 'WMT', 'WAZ'] 

# --- API FUNCTION ---
def get_departures(airport_icao, start_time_str, end_time_str):
    if not RAPIDAPI_KEY:
        st.error("Please enter your RapidAPI Key in the sidebar.")
        return []

    # API Endpoint
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
    except requests.exceptions.HTTPError as e:
        if response.status_code == 400:
            st.error("API Error 400: Time window too long? (Must be <12 hours)")
        else:
            st.error(f"API Error: {e}")
        return []
    except Exception as e:
        st.error(f"Error: {e}")
        return []

def filter_wizz(flights):
    """Filters for Wizz Air flights only."""
    wizz_flights = []
    for f in flights:
        airline_name = f.get('airline', {}).get('name', 'Unknown')
        flight_num = f.get('number', 'Unknown')
        is_wizz = any(code in flight_num for code in WIZZ_ICAO_CODES) or "Wizz" in airline_name
        if is_wizz:
            wizz_flights.append(f)
    return wizz_flights

# --- MAIN APP LOGIC ---

col1, col2, col3 = st.columns(3)
with col1:
    origin_icao = st.text_input("Origin (ICAO)", value="EPWA", help="E.g. EPWA, EGGW").upper().strip()
with col2:
    travel_date = st.date_input("Travel Date", datetime.now() + timedelta(days=1))
with col3:
    # NEW: Select time window to avoid 400 Error
    time_of_day = st.selectbox("Time of Day", ["Morning (06:00 - 17:59)", "Evening (12:00 - 23:59)"])

if st.button("Find Flights"):
    if not RAPIDAPI_KEY:
        st.warning("⚠️ Paste your API Key in the sidebar!")
    else:
        date_str = travel_date.strftime("%Y-%m-%d")
        
        # LOGIC: Set the hours based on user choice
        if "Morning" in time_of_day:
            start_full = f"{date_str}T06:00"
            end_full = f"{date_str}T17:59"
        else:
            start_full = f"{date_str}T12:00"
            end_full = f"{date_str}T23:59"
        
        with st.spinner(f"Scanning {time_of_day}..."):
            raw_flights = get_departures(origin_icao, start_full, end_full)
            wizz_flights = filter_wizz(raw_flights)

        if not wizz_flights:
            st.warning(f"No Wizz Air flights found from {origin_icao} in the {time_of_day}.")
        else:
            st.success(f"Found {len(wizz_flights)} flights!")
            
            flight_list = []
            for f in wizz_flights:
                dest = f.get('movement', {}).get('airport', {}).get('name', 'Unknown')
                dep_time = f.get('movement', {}).get('scheduledTimeLocal', 'Unknown')
                flight_num = f.get('number', 'Unknown')
                
                flight_list.append({
                    "Flight": flight_num,
                    "Destination": dest,
                    "Departure": dep_time.replace("T", " ")[:16]
                })
            
            st.dataframe(pd.DataFrame(flight_list), use_container_width=True)
