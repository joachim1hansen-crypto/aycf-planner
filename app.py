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

# --- FUNCTIONS ---
def get_departures(airport_icao, start_time, end_time):
    if not RAPIDAPI_KEY:
        st.error("Please enter your RapidAPI Key in the sidebar.")
        return []

    # API Endpoint
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
        # We allow 404 (just means no flights found) but hide the key in other errors
        if "404" not in str(e):
            st.warning("No flight data received (Check Key or Limits).")
        return []

def process_flights(raw_flights):
    """Clean the data to fix 'Unknown' issues."""
    cleaned = []
    for f in raw_flights:
        # Check if Wizz Air
        flight_num = f.get('number', 'Unknown')
        airline = f.get('airline', {}).get('name', '')
        is_wizz = any(c in flight_num for c in WIZZ_CODES) or "Wizz" in airline
        
        if is_wizz:
            # FIX: Destination is in 'arrival', Departure time is in 'departure'
            dest_name = f.get('arrival', {}).get('airport', {}).get('name', 'Unknown')
            dest_icao = f.get('arrival', {}).get('airport', {}).get('icao', '')
            
            dep_time = f.get('departure', {}).get('scheduledTimeLocal', 'Unknown')
            arr_time = f.get('arrival', {}).get('scheduledTimeLocal', None)
            
            # Format times to look nice (remove the T)
            dep_clean = dep_time.replace("T", " ")[:16]
            
            cleaned.append({
                "Flight": flight_num,
                "To": dest_name,
                "To_ICAO": dest_icao, # Hidden column for logic
                "Depart": dep_clean,
                "Arrive (Est)": arr_time
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
        # Save results to session state so they stay on screen
        st.session_state['leg1_flights'] = flights
        st.success(f"Found {len(flights)} flights!")

# STEP 2: SHOW RESULTS & SELECT CONNECTION
if 'leg1_flights' in st.session_state:
    df = pd.DataFrame(st.session_state['leg1_flights'])
    
    # Show the table (excluding hidden ICAO column for valid display)
    st.dataframe(df[["Flight", "To", "Depart"]], use_container_width=True)
    
    st.divider()
    st.header("2️⃣ Step 2: Choose a connection")
    
    # Create a list of options for the dropdown
    options = [f"{r['Flight']} to {r['To']} (@ {r['Depart']})" for r in st.session_state['leg1_flights']]
    selected_option = st.selectbox("Select your first flight:", options)
    
    # Find the data for the selected flight
    index = options.index(selected_option)
    choice = st.session_state['leg1_flights'][index]
    
    if st.button(f"Find Connections from {choice['To']}"):
        hub_icao = choice['To_ICAO']
        
        # Calculate Layover Time (Arrival + 3 hours)
        if choice['Arrive (Est)']:
            arrival_dt = datetime.strptime(choice['Arrive (Est)'][:16], "%Y-%m-%dT%H:%M")
        else:
            # Fallback: Assume 2 hour flight if data missing
            dep_dt = datetime.strptime(choice['Depart'], "%Y-%m-%d %H:%M")
            arrival_dt = dep_dt + timedelta(hours=2)
            
        search_start = arrival_dt + timedelta(hours=3)
        search_end = search_start + timedelta(hours=10) # Look ahead 10 hours
        
        # Format for API
        s_str = search_start.strftime("%Y-%m-%dT%H:%M")
        e_str = search_end.strftime("%Y-%m-%dT%H:%M")
        
        st.info(f"You land at {arrival_dt.strftime('%H:%M')}. Searching for flights after {search_start.strftime('%H:%M')}...")
        
        with st.spinner(f"Checking {hub_icao}..."):
            raw_conn = get_departures(hub_icao, s_str, e_str)
            conn_flights = process_flights(raw_conn)
            
        if conn_flights:
            st.balloons()
            st.write(f"### 🎉 Valid Connections found from {choice['To']}:")
            st.dataframe(pd.DataFrame(conn_flights)[["Flight", "To", "Depart"]], use_container_width=True)
        else:
            st.error(f"No Wizz Air connections found from {choice['To']} in the next 10 hours.")
