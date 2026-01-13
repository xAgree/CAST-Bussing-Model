# streamlit_app.py

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings

# Ignore SettingWithCopyWarning
warnings.simplefilter(action="ignore", category=pd.errors.SettingWithCopyWarning)

# Constants
BUS_CAPACITY = 60
Arrival_TimeFrame = 45
Departure_TimeFrame = 45
Domestic_TimeFrame = 15
transit_time = 21.7

Arrival_Rollover = pd.Timedelta(minutes=Arrival_TimeFrame)
Departure_Rollover = pd.Timedelta(minutes=Departure_TimeFrame)
Domestic_Rollover = pd.Timedelta(minutes=Domestic_TimeFrame)

st.title("Airport Bus Requirement Calculator")

uploaded_file = st.file_uploader("Upload Beontra Excel file", type=["xlsx"])
if uploaded_file:

    # Load file
    file = pd.read_excel(uploaded_file)
    file.columns = file.columns.str.strip()

    st.success("File uploaded successfully!")

    # --- Prepare Arrival & Departure ---
    Arrival = file[
        [
            "Turnaround.Arrival Flight.Flight Number [String]",
            "Turnaround.Arrival Flight.Aircraft Type [String]",
            "Turnaround.Arrival Flight.Airline Code [String]",
            "Turnaround.Arrival Flight.Flight Type [String]",
            "Turnaround.Arrival Flight.Flight Direction [Enumeration:TFlightDirection]",
            "Turnaround.Arrival Flight.Scheduled Block Time [Date/Time]",
            "Turnaround.Arrival Flight.Stand Name [String]",
            "Turnaround.Arrival Flight.Pax Count [Integer]",
            "Turnaround.Arrival Flight.Airport Code [String]",
            "Turnaround.Arrival Flight.Terminal [String]",
            "Turnaround.Arrival Flight.Stand.Stand Type [Enumeration:TStandHandlingType]"
        ]
    ].rename(columns={
        "Turnaround.Arrival Flight.Flight Number [String]": "Flight_Number",
        "Turnaround.Arrival Flight.Aircraft Type [String]": "Aircraft_Type",
        "Turnaround.Arrival Flight.Airline Code [String]": "Airline_Code",
        "Turnaround.Arrival Flight.Flight Type [String]": "Flight_Type",
        "Turnaround.Arrival Flight.Flight Direction [Enumeration:TFlightDirection]": "Flight_Direction",
        "Turnaround.Arrival Flight.Scheduled Block Time [Date/Time]": "Scheduled_Time",
        "Turnaround.Arrival Flight.Stand Name [String]": "Stand",
        "Turnaround.Arrival Flight.Pax Count [Integer]": "Pax_Count",
        "Turnaround.Arrival Flight.Airport Code [String]": "Airport_Code",
        "Turnaround.Arrival Flight.Terminal [String]": "Terminal",
        "Turnaround.Arrival Flight.Stand.Stand Type [Enumeration:TStandHandlingType]": "Stand Type"
    })

    # Turnaround Departure
    Departure = file[
        [
            "Turnaround.Departure Flight.Flight Number [String]",
            "Turnaround.Departure Flight.Aircraft Type [String]",
            "Turnaround.Departure Flight.Airline Code [String]",
            "Turnaround.Departure Flight.Flight Type [String]",
            "Turnaround.Departure Flight.Flight Direction [Enumeration:TFlightDirection]",
            "Turnaround.Departure Flight.Scheduled Block Time [Date/Time]",
            "Turnaround.Departure Flight.Stand Name [String]",
            "Turnaround.Departure Flight.Pax Count [Integer]",
            "Turnaround.Departure Flight.Airport Code [String]",
            "Turnaround.Departure Flight.Terminal [String]",
            "Turnaround.Departure Flight.Stand.Stand Type [Enumeration:TStandHandlingType]"
        ]
    ].rename(columns={
        "Turnaround.Departure Flight.Flight Number [String]": "Flight_Number",
        "Turnaround.Departure Flight.Aircraft Type [String]": "Aircraft_Type",
        "Turnaround.Departure Flight.Airline Code [String]": "Airline_Code",
        "Turnaround.Departure Flight.Flight Type [String]": "Flight_Type",
        "Turnaround.Departure Flight.Flight Direction [Enumeration:TFlightDirection]": "Flight_Direction",
        "Turnaround.Departure Flight.Scheduled Block Time [Date/Time]": "Scheduled_Time",
        "Turnaround.Departure Flight.Stand Name [String]": "Stand",
        "Turnaround.Departure Flight.Pax Count [Integer]": "Pax_Count",
        "Turnaround.Departure Flight.Airport Code [String]": "Airport_Code",
        "Turnaround.Departure Flight.Terminal [String]": "Terminal",
        "Turnaround.Departure Flight.Stand.Stand Type [Enumeration:TStandHandlingType]": "Stand Type"
    })
    # Datetime safety
    Arrival["Scheduled_Time"] = pd.to_datetime(Arrival["Scheduled_Time"], errors="coerce")
    Departure["Scheduled_Time"] = pd.to_datetime(Departure["Scheduled_Time"], errors="coerce")

    # Filter busops
    def filter_flights(df):
        return df[
            df["Stand Type"].str.contains("Remote", na=False) &
            (
                df["Terminal"].str.contains("International|Domestic", regex=True, na=False) |
                df["Terminal"].isna() |
                (df["Terminal"].str.strip() == "")
            ) &
            (df["Pax_Count"] != 0)
        ].copy()

    Arrival = filter_flights(Arrival)
    Departure = filter_flights(Departure)

    # --- Gate times ---
    # Arrival
    Arrival["Gate Start Time"] = Arrival["Scheduled_Time"]
    Arrival.loc[Arrival["Terminal"] == "International", "Gate End Time"] = Arrival.loc[Arrival["Terminal"] == "International", "Gate Start Time"] + Arrival_Rollover
    Arrival.loc[Arrival["Terminal"] == "Domestic", "Gate End Time"] = Arrival.loc[Arrival["Terminal"] == "Domestic", "Gate Start Time"] + Domestic_Rollover

    # Departure
    Departure["Gate End Time"] = Departure["Scheduled_Time"]
    Departure.loc[Departure["Terminal"] == "International", "Gate Start Time"] = Departure.loc[Departure["Terminal"] == "International", "Gate End Time"] - Arrival_Rollover
    Departure.loc[Departure["Terminal"] == "Domestic", "Gate Start Time"] = Departure.loc[Departure["Terminal"] == "Domestic", "Gate End Time"] - Domestic_Rollover

    # --- Bus calculation function ---
    def build_bus_counts(df, rollover, time_index):
        bus_counts = pd.Series(0, index=time_index)
        for _, row in df.iterrows():
            start = row["Gate Start Time"]
            delta = rollover
            buses = int(row["buses_needed_per_flight"])
            if row["Trips_Needed"] % 2 == 1:
                bus_counts.loc[start:start + delta] += buses - 1
                bus_counts.loc[start:start + (delta / 2)] += 1
            else:
                bus_counts.loc[start:start + delta] += buses
        return bus_counts

    # --- Arrival ---
    Arrival["Trips_Needed"] = np.ceil(Arrival["Pax_Count"] / BUS_CAPACITY)
    max_trips_A = Arrival_TimeFrame // transit_time
    Arrival["buses_needed_per_flight"] = np.ceil(Arrival["Trips_Needed"] / max_trips_A)

    Arrival_Int = Arrival[Arrival["Terminal"].str.contains("International", na=False)]
    Arrival_Dom = Arrival[Arrival["Terminal"].str.contains("Domestic", na=False)]

    start_time = min(Arrival["Gate Start Time"].min(), Departure["Scheduled_Time"].min()).floor("D")
    end_time = max(Arrival["Gate End Time"].max(), Departure["Scheduled_Time"].max()).replace(hour=23, minute=55)
    time_index = pd.date_range(start=start_time, end=end_time, freq="5min")

    A_bus_counts_int = build_bus_counts(Arrival_Int, Arrival_Rollover, time_index)
    A_bus_counts_dom = build_bus_counts(Arrival_Dom, Arrival_Rollover, time_index)

    # --- Departure ---
    Departure["Trips_Needed"] = np.ceil(Departure["Pax_Count"] / BUS_CAPACITY)
    max_trips_D = Departure_TimeFrame // transit_time
    Departure["buses_needed_per_flight"] = np.ceil(Departure["Trips_Needed"] / max_trips_D)

    Departure_Int = Departure[Departure["Terminal"].str.contains("International", na=False)]
    Departure_Dom = Departure[Departure["Terminal"].str.contains("Domestic", na=False)]

    D_bus_counts_int = build_bus_counts(Departure_Int, Departure_Rollover, time_index)
    D_bus_counts_dom = build_bus_counts(Departure_Dom, Departure_Rollover, time_index)

   # --- Combine bus counts ---
    df_buses = pd.DataFrame({
        "Arrival": A_bus_counts_int + A_bus_counts_dom,
        "Departure": D_bus_counts_int + D_bus_counts_dom,
        "Domestic": A_bus_counts_dom + D_bus_counts_dom
    })
    df_buses.index.name = "Time"

    st.subheader("Peak Bus Requirement")
    st.write(f"Peak buses needed: {int(df_buses.sum(axis=1).max())}")

    # --- Plot ---
    st.subheader("Bus Utilization Over Time")
    fig, ax = plt.subplots(figsize=(16, 6))
    df_buses_plot = df_buses.resample("15min").max()  # peak per 15-min interval
    x_labels = df_buses_plot.index.strftime('%a %d-%m %H:%M')
    df_buses_plot.plot(kind="bar", stacked=True, ax=ax, width=1)
    ax.set_xlabel("Time")
    ax.set_ylabel("Bus Count")
    ax.set_title("Number of Buses in Use (International + Domestic)")
    ax.legend(loc="upper right")
    tick_positions = range(0, len(df_buses_plot), max(1, len(df_buses_plot)//9))
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(x_labels[tick_positions], rotation=45, ha="right")
    plt.tight_layout()
    st.pyplot(fig)

    # --- Download ---
    from io import BytesIO
    if uploaded_file:
        df_buses_reset = df_buses.reset_index().rename(columns={"index": "Time"})

        # Prepare Excel data in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_buses_reset.to_excel(writer, index=False, sheet_name="Bus_Requirements")
        output.seek(0)

        # Streamlit download button
        st.download_button(
            label="Download Time Series as Excel",
            data=output,
            file_name="Time_Series.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
