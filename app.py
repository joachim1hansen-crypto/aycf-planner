import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Wizz AYCF Planner", page_icon="✈️", layout="wide")
st.title("💖 All You Can Fly: Connection Finder")

# Sidebar
key_input = st.sidebar.text_input("Enter RapidAPI Key", type="password")
RAPIDAPI_KEY = key_input.strip() if key_input else None
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
WIZZ_CODES = ['WZZ', 'WUK', 'WMT', 'WAZ', 'W6'] 

# --- HELPER: FIX FOR YOUR SCREENSHOT ---
def get_time_string(f):
    """
    Extracts time from the specific structure shown in your screenshot:
    departure -> scheduledTime -> local
    """
    # 1. Try Departure (Deep Nested) - This matches your screenshot!
    t = f.get('departure', {}).get('scheduledTime', {}).get('local')
    if t: return t
    
    # 2. Try Movement (Deep Nested)
    t = f.get('movement', {}).get('scheduledTime', {}).get('local')
    if t: return t

    # 3. Old Backup (Flat structure)
    t = f.get('movement', {}).get('scheduledTimeLocal')
    if t: return t
    
    return None

def parse_time(time_str):
    """
    Handles the date format with a SPACE instead of T.
    Example input: "2026-01-07 06:00+01:00"
    """
    if not time_str: return None
    try:
        # Take first 16 chars: "2026-01-07 06:00"
        clean_str = time_str[:16]
        # Replace 'T' with space just in case, to handle both formats
        clean_str = clean_str.replace("T", " ")
        return datetime.strptime(clean_str, "%Y-%m-%d %H:%M")
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
        if "404" not in str(e):
            st.error(f"API Error: {e}")
        return []

def process_flights(raw_flights):
    cleaned = []
    for f in raw_flights:
        flight_num = f.get('number', 'Unknown')
        airline = f.get('airline', {}).get('name', '')
        
        # Filter for Wizz Air
        is_wizz = any(c in flight_num for c in WIZZ_CODES) or "Wizz" in airline
        
        if is_wizz:
            dest_name = f.get('arrival', {}).get('airport', {}).get('name', 'Unknown')
            dest_icao = f.get('arrival', {}).get('airport', {}).get('icao', '')
            
            # Find Time using the new function
            raw_time = get_time_string(f)
            dep_dt = parse_time(raw_time)
            
            if dep_dt:
                formatted_dep = dep_dt.strftime("%H:%M")
                arr_dt = dep_dt + timedelta(hours=2, minutes=30)
            else:
                formatted_dep = "Unknown"
                arr_dt = None

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
        st.warning("No Wizz Air flights found.")
    else:
        st.session_state['leg1_flights'] = flights
        st.success(f"Found {len(flights)} flights!")

# STEP 2: DISPLAY & CONNECT
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
        
        if choice['Depart'] == "Unknown":
             st.error("Cannot plan: Time is Unknown.")
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
                st.dataframe(pd.DataFrame(conn_flights)[["Flight", "To", "Depart"]], use_container_width=True)
            else:
                st.warning("No connections found in the next 10 hours.")
