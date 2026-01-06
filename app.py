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
            # FIX 1: Destination is in 'arrival'
            dest_name = f.get('arrival', {}).get('airport', {}).get('name', 'Unknown')
            dest_icao = f.get('arrival', {}).get('airport', {}).get('icao', '')
            
            # FIX 2: Time is usually in 'movement' for this API
            # We try 'movement' first, then 'departure' as a backup
            dep_time = f.get('movement', {}).get('scheduledTimeLocal', None)
            if not dep_time:
                dep_time = f.get('departure', {}).get('scheduledTimeLocal', 'Unknown')
            
            # Estimate Arrival (Departure + 2.5 hours approx if data missing)
            # This helps us calculate the layover safely
            if dep_time and dep_time != 'Unknown':
                dep_dt = datetime.fromisoformat(dep_time[:19]) # Remove timezone for math
                arr_dt = dep_dt + timedelta(hours=2, minutes=30)
                formatted_dep = dep_dt.strftime("%H:%M")
            else:
                arr_dt = None
                formatted_dep = "Unknown"

            cleaned.append({
                "Flight": flight_num,
                "To": dest_name,
                "To_ICAO": dest_icao, # Hidden column for logic
                "Depart": formatted_dep,
                "Est_Arrival_Obj": arr_dt # Hidden object for math
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
        st.warning("No Wizz Air flights found.")
    else:
        st.session_state['leg1_flights'] = flights
        st.success(f"Found {len(flights)} flights!")

# STEP 2: SHOW RESULTS & CONNECT
if 'leg1_flights' in st.session_state:
    df = pd.DataFrame(st.session_state['leg1_flights'])
    
    st.divider()
    st.header("2️⃣ Step 2: Select a flight to Connect")
    st.info("Select a flight from the list below to find connections (2h+ layover).")
    
    # DROP DOWN SELECTION (Most reliable for phone)
    options = [f"{r['Flight']} to {r['To']} (@ {r['Depart']})" for r in st.session_state['leg1_flights']]
    selected_option = st.selectbox("Choose your flight:", options)
    
    # Process Selection
    if st.button("Find Connections ➡️"):
        index = options.index(selected_option)
        choice = st.session_state['leg1_flights'][index]
        
        hub_icao = choice['To_ICAO']
        arrival_dt = choice['Est_Arrival_Obj']
        
        if not hub_icao:
            st.error("Cannot find connections: Destination airport has no code.")
        elif not arrival_dt:
             st.error("Cannot calculate layover: Departure time unknown.")
        else:
            # 2 HOUR LAYOVER LOGIC
            min_connect_time = arrival_dt + timedelta(hours=2)
            search_end = min_connect_time + timedelta(hours=10) # Look ahead 10 hours
            
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
                # Show simple table
                st.table(pd.DataFrame(conn_flights)[["Flight", "To", "Depart"]])
            else:
                st.warning(f"No Wizz Air flights found leaving {choice['To']} between {min_connect_time.strftime('%H:%M')} and {search_end.strftime('%H:%M')}.")
