# analisis_dinamis_software_vs_hardware.py
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import tkinter as tk
from tkinter import filedialog
import os

def select_file(title):
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title=title, filetypes=[("CSV files", "*.csv")])
    return file_path

def parse_val(val):
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, str):
        # Bersihkan string dari karakter non-numerik kecuali koma/titik
        cleaned_val = val.replace(',', '.')
        try:
            return float(cleaned_val)
        except ValueError:
            return 0.0
    return float(val)

print("--- DRC VALIDATION TOOL: SOFTWARE VS HARDWARE ---")

# Proses Pemilihan File
path_sw = select_file("Pilih File CSV SOFTWARE (Golden Model)")
if path_sw:
    print(f"[OK] File SOFTWARE masuk: {os.path.basename(path_sw)}")
else:
    print("[ERROR] File SOFTWARE tidak dipilih.")
    exit()

path_hw = select_file("Pilih File CSV HARDWARE (Kria/FPGA)")
if path_hw:
    print(f"[OK] File HARDWARE masuk: {os.path.basename(path_hw)}")
else:
    print("[ERROR] File HARDWARE tidak dipilih.")
    exit()

# Identifikasi Kode Pengujian (A1, B1, dst)
file_name_hw = os.path.basename(path_hw)
test_code = file_name_hw.split('_')[-1].split('.')[0].upper()

col_names = [f"col_{i}" for i in range(11)] 

# Gunakan skiprows=2 untuk melewati 'sep=;' dan Header 'Time_ms...'
df_sw = pd.read_csv(path_sw, sep=';', skiprows=2, header=None, names=col_names, engine='python')
df_hw = pd.read_csv(path_hw, sep=';', skiprows=2, header=None, names=col_names, engine='python')

COL_G, COL_J, COL_K = 6, 9, 10

# PENYESUAIAN INDEKS: 
# Karena baris "Phase, time(ms)..." ada di baris pertama DF (indeks 0), 
# maka data "ATTACK PHASE" ada di indeks 1, "Steady State Start" di indeks 2, dst.
row_indices = [
    (1, "ATTACK PHASE", COL_J, COL_K),
    (2, "Steady State Start", COL_J, COL_K),
    (3, "Steady State End", COL_J, COL_K),
    (4, "10% Steady State", COL_J, COL_K),
    (5, "90% Steady State", COL_J, COL_K),
    (6, "ATTACK TIME (sw)", COL_J, None),
    (None, "-----------------", None, None),
    (8, "RELEASE PHASE", COL_J, COL_K),
    (9, "Steady State Start", COL_J, COL_K),
    (10, "Steady State End", COL_J, COL_K),
    (11, "10% Recovery", COL_J, COL_K),
    (12, "90% Recovery", COL_J, COL_K),
    (13, "Release TIME (sw)", COL_J, None)
]

# List untuk menampung data mentah guna dimasukkan ke CSV
raw_comparison_data = []

print("\n" + "="*95)
print(f"{'DATA PERBANDINGAN MENTAH':^95}")
print("="*95)
print(f"{'Phase':<25} | {'Time SW (ms)':<15} | {'Time HW (ms)':<15} | {'Gain SW (dB)':<15} | {'Gain HW (dB)':<15}")
print("-" * 95)

for idx, label, col_t, col_g in row_indices:
    if idx is None:
        print(f"{label:<25} | {'':<15} | {'':<15} | {'':<15} | {'':<15}")
        raw_comparison_data.append([label, "", "", "", ""])
        continue
    
    val_t_sw = parse_val(df_sw.iloc[idx, col_t]) if col_t else 0.0
    val_t_hw = parse_val(df_hw.iloc[idx, col_t]) if col_t else 0.0
    val_g_sw = parse_val(df_sw.iloc[idx, col_g]) if col_g else 0.0
    val_g_hw = parse_val(df_hw.iloc[idx, col_g]) if col_g else 0.0
    
    print(f"{label:<25} | {val_t_sw:<15.4f} | {val_t_hw:<15.4f} | {val_g_sw:<15.4f} | {val_g_hw:<15.4f}")
    
    # Masukkan ke list untuk CSV
    raw_comparison_data.append([
        label, 
        str(val_t_sw).replace('.', ','), 
        str(val_t_hw).replace('.', ','), 
        str(val_g_sw).replace('.', ','), 
        str(val_g_hw).replace('.', ',')
    ])

