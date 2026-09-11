

server = r"W2012R2-SQL12BI\SQLSELECTLINE"
database = "SL_M100"
pwd = "seda08154711tech"

import pymssql

belegtyps = ["A", "B", "C", "D", "E", "F", "G", "I", "L", "R", "S", "U", "Z"]

try:
    # pymssql allows explicit Windows Auth by passing domain\\user to 'user'
    conn = pymssql.connect(
        server=server,
        user="SEDATECH\\administrator",  # Your remote domain user
        password="Q47RgEIffYevQR",        # Your remote password
        database=database,
        tds_version="7.0"
    )
    
    print("Success! Natively connected as SEDATECH\\administrator.")
    
    # Test a quick query
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM dbo.BELEG WHERE Name = 'Khavazov' AND Vorname = 'Karim' ORDER BY Datum DESC;
        """, ("%Lungu Nicolas%",))
        #SELECT Artikelnummer FROM dbo.BELEGP WHERE Belegnummer = 'RA165516'
        #SELECT Stueckliste, EANNummer FROM dbo.ART WHERE Artikelnummer = 'UCCI966I2_10306'
        for row in cursor.fetchall():
            print(row)
    except pymssql.Error as e:
        print(e)

    
    conn.close()

except Exception as e:
    print(f"Connection failed: {e}")

def get_by_type(typ):
    try:
        conn = pymssql.connect(
            server=server,
            user="SEDATECH\\administrator",  # Your remote domain user
            password="Q47RgEIffYevQR",        # Your remote password
            database=database,
            tds_version="7.0"
        )
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP 1 Belegnummer, Datum FROM dbo.BELEG WHERE Belegtyp = '{typ}' ORDER BY Datum DESC;
        """)
        for row in cursor.fetchall():
            print(f"For type {typ}: {row[0]}   Latest date: {row[1]}")
    except pymssql.Error as e:
        print(e)

    conn.close()

# for typ in belegtyps:
#     get_by_type(typ)