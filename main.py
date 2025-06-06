import streamlit as st
import pandas as pd
import smartsheet
import datetime




def smartsheet_to_dataframe(sheet_id):
    smartsheet_client = smartsheet.Smartsheet(st.secrets['smartsheet']['access_token'])
    sheet             = smartsheet_client.Sheets.get_sheet(sheet_id)
    columns           = [col.title for col in sheet.columns]
    rows              = []
    for row in sheet.rows: rows.append([cell.value for cell in row.cells])
    return pd.DataFrame(rows, columns=columns)




st.image(st.secrets['images']['logo'], width=100)

st.title('Inspector Schedule Assistant')
st.info('Use occupancy and unit data to help determine turn-day schedules.')

current_year = datetime.datetime.now().year
prior_year   = current_year - 1
report_url   = f"{st.secrets['escapia']['part_1']}{prior_year}{st.secrets['escapia']['part_2']}{current_year}{st.secrets['escapia']['part_3']}"
        
st.link_button('Download the **Housekeeping Report** from **Escapia**', url=report_url, type='secondary', use_container_width=True, help='Housekeeping Arrival Departure Report - Excel 1 line')

escapia_file = st.file_uploader(label='Housekeeping Arrival Departure Report - Excel 1 line.csv', type='csv')

if escapia_file is not None:

    udf                = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['order'])
    adf                = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['areas'])
    df                 = pd.read_csv(escapia_file)
    df                 = df[['Unit_Code','PropertyName','Bedrooms','Bathrooms','Housekeeper_Name','Reservation_Number','ReservationTypeDescription','Start_Date','Departure']]
    df.columns         = ['Unit_Code','Friendly_Name','Bedrooms','Bathrooms','Housekeeper','Reservation_Number','Reservation_Type','Arrival','Departure']

    date_columns       = ['Arrival','Departure']

    for column in date_columns: df[column] = pd.to_datetime(df[column]).dt.date

    today              = datetime.date.today()
    days_til_saturday  = (5 - today.weekday()) % 7
    upcoming_saturday  = today + datetime.timedelta(days=days_til_saturday)
    
    date               = st.date_input('🗓️ Scheduling for Date', value=upcoming_saturday)

    arrivals           = df[df['Arrival'] == date]
    arrivals           = arrivals[['Unit_Code','Reservation_Number','Reservation_Type']]
    arrivals.columns   = ['Unit_Code','Incoming_Reservation_Number','Incoming_Reservation_Type']

    departures         = df[df['Departure']  == date]
    departures         = departures[['Unit_Code','Friendly_Name','Bedrooms','Bathrooms','Housekeeper','Reservation_Number']]
    departures.columns = ['Unit_Code','Friendly_Name','Bedrooms','Bathrooms','Housekeeper','Departing_Reservation_Number']

    turns              = pd.merge(left=departures, right=arrivals, on=['Unit_Code'])

    udf                = pd.merge(left=udf, right=adf, on=['Area'], how='left')
    udf                = udf[['Unit_Code','Address','Area','Order_y','Order_x']]
    udf.columns        = ['Unit_Code','Address','Area','Section','Position']
    udf.Position       = udf.Position.astype(int)
    
    result             = pd.merge(left=turns, right=udf, on=['Unit_Code'], how='left')
    result             = result[['Unit_Code','Friendly_Name','Address','Bedrooms','Bathrooms','Housekeeper','Departing_Reservation_Number','Incoming_Reservation_Number','Incoming_Reservation_Type','Area','Position']]
    result             = result.sort_values(by=['Position'])
    result             = result.reset_index(drop=True)
    
    l, m, r            = st.columns(3)
    l.metric('B2Bs',   len(result['Unit_Code'].unique()))
    m.metric('Owners', turns[turns['Incoming_Reservation_Type'] == 'Owner'].shape[0])
    r.metric('Areas',  len(result['Area'].unique()))

    st.download_button('Download **Schedule**', data=result.to_csv(), file_name=f"Inspector_Schedule_{date.strftime('%m/%d/%Y')}.csv", mime='csv', use_container_width=True, type='primary')