# --- HITUNG METRIK ---
min_len = min(len(df_sw), len(df_hw))
y_sw_signal = df_sw.iloc[:min_len, COL_G].apply(parse_val).values
y_hw_signal = df_hw.iloc[:min_len, COL_G].apply(parse_val).values

mae = mean_absolute_error(y_sw_signal, y_hw_signal)
rmse = np.sqrt(mean_squared_error(y_sw_signal, y_hw_signal))
r2 = r2_score(y_sw_signal, y_hw_signal)

# Ambil data spesifik (sesuai indeks baru)
atk_sw = parse_val(df_sw.iloc[6, COL_J]) # Attack Time (sw)
atk_hw = parse_val(df_hw.iloc[6, COL_J])
rel_sw = parse_val(df_sw.iloc[13, COL_J]) # Release Time (sw)
rel_hw = parse_val(df_hw.iloc[13, COL_J])
ss_gain_sw = parse_val(df_sw.iloc[2, COL_K]) # SS Gain Attack
ss_gain_hw = parse_val(df_hw.iloc[2, COL_K])

atk_error = abs((atk_sw - atk_hw) / atk_sw * 100) if atk_sw != 0 else 0
rel_error = abs((rel_sw - rel_hw) / rel_sw * 100) if rel_sw != 0 else 0
ss_error = abs(ss_gain_sw - ss_gain_hw)

print("\n" + "="*50)
print(f"HASIL ANALISIS METRIK: {test_code}")
print("-" * 50)
print(f"Attack Time Error   : {atk_error:.4f} %")
print(f"Release Time Error  : {rel_error:.4f} %")
print(f"SS Gain Error       : {ss_error:.6f} dB")
print("")
print(f"MAE (Presisi)       : {mae:.8f} dB")
print(f"RMSE                : {rmse:.8f} dB")
print(f"R2 Score (Korelasi) : {r2:.8f}")
print("="*50)

# MODIFIKASI PATH DAN EKSPOR DATA LENGKAP KE CSV
script_dir = os.path.dirname(os.path.abspath(__file__))
output_filename = f"hasil_analisis_dinamis_{test_code}.csv"
output_path = os.path.join(script_dir, output_filename)

# Gabungkan Data Mentah dan Hasil Metrik ke dalam satu CSV
with open(output_path, mode='w', encoding='utf-8') as f:
    f.write(f"sep=;\n")
    f.write(f"DATA PERBANDINGAN MENTAH - {test_code};;;;\n")
    f.write(f"Phase;Time SW (ms);Time HW (ms);Gain SW (dB);Gain HW (dB)\n")
    
    for row in raw_comparison_data:
        f.write(";".join(row) + "\n")
    
    f.write(f"\n; ; ; ;\n")
    f.write(f"HASIL ANALISIS METRIK;;;;\n")
    f.write(f"Metrik;Nilai;;;\n")
    f.write(f"Attack Time Error (%);{str(round(atk_error, 8)).replace('.', ',')};;;\n")
    f.write(f"Release Time Error (%);{str(round(rel_error, 8)).replace('.', ',')};;;\n")
    f.write(f"SS Gain Error (dB);{str(round(ss_error, 8)).replace('.', ',')};;;\n")
    f.write(f"MAE (dB);{str(round(mae, 8)).replace('.', ',')};;;\n")
    f.write(f"RMSE (dB);{str(round(rmse, 8)).replace('.', ',')};;;\n")
    f.write(f"R2 Score;{str(round(r2, 8)).replace('.', ',')};;;\n")

print(f"\n[Selesai] File analisis lengkap disimpan: {output_path}")