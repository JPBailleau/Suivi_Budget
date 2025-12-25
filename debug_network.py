import os
import shutil
import pandas as pd

net_path = r"\\SRV-APP01\kpi\Suivi_Budget\resultats.xls"
local_copy = "Resultats_Debug_Copy.xls"

print("-" * 60)
print(f"DEBUG: Testing access to {net_path}")
print("-" * 60)

# 1. Test Existence
exists = os.path.exists(net_path)
print(f"1. os.path.exists: {exists}")

if exists:
    # 2. Test Read Access (Standard Open)
    try:
        with open(net_path, 'rb') as f:
            header = f.read(10)
        print("2. open(..., 'rb'): SUCCESS (Can read bytes)")
    except Exception as e:
        print(f"2. open(..., 'rb'): FAILED -> {e}")

    # 3. Test Copy
    try:
        shutil.copy2(net_path, local_copy)
        print(f"3. shutil.copy2: SUCCESS (Copied to {local_copy})")
        if os.path.exists(local_copy):
            os.remove(local_copy)
    except Exception as e:
        print(f"3. shutil.copy2: FAILED -> {e}")

    # 4. Test Pandas Direct Read
    try:
        df = pd.read_excel(net_path)
        print(f"4. pd.read_excel: SUCCESS (Loaded {len(df)} lines)")
    except Exception as e:
        print(f"4. pd.read_excel: FAILED -> {e}")

else:
    print("SKIPPING other tests because file does not exist for Python.")
    # List directory if possible
    dir_path = os.path.dirname(net_path)
    print(f"Attempting to list dir: {dir_path}")
    try:
        items = os.listdir(dir_path)
        print(f"Dir contents: {items}")
    except Exception as e:
        print(f"Cannot list dir: {e}")

print("-" * 60)
