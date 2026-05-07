import streamlit as st
import pandas as pd
import numpy as np
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





def get_unitcode_from_property_string(row):

    if '(' in row['Property']:
        return row['Property'].split('(')[1].split(')')[0]
            
    return None





def get_pod_from_property_tags_string(row):

    tags = row['Property tags'].split(';') if pd.notna(row['Property tags']) else []
    tags = [tag.strip().upper() for tag in tags]

    for tag in tags:
        if 'POD' in tag:
            return tag.split()[0]
    
    return None





st.set_page_config(page_title='Inspector Schedule', page_icon='🧍🏻‍♀️', layout='wide')


st.image(st.secrets['images']['logo'], width=100)

st.title('Inspector Schedule Assistant')
st.info('Use occupancy, unit, and liaison data to help determine turn-day schedules.')




with st.sidebar:
    st.title('Files')
    
    st.info('**breezeway-task-custom-export**\n\nBreezeway > Tasks > Inspection > Auto Scheduled Inspections > Select all tasks > Export to CSV > Custom Report')
    
    breezeway_file = st.file_uploader(
        label='**breezeway-task-custom-export**.csv',
        type='csv',
        label_visibility='collapsed'
        )
    

if breezeway_file:

    if 'locked_in' not in st.session_state:
        st.session_state['locked_in'] = False

    udf                   = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['order'])
    adf                   = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['areas'])
    
    df                    = pd.read_csv(breezeway_file)
    df['Unit_Code']       = df.apply(get_unitcode_from_property_string, axis=1)
    df['Pod']             = df.apply(get_pod_from_property_tags_string, axis=1)
    df                    = df.merge(udf[['Area','Order','Unit_Code']], on='Unit_Code', how='left')

    df                    = df[['Task title','Property','Due date','Area','Order','Pod','Assignees']]
    df.columns            = ['Inspection','Unit','Inspection_Date','Area','Order','Pod','Assignees']

    df['Inspection_Date'] = pd.to_datetime(df['Inspection_Date']).dt.date

    c1, c2, c3            = st.columns(3)

    c1.selectbox('Pod', options=df['Pod'].dropna().sort_values().unique(), key='pod_filter', disabled=st.session_state['locked_in'])

    df = df[df['Pod'] == st.session_state['pod_filter']]

    c2.selectbox('Inspection Date', options=df['Inspection_Date'].dropna().unique(), key='date_filter', disabled=st.session_state['locked_in'])

    c3.number_input('Non-B2B Look Ahead (Days)', min_value=0, max_value=14, value=1, step=1, key='lookahead_filter', disabled=st.session_state['locked_in'])

    if st.button('Build Schedule', use_container_width=True, type='secondary', disabled=st.session_state['locked_in'], ):
        st.session_state['locked_in'] = True
        st.rerun()

    if st.session_state['locked_in']:
        
        df = df[
        ((df['Inspection'].str.contains(r'\(B2B\)', na=False)) & (df['Inspection_Date'] == st.session_state['date_filter'])) |
        ((df['Inspection'].str.contains(r'\(non B2B\)', na=False)) & (df['Inspection_Date'] <= st.session_state['date_filter'] + datetime.timedelta(days=st.session_state['lookahead_filter'])))
        ]

        df['Assignees'] = df['Assignees'].fillna('').str.split(';').apply(
            lambda x: [item.strip() for item in x if item]
            )
        
        df = df.sort_values(by=['Order']).reset_index(drop=True)
        df = df.drop(columns=['Pod'])

        filter = df['Assignees'].apply(lambda x: any('.' in item for item in x) or len(x) > 1)

        to_be_assigned   = df[filter]
        already_assigned = df[~filter]

        assign = to_be_assigned.copy()
        assign.insert(0, 'Select', False)

        assigned = already_assigned.copy()
        assigned.insert(0, 'Inspector', False)
        assigned['Inspector'] = assigned['Assignees'].apply(lambda x: x[0])
        assigned = assigned.drop(columns=['Assignees'])

        if 'tba' not in st.session_state:
            st.session_state['tba'] = assign

        if 'assigned' not in st.session_state:
            st.session_state['assigned'] = assigned

        st.subheader(f'To Be Assigned ({st.session_state['tba'].shape[0]})')
        st.info('Any inspections with a dot assignee will be flagged for assignment.', icon='⚫️')
        st.info('Any inspections with more than one assignee will be flagged for assignment to a sole assignee.', icon='👩🏽‍🤝‍👨🏻')
        selected_df = st.data_editor(
            st.session_state['tba'],
            column_config={
                'Select': st.column_config.CheckboxColumn(disabled=False),
                'Inspection': st.column_config.TextColumn(disabled=True),
                'Inspection_Date': st.column_config.DateColumn(disabled=True),
                'Area': st.column_config.TextColumn(disabled=True),
                'Order': st.column_config.NumberColumn(disabled=True),
                'Assignees': st.column_config.ListColumn(disabled=True),
                },
                hide_index=True,
                width='stretch',
                )

        l, r               = st.columns(2)

        idf                = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['inspectors'])
        idf['Summary']     = idf['Employee'] + ' - ' + idf['Role']

        olhl               = smartsheet_to_dataframe(st.secrets['smartsheet']['sheets']['liaisons'])
        olhl               = olhl[['Unit_Code','OL','HL']]

        ols                = olhl[['OL']].drop_duplicates()
        ols.columns        = ['Employee']
        ols['Role']        = 'Owner Liaison'
        ols['Summary']     = ols['Employee'] + ' - ' + ols['Role']

        hls                = olhl[['HL']].drop_duplicates()
        hls.columns        = ['Employee']
        hls['Role']        = 'Home Liaison'
        hls['Summary']     = hls['Employee'] + ' - ' + hls['Role']

        idf                = pd.concat([idf, ols, hls], ignore_index=True)
        idf                = idf.dropna(subset=['Summary'])
        idf                = idf.sort_values(by=['Employee'])

        selected_inspector = l.selectbox('Inspector', options=idf.Summary.unique(), label_visibility='collapsed')
        inspector          = selected_inspector.split(' - ')[0]

        selected           = selected_df[selected_df['Select'] == True].shape[0]

        if r.button(f'Assign **{selected}** to **{inspector}**', use_container_width=True, type='primary', disabled=selected == 0):

            if selected == 0:
                st.warning('Please select at least one unit to assign.')

            else:
            
                sdf = selected_df[selected_df['Select'] == True].copy()
                sdf.insert(0, 'Inspector', inspector)
                sdf.drop(columns=['Select', 'Assignees'], inplace=True)

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
                    'Select': st.column_config.CheckboxColumn(disabled=False),
                    'Inspection': st.column_config.TextColumn(disabled=True),
                    'Assignees': st.column_config.ListColumn(disabled=True),
                    'Inspection_Date': st.column_config.DateColumn(disabled=True),
                    'Area': st.column_config.TextColumn(disabled=True),
                    'Order': st.column_config.NumberColumn(disabled=True),
                    'Inspector': st.column_config.SelectboxColumn(
                        options=idf['Employee'].unique().tolist(),  
                    ),
                },
                hide_index=True,
                width='stretch',
                )
            
            if not original.equals(assigned_df):

                st.warning('Please save your changes. Not doing so will undo them on the next assignment.')

                if st.button('Save Changes', use_container_width=True, type='secondary'):
                    st.session_state['assigned'] = assigned_df
                    st.rerun()

            
            final = st.session_state['assigned'].sort_values(['Inspector', 'Order']).copy()
            final['Order'] = final['Order'].astype(int)
            final.insert(0, 'Date', pd.to_datetime(st.session_state['date_filter']))

            # if tba inspections do not include '(B2B)'
            if not st.session_state['tba']['Inspection'].str.contains(r'\(B2B\)', na=False).any():

                st.success('All B2Bs have been assigned an inspector!', icon='🔁')
                st.info('Please review and finalize your assignments.', icon='🕵🏻‍♂️')

                st.download_button(
                    label=f'Download **Assigned** for **{st.session_state["date_filter"].strftime("%A, %m/%d/%y")}**',
                    data=final.to_csv(index=False),
                    file_name=f'Inspections_{st.session_state['date_filter'].strftime("%Y-%m-%d")}_{st.session_state['pod_filter'].title()}.csv',
                    mime='CSV',
                    use_container_width=True,
                    type='primary')
            
            else:
                
                st.warning('All B2B inspections must have an assignee before results can be provided.', icon='🔁')