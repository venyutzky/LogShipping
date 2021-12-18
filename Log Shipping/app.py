import streamlit as st
import pandas as pd
import os
import pyodbc
import pymongo
import datetime

st.set_page_config(page_title='Log Shipping Monitoring', layout='wide', initial_sidebar_state='expanded')


# Get Data
Driver = 'SQL Server Native Client 11.0'
Server = 'VENYUTZKY'
Database = 'TBD'

#Database MongoDB
client = pymongo.MongoClient('localhost', 27017)
mongoDB = client.database_use

class User:
    user = {
        "Driver": Driver,
        "Server": Server,
        "Database": Database
    }
    mongoDB.users.insert_one(user)

# Connect to SQL Server
conn_str = (f'Driver={Driver};Server={Server};Database={Database};Trusted_Connection=yes')   

# Return Dataframe
def read(conn_str, query):
    cnxn = pyodbc.connect(conn_str)
    return pd.read_sql_query(query, cnxn)

def read2(conn_str, query):
    cnxn = pyodbc.connect(conn_str)
    cursor = cnxn.cursor()
    cursor.execute(query)
    columns = [column[0] for column in cursor.description]
    results = []
    for row in cursor.fetchall():
        results.append(list(row[0:len(columns)]))
    cnxn.close()
    df = pd.DataFrame(results, columns=columns)
    return df

# write function
def write(conn_str, query):
    cnxn = pyodbc.connect(conn_str)
    cursor = cnxn.cursor()
    with cnxn:
        cursor.execute(query)
    cnxn.close()    


# Pengambilan Data
backupReport = read(conn_str=conn_str, query='SELECT * FROM PMAG_BackupRestoreReport') # success backup
backupReport = backupReport[backupReport['Duration (millisecond)'] < 2000]
failBackupReport = read(conn_str=conn_str, query='SELECT * FROM PMAG_FailBackupRestoreReport') #fail backup
restoreReport = read(conn_str=conn_str, query='SELECT * FROM PMAG_LogRestoreHistory ORDER BY RestoreTime') # restore time
activeSecondary = read(conn_str=conn_str, query="SELECT * FROM PMAG_ActiveSecondaries")
refresh = datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S")


# Proses Data
last = restoreReport['RestoreTime'].tail(1).item()
first = restoreReport['RestoreTime'].head(1).item()
s_backup = backupReport.shape[0]
f_fail = failBackupReport.shape[0]
avg = backupReport['Duration (millisecond)'].mean() / 1000



# Bagian 1
with st.container():
    st.write("")
    st.title("Log Shipping Backup Restore Report")
    col1, col2, col3, col4 = st.columns(4)
    col1.caption(" Last refresh __" + refresh + "__")
    col2.caption(f' Instance: __{Server}__')
    col3.caption(f' Database:__{Database}__')
    col4.caption("Press R for manual refresh")
    st.markdown('---')

# Bagian Display Data
with st.container():
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("# Success Backup", s_backup, 'Backups')
    col2.metric("# Fail Restore", f_fail, 'Failure')
    col3.metric("Last Backup", f'{((datetime.datetime.now() - last).total_seconds() / 60):.1f} min', 'ago')
    col4.metric("Next Backup in", f'{(((datetime.timedelta(minutes=15.0) + last) - datetime.datetime.now()).total_seconds()/60):.0f} min', 'automatic')
    col5.metric("Last Clear History", f'{-1 * ((first - datetime.datetime.now()).days)} days', 'ago')

    st.markdown("---")

# Bagian Initial Backup
with st.container():
    col1, col2 = st.columns(2)
    col1.subheader('Last Restored Secondary')
    col1.dataframe(activeSecondary)
    col2.subheader('Initial Backup')
    if col2.button('Backup Now'):
        os.system(f''' sqlcmd -S {Server} -d {Database} -E -Q "EXEC dbo.PMAG_Backup @dbname = N'{Database}', @type = 'trn';"
        ''')
        col2.success('backup has been started')
