import streamlit as st
import pandas as pd
import smartsheet
import datetime



@st.cache_data
def smartsheet_to_dataframe(sheet_id):
    smartsheet_client = smartsheet.Smartsheet(st.secrets['smartsheet']['access_token'])
    sheet             = smartsheet_client.Sheets.get_sheet(sheet_id)
    columns           = [col.title for col in sheet.columns]
    rows              = []
    for row in sheet.rows: rows.append([cell.value for cell in row.cells])
    return pd.DataFrame(rows, columns=columns)


st.set_page_config(page_title='Inspector Schedule', page_icon='🧍🏻‍♀️', layout='wide')


st.image(st.secrets['images']['logo'], width=100)

st.title('Inspector Schedule Assistant')
st.info('Use occupancy, unit, and liaison data to help determine turn-day schedules.')




with st.sidebar:
    current_year = datetime.datetime.now().year
    prior_year   = current_year - 1
    report_url   = f"{st.secrets['escapia']['part_1']}{prior_year}{st.secrets['escapia']['part_2']}{current_year}{st.secrets['escapia']['part_3']}"

    st.title('Files')
    st.link_button('Download **Escapia Report**', url=report_url, type='secondary', use_container_width=True, help='Housekeeping Arrival Departure Report - Excel 1 line')
    escapia_file = st.file_uploader(label='**Housekeeping Arrival Departure Report**.csv', type='csv')

    with st.expander('Continue where you left off?'):
        st.success('Coming soon!')
        # continue_file = st.file_uploader(label='**Inspector_Schedule_YYYY-MM-DD**.csv', type='csv')


if 'locked_in_date' not in st.session_state:
    st.session_state['locked_in_date'] = False


if escapia_file is None:
    st.session_state['locked_in_date'] = False

