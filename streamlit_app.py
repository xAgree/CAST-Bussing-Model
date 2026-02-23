# streamlit_app.py

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings
from io import BytesIO

warnings.simplefilter(action="ignore", category=pd.errors.SettingWithCopyWarning)

# -----------------------------
# Constants
# -----------------------------
BUS_CAPACITY = 60
Arrival_TimeFrame = 45
Departure_TimeFrame = 45
transit_time = 21.7
FLIGHT_LOAD_FACTOR = 0.86

Arrival_Rollover = pd.Timedelta(minutes=Arrival_TimeFrame - 15)
Departure_Rollover = pd.Timedelta(minutes=Departure_TimeFrame - 15)

st.title("Airport Bus Requirement Calculator")

uploaded_file = st.file_uploader("Upload Beontra Excel file", type=["xlsx"])

if uploaded_file:

    # -----------------------------
    # Load File
    # -----------------------------
    file = pd.read_excel(uploaded_file)
    file.columns = file.columns.str.strip()
    st.success("File uploaded successfully!")

    # -----------------------------
    # Extract Arrival
    # -----------------------------
    Arrival = file[[
        "Turnaround.Arrival Flight.Scheduled Block Time [Date/Time]",
        "Turnaround.Arrival Flight.Pax Count [Integer]",
        "Turnaround.Arrival Flight.Stand.Stand Type [Enumeration:TStandHandlingType]"
    ]].rename(columns={
        "Turnaround.Arrival Flight.Scheduled Block Time [Date/Time]": "Scheduled_Time",
        "Turnaround.Arrival Flight.Pax Count [Integer]": "Pax_Count",
        "Turnaround.Arrival Flight.Stand.Stand Type [Enumeration:TStandHandlingType]": "Stand Type"
    })

    # -----------------------------
    # Extract Departure
    # -----------------------------
    Departure = file[[
        "Turnaround.Departure Flight.Scheduled Block Time [Date/Time]",
        "Turnaround.Departure Flight.Pax Count [Integer]",
        "Turnaround.Departure Flight.Stand.Stand Type [Enumeration:TStandHandlingType]"
    ]].rename(columns={
        "Turnaround.Departure Flight.Scheduled Block Time [Date/Time]": "Scheduled_Time",
        "Turnaround.Departure Flight.Pax Count [Integer]": "Pax_Count",
        "Turnaround.Departure Flight.Stand.Stand Type [Enumeration:TStandHandlingType]": "Stand Type"
    })

    Arrival["Scheduled_Time"] = pd.to_datetime(Arrival["Scheduled_Time"], errors="coerce")
    Departure["Scheduled_Time"] = pd.to_datetime(Departure["Scheduled_Time"], errors="coerce")

    # -----------------------------
    # Filter Remote Stands
    # -----------------------------
    def filter_remote(df):
        return df[
            df["Stand Type"].str.contains("Remote", na=False)
            & (df["Pax_Count"] > 0)
        ].copy()

    Arrival = filter_remote(Arrival)
    Departure = filter_remote(Departure)

    # -----------------------------
    # Apply Load Factor
    # -----------------------------
    Arrival["Effective_Pax"] = np.ceil(Arrival["Pax_Count"] * FLIGHT_LOAD_FACTOR)
    Departure["Effective_Pax"] = np.ceil(Departure["Pax_Count"] * FLIGHT_LOAD_FACTOR)

    # -----------------------------
    # Gate Windows
    # -----------------------------
    Arrival["Gate Start"] = Arrival["Scheduled_Time"]
    Arrival["Gate End"] = Arrival["Scheduled_Time"] + Arrival_Rollover

    Departure["Gate End"] = Departure["Scheduled_Time"]
    Departure["Gate Start"] = Departure["Scheduled_Time"] - Departure_Rollover

    # -----------------------------
    # Build Time Index (5-min)
    # -----------------------------
    start_time = min(
        Arrival["Gate Start"].min(),
        Departure["Gate Start"].min()
    ).floor("D")

    end_time = max(
        Arrival["Gate End"].max(),
        Departure["Gate End"].max()
    ).replace(hour=23, minute=55)

    time_index = pd.date_range(start=start_time, end=end_time, freq="5min")

    # -----------------------------
    # Bus Calculation Function
    # -----------------------------
    def build_bus_counts(df, rollover):
        bus_counts = pd.Series(0, index=time_index)

        for _, row in df.iterrows():

            trips = np.ceil(row["Effective_Pax"] / BUS_CAPACITY)
            max_trips = Arrival_TimeFrame // transit_time
            buses = int(np.ceil(trips / max_trips))

            bus_counts.loc[row["Gate Start"]:row["Gate End"]] += buses

        return bus_counts

    A_counts = build_bus_counts(Arrival, Arrival_Rollover)
    D_counts = build_bus_counts(Departure, Departure_Rollover)

    # -----------------------------
    # Combine (5-min resolution)
    # -----------------------------
    df_buses = pd.DataFrame({
        "Arrival": A_counts,
        "Departure": D_counts
    })

    df_buses["Total"] = df_buses.sum(axis=1)
    df_buses.index.name = "Time"

    # -----------------------------
    # Peak (5-min true peak)
    # -----------------------------
    st.subheader("Peak Bus Requirement (5-Minute Resolution)")
    st.write(f"Peak buses needed: {int(df_buses['Total'].max())}")

    # -----------------------------
    # Plot (5-min)
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

    midnight_mask = df_buses.index.time == pd.to_datetime("00:00").time()
    tick_positions = np.where(midnight_mask)[0]
    tick_labels = df_buses.index[midnight_mask].strftime("%a %d-%m")

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right")

    plt.tight_layout()
    st.pyplot(fig)

    # -----------------------------
    # Export (5-min EXACT match)
    # -----------------------------
    export_df = df_buses.reset_index()

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="5min_Bus_Requirements")

    output.seek(0)

    st.download_button(
        label="Download 5-Minute Bus Requirements",
        data=output,
        file_name="Bus_Requirements_5min.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
