import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Wizz AYCF Planner", page_icon="✈️", layout="wide")
st.title("💖 All You Can Fly: Connection Finder")

# Sidebar - We added .strip() to fix the crash!
key_input = st.sidebar.text_input("Enter RapidAPI Key", type="password")
RAPIDAPI_KEY = key_input.strip() if key_input else None
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
WIZZ_CODES = ['WZZ', 'WUK', 'WMT', 'WAZ', 'W6'] 

# --- HELPER: ROBUST TIME FINDER ---
def get_time_string(f, key_name='scheduledTimeLocal'):
    """Safely extracts time from movement or departure."""
    # Check movement first (most accurate)
    t = f.get('movement', {}).get(key_name)
    if t: return t
    # Check departure/arrival object
    t = f.get('departure', {}).get(key_name)
    if t: return t
    t = f.get('arrival', {}).get(key_name)
    if t: return t
    return None

def parse_time(time_str):
    """Converts API string to datetime object safely."""
    if not time_str: return None
    try:
        # Standard format: 2026-01-07T14:30+01:00
        # We take the first 16 chars: 2026-01-07T14:30
        clean_str = time_str[:16]
        return datetime.strptime(clean_str, "%Y-%m-%dT%H:%M")
    except:
        return None

# --- API FUNCTION ---
def get_departures(airport_icao, start_time, end_time):
    if not RAPIDAPI_KEY:
        st.error("Please enter your RapidAPI Key in the sidebar.")
        return []

    url = f"https://aerodatabox.p.rapidapi.com/flights/airports/icao/{airport_icao}/{start_time}/{end_time}"
    
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
        return response.json().get('departures', [])
    except Exception as e:
        # Show the error only if it's NOT a 404 (which just means no flights)
        if "404" not in str(e):
            st.error(f"API Connection Error: {e}")
        return []

def process_flights(raw_flights):
    cleaned = []
    for f in raw_flights:
        flight_num = f.get('number', 'Unknown')
        airline = f.get('airline', {}).get('name', '')
        
        # Loose filter: Check for Wizz code OR "Wizz" in name
        is_wizz = any(c in flight_num for c in WIZZ_CODES) or "Wizz" in airline
        
        if is_wizz:
            dest_name = f.get('arrival', {}).get('airport', {}).get('name', 'Unknown')
            dest_icao = f.get('arrival', {}).get('airport', {}).get('icao', '')
            
            # Try to get Scheduled Time, then Estimated, then Actual
            raw_time = get_time_string(f, 'scheduledTimeLocal')
            if not raw_time:
                 raw_time = get_time_string(f, 'estimatedTimeLocal')
            
            # Parse it
            dep_dt = parse_time(raw_time)
            
            if dep_dt:
                formatted_dep = dep_dt.strftime("%H:%M")
                arr_dt = dep_dt + timedelta(hours=2, minutes=30) # Est landing
            else:
                formatted_dep = "Unknown"
                arr_dt = None

            # Add to list
            cleaned.append({
                "Flight": flight_num,
                "To": dest_name,
                "To_ICAO": dest_icao,
                "Depart": formatted_dep,
                "Est_Arrival_Obj": arr_dt,
                "Raw_Data": f 
            })
    return cleaned

# --- APP INTERFACE ---

st.header("1️⃣ Step 1: Where are you starting?")
col1, col2, col3 = st.columns(3)
with col1:
    origin = st.text_input("Origin (ICAO)", value="EPWA").upper().strip()
with col2:
    date = st.date_input("Travel Date", datetime.now() + timedelta(days=1))
with col3:
    time_window = st.selectbox("Time Window", ["Morning (06:00-14:00)", "Afternoon (14:00-22:00)"])

if st.button("Find Departures", type="primary"):
    date_str = date.strftime("%Y-%m-%d")
    if "Morning" in time_window:
        start, end = f"{date_str}T06:00", f"{date_str}T13:59"
    else:
        start, end = f"{date_str}T14:00", f"{date_str}T21:59"
    
    with st.spinner("Scanning..."):
        raw = get_departures(origin, start, end)
        flights = process_flights(raw)
        
    if not flights:
        st.warning("No Wizz Air flights found (or API returned empty data).")
    else:
        st.session_state['leg1_flights'] = flights
        st.success(f"Found {len(flights)} flights!")
        
        # DEBUG EXPANDER (Check this if time is Unknown!)
        with st.expander("🛠️ Debug Data (Click if issues)"):
            st.write("First flight raw data:")
            st.json(flights[0]['Raw_Data'])

# DISPLAY RESULTS
if 'leg1_flights' in st.session_state:
    df = pd.DataFrame(st.session_state['leg1_flights'])
    st.dataframe(df[["Flight", "To", "Depart"]], use_container_width=True)
    
    st.divider()
    st.header("2️⃣ Step 2: Connections")
    
    options = [f"{r['Flight']} to {r['To']} (@ {r['Depart']})" for r in st.session_state['leg1_flights']]
    selected_option = st.selectbox("Select Flight:", options)
    
    if st.button("Find Connections ➡️"):
        index = options.index(selected_option)
        choice = st.session_state['leg1_flights'][index]
        
        if not choice['Est_Arrival_Obj']:
             st.error("Cannot plan: Time is Unknown. Check Debug Data.")
        elif not choice['To_ICAO']:
             st.error("Cannot plan: Destination ICAO code missing.")
        else:
            hub_icao = choice['To_ICAO']
            arrival_dt = choice['Est_Arrival_Obj']
            
            min_connect = arrival_dt + timedelta(hours=2)
            search_end = min_connect + timedelta(hours=10)
            
            s_str = min_connect.strftime("%Y-%m-%dT%H:%M")
            e_str = search_end.strftime("%Y-%m-%dT%H:%M")
            
            st.info(f"Checking flights from {choice['To']} after {min_connect.strftime('%H:%M')}...")
            
            raw_conn = get_departures(hub_icao, s_str, e_str)
            conn_flights = process_flights(raw_conn)
            
            if conn_flights:
                st.balloons()
                st.write(f"### 🎉 Valid Connections from {choice['To']}:")
                st.table(pd.DataFrame(conn_flights)[["Flight", "To", "Depart"]])
            else:
                st.warning("No connections found in the next 10 hours.")
