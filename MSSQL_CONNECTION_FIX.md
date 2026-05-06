# Dash MSSQL Connection Fix - Complete

## Problem Identified
Your Dash app was crashing with the error:
```
Callback error updating ..california-map.figure...stored-click-data.data..
```

This happened because **the Python environment couldn't connect to MSSQL**, even though VS Code's built-in extension could.

**Root Cause**: Missing ODBC drivers on your macOS system.

## Solution Implemented

### Step 1: Install UnixODBC (Required by pyodbc)
```bash
brew install unixodbc
```
✓ Installed: unixodbc 2.3.14

### Step 2: Install Microsoft ODBC Driver 17 for SQL Server
```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew install msodbcsql17
```
✓ Installed: msodbcsql17 17.11.1.1
✓ ODBC Driver registered: "ODBC Driver 17 for SQL Server"

### Step 3: Rebuild pyodbc to Link Against ODBC Libraries
```bash
pip install --force-reinstall --no-cache-dir pyodbc
```
✓ Reinstalled: pyodbc 5.3.0

## Verification

### Database Connection Test
```
✓ Successfully connected to MSSQL database!
Database version: Microsoft SQL Server 2022 (RTM-CU23-GDR)
```

### Environment Check
✓ pyodbc: Imported successfully
✓ ODBC Drivers Available:
  - ODBC Driver 17 for SQL Server

### Python App Status
✓ Dash app is running at http://127.0.0.1:8050/
✓ Database connection working from Python

## What This Fixed

- **Before**: Python callbacks couldn't query MSSQL → map didn't populate → callback errors
- **After**: Python callbacks can query MSSQL → map data will populate → callbacks execute successfully

## Your `.env` File
Your `.env` is correctly configured with:
- `DB_SERVER=LSCDBP2.LIFESCI.UCLA.EDU`
- `DB_DATABASE=QPLAD`
- `MAP_TABLE=dat_avail_db`
- All required authentication variables

## Next Steps
1. **Run your Dash app**: `python app.py`
2. **Login** (if required by your Auth0 configuration)
3. **Navigate to Tree Sites tab**
4. **The map should now populate with data** from your MSSQL database

## Troubleshooting
If the map still doesn't show data after login:
1. Check browser DevTools > Console for any remaining errors
2. Verify `DAT_AVAIL_TABLE` environment variable is set (currently empty in `.env`)
3. Check that `dat_avail_db` table exists and has data in your MSSQL database
