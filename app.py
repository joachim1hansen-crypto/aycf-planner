import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Wizz AYCF Planner", page_icon="✈️", layout="wide")
st.title("💖 All You Can Fly: Connection Finder")

# Sidebar
RAPIDAPI_KEY = st.sidebar.text_input("Enter RapidAPI Key", type="password")
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
WIZZ_CODES = ['WZZ', 'WUK', 'WMT', 'WAZ', 'W6'] 

# --- HELPER: FIND TIME ---
def find_flight_time(f):
    """
    Tries to find the time in 4 different places in the API response.
    Returns the time string or None.
    """
    # 1. Try Movement Local Time (Most common)
    t = f.get('movement', {}).get('scheduledTimeLocal')
    if t: return t
    
    # 2. Try Movement UTC Time
    t = f.get('movement', {}).get('scheduledTimeUtc')
    if t: return t
    
    # 3. Try Departure Local Time (Backup)
    t = f.get('departure', {}).get('scheduledTimeLocal')
    if t: return t
    
    # 4. Try Departure UTC Time (Last resort)
    t = f.get('departure', {}).get('scheduledTimeUtc')
    if t: return t
    
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
            st.warning("No flight data received (Check Key or Limits).")
        return []

def process_flights(raw_flights):
    """Clean the data and fix 'Unknown' times."""
    cleaned = []
    for f in raw_flights:
        flight_num = f.get('number', 'Unknown')
        airline = f.get('airline', {}).get('name', '')
        
        # Check if Wizz Air
        is_wizz = any(c in flight_num for c in WIZZ_CODES) or "Wizz" in airline
        
        if is_wizz:
            # FIX: Use the smart time finder
            raw_time = find_flight_time(f)
            
            dest_name = f.get('arrival', {}).get('airport', {}).get('name', 'Unknown')
            dest_icao = f.get('arrival', {}).get('airport', {}).get('icao', '')
            
            if raw_time:
                # Format time nicely (Remove T)
                # Example: 2026-01-07T06:00 -> 06:00
                dep_dt = datetime.fromisoformat(raw_time[:19])
                formatted_dep = dep_dt.strftime("%H:%M")
                
                # Estimate Arrival (Departure + 2.5 hours)
                # We use this to calculate the connection
                arr_dt = dep_dt + timedelta(hours=2, minutes=30)
            else:
                formatted_dep = "Unknown"
                arr_dt = None

            # Only add flights where we found a time (otherwise we can't plan connections)
            if formatted_dep != "Unknown":
                cleaned.append({
                    "Flight": flight_num,
                    "To": dest_name,
                    "To_ICAO": dest_icao,
                    "Depart": formatted_dep,
                    "Est_Arrival_Obj": arr_dt 
                })
    return cleaned

# --- APP LOGIC ---

# STEP 1: FIND FIRST FLIGHT
st.header("1️⃣ Step 1: Where are you starting?")
col1, col2, col3 = st.columns(3)
with col1:
    origin = st.text_input("Origin Airport (ICAO)", value="EPWA").upper().strip()
with col2:
    date = st.date_input("Travel Date", datetime.now() + timedelta(days=1))
with col3:
    time_window = st.selectbox("Time of Day", ["Morning (06:00-14:00)", "Afternoon (14:00-22:00)"])

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
        st.warning("No Wizz Air flights found (or missing time data).")
    else:
        st.session_state['leg1_flights'] = flights
        st.success(f"Found {len(flights)} flights!")

# STEP 2: SHOW RESULTS & CONNECT
if 'leg1_flights' in st.session_state:
    df = pd.DataFrame(st.session_state['leg1_flights'])
    
    st.divider()
    st.header("2️⃣ Step 2: Select a flight to Connect")
    
    # DROP DOWN SELECTION
    options = [f"{r['Flight']} to {r['To']} (@ {r['Depart']})" for r in st.session_state['leg1_flights']]
    selected_option = st.selectbox("Choose your flight:", options)
    
    if st.button("Find Connections ➡️"):
        index = options.index(selected_option)
        choice = st.session_state['leg1_flights'][index]
        
        hub_icao = choice['To_ICAO']
        arrival_dt = choice['Est_Arrival_Obj']
        
        if not hub_icao:
            st.error("Cannot find connections: Destination airport has no code.")
        else:
            # 2 HOUR LAYOVER LOGIC
            min_connect_time = arrival_dt + timedelta(hours=2)
            search_end = min_connect_time + timedelta(hours=10) 
            
            s_str = min_connect_time.strftime("%Y-%m-%dT%H:%M")
            e_str = search_end.strftime("%Y-%m-%dT%H:%M")
            
            st.markdown(f"""
            **Trip Plan:**
            1. Land in **{choice['To']}** around {arrival_dt.strftime('%H:%M')}
            2. Minimum Layover: **2 Hours**
            3. Searching for flights after: **{min_connect_time.strftime('%H:%M')}**
            """)
            
            with st.spinner(f"Checking flights from {choice['To']}..."):
                raw_conn = get_departures(hub_icao, s_str, e_str)
                conn_flights = process_flights(raw_conn)
            
            if conn_flights:
                st.balloons()
                st.write(f"### 🎉 Valid Connections from {choice['To']}:")
                st.table(pd.DataFrame(conn_flights)[["Flight", "To", "Depart"]])
            else:
                st.warning(f"No Wizz Air flights found leaving {choice['To']} between {min_connect_time.strftime('%H:%M')} and {search_end.strftime('%H:%M')}.")
