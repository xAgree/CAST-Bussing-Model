# streamlit_app.py
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings
from io import BytesIO

# warnings.simplefilter(action="ignore", category=pd.errors.SettingWithCopyWarning)

# -----------------------------
# Constants
# -----------------------------
BUS_CAPACITY = 60
Arrival_TimeFrame = 45
Departure_TimeFrame = 45
Domestic_TimeFrame = 15
transit_time = 21.7
FLIGHT_LOAD_FACTOR = .86


Arrival_Rollover = pd.Timedelta(minutes=Arrival_TimeFrame)
Departure_Rollover = pd.Timedelta(minutes=Departure_TimeFrame)
Domestic_Rollover = pd.Timedelta(minutes=Domestic_TimeFrame)

st.title("Airport Bus Requirement Calculator")

uploaded_file = st.file_uploader("Upload Beontra Excel file", type=["xlsx"])

if uploaded_file:

    # -----------------------------
    # Load file
    # -----------------------------
    file = pd.read_excel(uploaded_file)
    file.columns = file.columns.str.strip()
    st.success("File uploaded successfully!")

    # -----------------------------
    # Extract Arrival & Departure
    # -----------------------------
    Arrival = file[[
        "Turnaround.Arrival Flight.Flight Number [String]",
        "Turnaround.Arrival Flight.Scheduled Block Time [Date/Time]",
        "Turnaround.Arrival Flight.Pax Count [Integer]",
        "Turnaround.Arrival Flight.Terminal [String]",
        "Turnaround.Arrival Flight.Stand.Stand Type [Enumeration:TStandHandlingType]"
    ]].rename(columns={
        "Turnaround.Arrival Flight.Flight Number [String]": "Flight_Number",
        "Turnaround.Arrival Flight.Scheduled Block Time [Date/Time]": "Scheduled_Time",
        "Turnaround.Arrival Flight.Pax Count [Integer]": "Pax_Count",
        "Turnaround.Arrival Flight.Terminal [String]": "Terminal",
        "Turnaround.Arrival Flight.Stand.Stand Type [Enumeration:TStandHandlingType]": "Stand Type"
    })

    Departure = file[[
        "Turnaround.Departure Flight.Flight Number [String]",
        "Turnaround.Departure Flight.Scheduled Block Time [Date/Time]",
        "Turnaround.Departure Flight.Pax Count [Integer]",
        "Turnaround.Departure Flight.Terminal [String]",
        "Turnaround.Departure Flight.Stand.Stand Type [Enumeration:TStandHandlingType]"
    ]].rename(columns={
        "Turnaround.Departure Flight.Flight Number [String]": "Flight_Number",
        "Turnaround.Departure Flight.Scheduled Block Time [Date/Time]": "Scheduled_Time",
        "Turnaround.Departure Flight.Pax Count [Integer]": "Pax_Count",
        "Turnaround.Departure Flight.Terminal [String]": "Terminal",
        "Turnaround.Departure Flight.Stand.Stand Type [Enumeration:TStandHandlingType]": "Stand Type"
    })

    # Datetime safety
    Arrival["Scheduled_Time"] = pd.to_datetime(Arrival["Scheduled_Time"], errors="coerce")
    Departure["Scheduled_Time"] = pd.to_datetime(Departure["Scheduled_Time"], errors="coerce")

    # -----------------------------
    # Filter Remote Stands
    # -----------------------------
    def filter_flights(df):
        return df[
            df["Stand Type"].str.contains("Remote", na=False) &
            (df["Pax_Count"] != 0)
        ].copy()

    Arrival = filter_flights(Arrival)
    Departure = filter_flights(Departure)

    # -----------------------------
    # Apply Load Factor
    # -----------------------------
    Arrival["Effective_Pax"] = np.ceil(Arrival["Pax_Count"] * FLIGHT_LOAD_FACTOR)
    Departure["Effective_Pax"] = np.ceil(Departure["Pax_Count"] * FLIGHT_LOAD_FACTOR)

    # -----------------------------
    # Gate Windows
    # -----------------------------
    # Arrival
    Arrival["Gate Start Time"] = Arrival["Scheduled_Time"]
    Arrival.loc[Arrival["Terminal"] == "International", "Gate End Time"] = \
        Arrival.loc[Arrival["Terminal"] == "International", "Gate Start Time"] + Arrival_Rollover
    Arrival.loc[Arrival["Terminal"] == "Domestic", "Gate End Time"] = \
        Arrival.loc[Arrival["Terminal"] == "Domestic", "Gate Start Time"] + Domestic_Rollover

    # Departure
    Departure["Gate End Time"] = Departure["Scheduled_Time"]
    Departure.loc[Departure["Terminal"] == "International", "Gate Start Time"] = \
        Departure.loc[Departure["Terminal"] == "International", "Gate End Time"] - Departure_Rollover
    Departure.loc[Departure["Terminal"] == "Domestic", "Gate Start Time"] = \
        Departure.loc[Departure["Terminal"] == "Domestic", "Gate End Time"] - Domestic_Rollover

    # -----------------------------
    # Build Time Index (5-min)
    # -----------------------------
    start_time = min(Arrival["Gate Start Time"].min(), Departure["Gate Start Time"].min()).floor("D")
    end_time = max(Arrival["Gate End Time"].max(), Departure["Gate End Time"].max()).replace(hour=23, minute=55)
    time_index = pd.date_range(start=start_time, end=end_time, freq="5min")

    # -----------------------------
    # Bus Calculation Function
    # -----------------------------
    def build_bus_counts(df, rollover):
        bus_counts = pd.Series(0, index=time_index)
        for _, row in df.iterrows():
            trips_needed = np.ceil(row["Effective_Pax"] / BUS_CAPACITY)
            max_trips = int(Arrival_TimeFrame // transit_time)
            buses_needed = int(np.ceil(trips_needed / max_trips))
            bus_counts.loc[row["Gate Start Time"]:row["Gate End Time"]] += buses_needed
        return bus_counts

    # -----------------------------
    # Arrival & Departure Bus Counts
    # -----------------------------
    Arrival_Int = Arrival[Arrival["Terminal"] == "International"]
    Arrival_Dom = Arrival[Arrival["Terminal"] == "Domestic"]
    Departure_Int = Departure[Departure["Terminal"] == "International"]
    Departure_Dom = Departure[Departure["Terminal"] == "Domestic"]

    A_counts = build_bus_counts(Arrival_Int, Arrival_Rollover) + build_bus_counts(Arrival_Dom, Domestic_Rollover)
    D_counts = build_bus_counts(Departure_Int, Departure_Rollover) + build_bus_counts(Departure_Dom, Domestic_Rollover)

    # -----------------------------
    # Combine
    # -----------------------------
    df_buses = pd.DataFrame({
        "Arrival": A_counts,
        "Departure": D_counts
    })
    df_buses["Total"] = df_buses.sum(axis=1)
    df_buses.index.name = "Time"

    # -----------------------------
    # Peak
    # -----------------------------
    st.subheader("Peak Bus Requirement (5-Minute Resolution)")
    st.write(f"Peak buses needed: {int(df_buses['Total'].max())}")

    # -----------------------------
    # Plot
    # -----------------------------
    st.subheader("Bus Utilization Over Time (5-Minute Resolution)")
    fig, ax = plt.subplots(figsize=(16, 6))

    df_buses[["Arrival", "Departure"]].plot(
        kind="bar",
        stacked=True,
        ax=ax,
        width=1
    )

    ax.set_xlabel("Time")
    ax.set_ylabel("Number of Buses")
    ax.set_title("Buses in Use (5-Minute Intervals)")
    ax.legend(loc="upper right")

    # X-ticks at midnight
    midnight_mask = df_buses.index.time == pd.to_datetime("00:00").time()
    tick_positions = np.where(midnight_mask)[0]
    tick_labels = df_buses.index[midnight_mask].strftime('%a %d-%m')
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right")

    plt.tight_layout()
    st.pyplot(fig)

    # -----------------------------
    # Export to Excel
    # -----------------------------
    export_df = df_buses.reset_index()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name="5min_Bus_Requirements")
    output.seek(0)

    st.download_button(
        label="Download 5-Minute Bus Requirements",
        data=output,
        file_name="Bus_Requirements_5min.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