if escapia_file is not None:

    udf                = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['order'])
    adf                = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['areas'])
    

    df                 = pd.read_csv(escapia_file)
    df                 = df[['Unit_Code','PropertyName','SleepsMaximum','Bedrooms','Bathrooms','Housekeeper_Name','Reservation_Number','ReservationTypeDescription','Start_Date','Departure']]
    df.columns         = ['Unit_Code','Friendly_Name','SleepsMaximum','Bedrooms','Bathrooms','Housekeeper','Reservation_Number','Reservation_Type','Arrival','Departure']

    date_columns       = ['Arrival','Departure']

    for column in date_columns: df[column] = pd.to_datetime(df[column]).dt.date

    today              = datetime.date.today()
    days_til_saturday  = (5 - today.weekday()) % 7
    upcoming_saturday  = today + datetime.timedelta(days=days_til_saturday)
    
    l, r = st.columns(2)

    date               = l.date_input('🗓️ Scheduling for Date', value=upcoming_saturday, label_visibility='collapsed', disabled=st.session_state['locked_in_date'])

    if r.button('Begin Scheduling', use_container_width=True, disabled=st.session_state['locked_in_date']):
        st.session_state['locked_in_date'] = True
        st.rerun()
    
    if st.session_state['locked_in_date']:

        arrivals           = df[df['Arrival'] == date]
        arrivals           = arrivals[['Unit_Code','Reservation_Number','Reservation_Type']]
        arrivals.columns   = ['Unit_Code','Incoming_Reservation_Number','Incoming_Type']

        departures         = df[df['Departure']  == date]
        departures         = departures[['Unit_Code','Friendly_Name','SleepsMaximum','Bedrooms','Bathrooms','Housekeeper','Reservation_Number']]
        departures.columns = ['Unit_Code','Friendly_Name','Sleeps','Bedrooms','Bathrooms','Housekeeper','Departing_Reservation_Number']

        turns              = pd.merge(left=departures, right=arrivals, on=['Unit_Code'])

        udf                = pd.merge(left=udf, right=adf, on=['Area'], how='left')
        udf                = udf[['Unit_Code','Address','Area','Order_y','Order_x']]
        udf.columns        = ['Unit_Code','Address','Area','Section','Position']
        udf.Position       = udf.Position.astype(int)
        
        result             = pd.merge(left=turns, right=udf, on=['Unit_Code'], how='left')
        result             = result[['Unit_Code','Friendly_Name','Address','Sleeps','Bedrooms','Bathrooms','Incoming_Type','Area','Departing_Reservation_Number','Incoming_Reservation_Number','Position']]
        result             = result.sort_values(by=['Position'])
        result             = result.reset_index(drop=True)
        
        l, m, r            = st.columns(3)
        l.metric('B2Bs',   len(result['Unit_Code'].unique()))
        m.metric('Owners', turns[turns['Incoming_Type'] == 'Owner'].shape[0])
        r.metric('Areas',  len(result['Area'].unique()))


        assign = result
        assign = assign[['Unit_Code','Friendly_Name','Address','Sleeps','Bedrooms','Bathrooms','Incoming_Type','Area','Position']]
        olhl   = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['liaisons'])
        olhl   = olhl[['Unit_Code','OL','HL']]
        assign = pd.merge(left=assign, right=olhl, on=['Unit_Code'], how='left')
        assign.insert(0, 'Select', False)

        if 'tba' not in st.session_state:
            st.session_state['tba'] = assign

        st.subheader(f'To Be Assigned ({st.session_state['tba'].shape[0]})')
        selected_df = st.data_editor(
            st.session_state['tba'],
            column_config={
                'Select': st.column_config.CheckboxColumn(disabled=False),
                'Unit_Code': st.column_config.TextColumn(disabled=True),
                'Friendly_Name': st.column_config.TextColumn(disabled=True),
                'Address': st.column_config.TextColumn(disabled=True),
                'Sleeps': st.column_config.NumberColumn(disabled=True),
                'Bedrooms': st.column_config.NumberColumn(disabled=True),
                'Bathrooms': st.column_config.NumberColumn(disabled=True),
                'Incoming_Reservation_Type': st.column_config.TextColumn(disabled=True),
                'Area': st.column_config.TextColumn(disabled=True),
                'Position': st.column_config.NumberColumn(disabled=True),
                'OL': st.column_config.TextColumn(disabled=True),
                'HL': st.column_config.TextColumn(disabled=True),
                },
                hide_index=True,
                use_container_width=True,
                )

        l, r = st.columns(2)

        idf            = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['inspectors'])
        idf['Summary'] = idf['Employee'] + ' - ' + idf['Role']

        ols = olhl[['OL']].drop_duplicates()
        ols.columns = ['Employee']
        ols['Role'] = 'Owner Liaison'
        ols['Summary'] = ols['Employee'] + ' - ' + ols['Role']

        hls = olhl[['HL']].drop_duplicates()
        hls.columns = ['Employee']
        hls['Role'] = 'Home Liaison'
        hls['Summary'] = hls['Employee'] + ' - ' + hls['Role']

        idf = pd.concat([idf, ols, hls], ignore_index=True)
        idf = idf.dropna(subset=['Summary'])
        idf = idf.sort_values(by=['Employee'])

        selected_inspector = l.selectbox('Inspector', options=idf.Summary.unique(), label_visibility='collapsed')
        inspector          = selected_inspector.split(' - ')[0]

        selected = selected_df[selected_df['Select'] == True].shape[0]

        if r.button(f'Assign **{selected}** to **{inspector}**', use_container_width=True, type='primary', disabled=selected == 0):

            if selected == 0:
                st.warning('Please select at least one unit to assign.')

            else:
            
                sdf = selected_df[selected_df['Select'] == True].copy()
                sdf.insert(0, 'Inspector', inspector)
                sdf.drop(columns=['Select'], inplace=True)

                if 'assigned' not in st.session_state:
                    st.session_state['assigned'] = sdf
                else:
                    st.session_state['assigned'] = pd.concat([st.session_state['assigned'], sdf], ignore_index=True)
                
                st.session_state['tba'] = selected_df[selected_df['Select'] == False].copy()
                st.rerun()

        if 'assigned' in st.session_state and not st.session_state['assigned'].empty:

            st.subheader(f'Assigned ({st.session_state["assigned"].shape[0]})')

            original  = st.session_state['assigned']
            assignees = original.Inspector.sort_values().unique()
            columns   = st.columns(4)
            count     = 0

            assignments = original.Inspector.value_counts()
            average_assignments = assignments.mean()

            for assignee in assignees:

                assignments = original.Inspector.value_counts()

                columns[count].metric(assignee, assignments[assignee], int(assignments[assignee] - average_assignments))
                count += 1
                    
                if count == 4: count = 0
                        

            assigned_df = st.data_editor(
                st.session_state['assigned'],
                column_config={
                    'Unit_Code': st.column_config.TextColumn(disabled=True),
                    'Friendly_Name': st.column_config.TextColumn(disabled=True),
                    'Address': st.column_config.TextColumn(disabled=True),
                    'Sleeps': st.column_config.NumberColumn(disabled=True),
                    'Bedrooms': st.column_config.NumberColumn(disabled=True),
                    'Bathrooms': st.column_config.NumberColumn(disabled=True),
                    'Incoming_Type': st.column_config.TextColumn(disabled=True),
                    'Area': st.column_config.TextColumn(disabled=True),
                    'Position': st.column_config.NumberColumn(disabled=True),
                    'Inspector': st.column_config.SelectboxColumn(
                        options=idf['Employee'].unique(),  
                    ),
                },
                hide_index=True,
                use_container_width=True,
                )
            
            if not original.equals(assigned_df):
                st.warning('Please save your changes. Not doing so will undo them on the next assignment.')
                if st.button('Save Changes', use_container_width=True, type='secondary'):
                    st.session_state['assigned'] = assigned_df
                    st.rerun()
            
            if st.session_state['tba'].empty:

                st.success('All B2Bs have been assigned an inspector!', icon='🙌')
                st.info('Please review and finalize your assignments.', icon='👍')
                final = st.session_state['assigned'].sort_values(['Inspector', 'Position']).copy()
                final.insert(0, 'Date', date)

                cleaners = df[['Unit_Code','Housekeeper']]
                cleaners = cleaners.drop_duplicates()

                final = pd.merge(final, cleaners, on='Unit_Code', how='left')

                st.download_button(
                    label=f'Download **Schedule** for **{date.strftime('%A, %m/%d/%y')}**',
                    data=final.to_csv(index=False),
                    file_name=f'Inspectors_{date}.csv',
                    mime='CSV',
                    use_container_width=True,
                    type='primary')