# streamlit_app.py

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings
from io import BytesIO

warnings.simplefilter(action="ignore", category=pd.errors.SettingWithCopyWarning)

# -----------------------
# Constants
# -----------------------
BUS_CAPACITY = 60
Arrival_TimeFrame = 45
Departure_TimeFrame = 45
Domestic_TimeFrame = 15
transit_time = 21.7
FLIGHT_LOAD_FACTOR = 0.86

Arrival_Rollover   = pd.Timedelta(minutes=Arrival_TimeFrame - 15)
Departure_Rollover = pd.Timedelta(minutes=Departure_TimeFrame - 15)
Domestic_Rollover  = pd.Timedelta(minutes=Domestic_TimeFrame)

st.title("Airport Bus Requirement Calculator")

uploaded_file = st.file_uploader("Upload Beontra Excel file", type=["xlsx"])

if uploaded_file:

    file = pd.read_excel(uploaded_file)
    file.columns = file.columns.str.strip()

    st.success("File uploaded successfully!")

    # -----------------------
    # Prepare Data
    # -----------------------

    def prepare(df, prefix):
        return df[
            [
                f"{prefix}.Flight Number [String]",
                f"{prefix}.Aircraft Type [String]",
                f"{prefix}.Airline Code [String]",
                f"{prefix}.Flight Type [String]",
                f"{prefix}.Flight Direction [Enumeration:TFlightDirection]",
                f"{prefix}.Scheduled Block Time [Date/Time]",
                f"{prefix}.Stand Name [String]",
                f"{prefix}.Pax Count [Integer]",
                f"{prefix}.Airport Code [String]",
                f"{prefix}.Terminal [String]",
                f"{prefix}.Stand.Stand Type [Enumeration:TStandHandlingType]"
            ]
        ].rename(columns={
            f"{prefix}.Flight Number [String]": "Flight_Number",
            f"{prefix}.Aircraft Type [String]": "Aircraft_Type",
            f"{prefix}.Airline Code [String]": "Airline_Code",
            f"{prefix}.Flight Type [String]": "Flight_Type",
            f"{prefix}.Flight Direction [Enumeration:TFlightDirection]": "Flight_Direction",
            f"{prefix}.Scheduled Block Time [Date/Time]": "Scheduled_Time",
            f"{prefix}.Stand Name [String]": "Stand",
            f"{prefix}.Pax Count [Integer]": "Pax_Count",
            f"{prefix}.Airport Code [String]": "Airport_Code",
            f"{prefix}.Terminal [String]": "Terminal",
            f"{prefix}.Stand.Stand Type [Enumeration:TStandHandlingType]": "Stand Type"
        })

    Arrival = prepare(file, "Turnaround.Arrival Flight")
    Departure = prepare(file, "Turnaround.Departure Flight")

    Arrival["Scheduled_Time"] = pd.to_datetime(Arrival["Scheduled_Time"], errors="coerce")
    Departure["Scheduled_Time"] = pd.to_datetime(Departure["Scheduled_Time"], errors="coerce")

    def filter_flights(df):
        return df[
            df["Stand Type"].str.contains("Remote", na=False) &
            df["Terminal"].str.contains("International|Domestic", regex=True, na=False) &
            (df["Pax_Count"] != 0)
        ].copy()

    Arrival = filter_flights(Arrival)
    Departure = filter_flights(Departure)

    # -----------------------
    # Load Factor
    # -----------------------

    Arrival["Effective_Pax"] = np.ceil(Arrival["Pax_Count"] * FLIGHT_LOAD_FACTOR)
    Departure["Effective_Pax"] = np.ceil(Departure["Pax_Count"] * FLIGHT_LOAD_FACTOR)

    # -----------------------
    # Gate Times
    # -----------------------

    # Arrival
    Arrival["Gate Start Time"] = Arrival["Scheduled_Time"]
    Arrival.loc[Arrival["Terminal"] == "International", "Gate End Time"] = (
        Arrival["Gate Start Time"] + Arrival_Rollover
    )
    Arrival.loc[Arrival["Terminal"] == "Domestic", "Gate End Time"] = (
        Arrival["Gate Start Time"] + Domestic_Rollover
    )

    # Departure
    Departure["Gate End Time"] = Departure["Scheduled_Time"]
    Departure.loc[Departure["Terminal"] == "International", "Gate Start Time"] = (
        Departure["Gate End Time"] - Departure_Rollover
    )
    Departure.loc[Departure["Terminal"] == "Domestic", "Gate Start Time"] = (
        Departure["Gate End Time"] - Domestic_Rollover
    )

    # -----------------------
    # Bus Calculation
    # -----------------------

    def build_bus_counts(df, time_index):
        bus_counts = pd.Series(0, index=time_index)
        for _, row in df.iterrows():
            start = row["Gate Start Time"]
            end   = row["Gate End Time"]
            buses = int(row["buses_needed_per_flight"])
            bus_counts.loc[start:end] += buses
        return bus_counts

    # Trips & buses
    Arrival["Trips_Needed"] = np.ceil(Arrival["Effective_Pax"] / BUS_CAPACITY)
    max_trips_A = Arrival_TimeFrame // transit_time
    Arrival["buses_needed_per_flight"] = np.ceil(Arrival["Trips_Needed"] / max_trips_A)

    Departure["Trips_Needed"] = np.ceil(Departure["Effective_Pax"] / BUS_CAPACITY)
    max_trips_D = Departure_TimeFrame // transit_time
    Departure["buses_needed_per_flight"] = np.ceil(Departure["Trips_Needed"] / max_trips_D)

    # -----------------------
    # 5-Minute Time Index
    # -----------------------

    start_time = min(
        Arrival["Gate Start Time"].min(),
        Departure["Gate Start Time"].min()
    ).floor("D")

    end_time = max(
        Arrival["Gate End Time"].max(),
        Departure["Gate End Time"].max()
    ).replace(hour=23, minute=55)

    time_index = pd.date_range(start=start_time, end=end_time, freq="5min")

    # Build 5-min series
    A_total = build_bus_counts(Arrival, time_index)
    D_total = build_bus_counts(Departure, time_index)

    df_buses = pd.DataFrame({
        "Arrival": A_total,
        "Departure": D_total
    })

    df_buses.index.name = "Time"

    # -----------------------
    # Peak (5-min exact)
    # -----------------------

    peak_value = int(df_buses.sum(axis=1).max())

    st.subheader("Peak Bus Requirement")
    st.write(f"Peak buses needed (5-min peak): {peak_value}")

    # -----------------------
    # Plot (5-min)
    # -----------------------

    st.subheader("Bus Utilization Over Time (5-Min Intervals)")

    fig, ax = plt.subplots(figsize=(16, 6))

    df_buses.plot(
        kind="bar",
        stacked=True,
        ax=ax,
        width=1
    )

    ax.set_xlabel("Time")
    ax.set_ylabel("Bus Count")
    ax.set_title("Number of Buses in Use (Arrival + Departure)")
    ax.legend(loc="upper right")

    # Reduce x tick density for readability
    ax.set_xticks(range(0, len(df_buses.index), 12))
    ax.set_xticklabels(
        df_buses.index[::12].strftime('%d-%m %H:%M'),
        rotation=45,
        ha="right"
    )

    plt.tight_layout()
    st.pyplot(fig)

    # -----------------------
    # Download (5-min data)
    # -----------------------

    output = BytesIO()
    df_buses.reset_index().to_excel(output, index=False, sheet_name="Bus_Requirements")
    output.seek(0)

    st.download_button(
        label="Download 5-Min Time Series as Excel",
        data=output,
        file_name="Time_Series_5min.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
