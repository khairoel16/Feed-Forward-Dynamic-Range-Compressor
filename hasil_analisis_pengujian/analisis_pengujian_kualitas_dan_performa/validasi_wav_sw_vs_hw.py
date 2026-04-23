# validasi_wav_sw_vs_hw.py
import numpy as np
import soundfile as sf
import csv
import os
from tkinter import filedialog, Tk
from sklearn.metrics import r2_score

# =========================================================
# 1. PEMILIHAN FILE VIA FILE EXPLORER
# =========================================================
root = Tk()
root.withdraw()

print("\n" + "="*80)
print("--- VALIDASI AKURASI: SOFTWARE (GOLDEN MODEL) VS HARDWARE (KRIA) ---")
print("="*80)

# Instruksi dan Pemilihan File Golden Model
print("[Step 1] Pilih file audio WAV hasil DRC SOFTWARE (Golden Model)...")
file_sw = filedialog.askopenfilename(
    title="Pilih File Audio GOLDEN MODEL (Software)", 
    filetypes=[("WAV files", "*.wav")]
)
if not file_sw:
    print("❌ Error: Pemilihan file Software dibatalkan.")
    exit()
print(f"✅ File SW Masuk: {file_sw}")

# Instruksi dan Pemilihan File Hardware
print("\n[Step 2] Pilih file audio WAV hasil DRC HARDWARE (Kria Output)...")
file_hw = filedialog.askopenfilename(
    title="Pilih File Audio HARDWARE (Kria Out)", 
    filetypes=[("WAV files", "*.wav")]
)
if not file_hw:
    print("❌ Error: Pemilihan file Hardware dibatalkan.")
    exit()
print(f"✅ File HW Masuk: {file_hw}")

# =========================================================
# 2. LOAD DATA & ALIGNMENT
# =========================================================
data_sw, fs = sf.read(file_sw)
data_hw, _  = sf.read(file_hw)

# Sinkronisasi panjang data
min_len = min(len(data_sw), len(data_hw))
y_true = data_sw[:min_len]  # Reference (Software)
y_pred = data_hw[:min_len]  # Test (Hardware)

# =========================================================
# 3. KALKULASI METRIK VALIDASI
# =========================================================
error = y_true - y_pred
mae = np.mean(np.abs(error))
mse = np.mean(error**2)
rmse = np.sqrt(mse)

signal_power = np.mean(y_true**2)
error_power = np.mean(error**2)
snr = 10 * np.log10(signal_power / (error_power + 1e-12))
psnr = 20 * np.log10(1.0 / (rmse + 1e-12))
r2 = r2_score(y_true, y_pred)

# =========================================================
# 4. OUTPUT LAPORAN (CONSOLE & CSV)
# =========================================================
script_dir = os.path.dirname(os.path.abspath(__file__))
base_name = os.path.splitext(os.path.basename(file_hw))[0]
csv_path = os.path.join(script_dir, f"{base_name}_validasi_metrics.csv")

def f_id(val):
    return f"{val:.10f}".replace('.', ',')

# Simpan ke CSV
with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
    f.write("sep=;\n")
    writer = csv.writer(f, delimiter=';')
    writer.writerow(["METRIC", "VALUE", "UNIT", "DESCRIPTION"])
    writer.writerow(["MAE", f_id(mae), "Amplitude", "Mean Absolute Error"])
    writer.writerow(["MSE", f_id(mse), "Amplitude^2", "Mean Squared Error"])
    writer.writerow(["RMSE", f_id(rmse), "Amplitude", "Root Mean Squared Error"])
    writer.writerow(["SNR", f_id(snr), "dB", "Signal-to-Noise Ratio"])
    writer.writerow(["PSNR", f_id(psnr), "dB", "Peak Signal-to-Noise Ratio"])
    writer.writerow(["R2 Score", f_id(r2), "-", "Coefficient of Determination"])

# Tampilan Console dengan Tabel yang Diperbaiki
line_width = 90
print(f"\n" + "="*line_width)
print("📊 HASIL ANALISIS DEVIASI (SOFTWARE vs HARDWARE)")
print("="*line_width)
print(f"{'Metrik Statistik':<30} | {'Nilai Hasil':<25} | {'Satuan'}")
print("-" * line_width)
print(f"{'Mean Absolute Error (MAE)':<30} | {mae:<25.10f} | Amplitude")
print(f"{'Mean Squared Error (MSE)':<30} | {mse:<25.10f} | Amplitude^2")
print(f"{'Root Mean Squared Error (RMSE)':<30} | {rmse:<25.10f} | Amplitude")
print(f"{'Signal-to-Noise Ratio (SNR)':<30} | {snr:<25.5f} | dB")
print(f"{'Peak SNR (PSNR)':<30} | {psnr:<25.5f} | dB")
print(f"{'R-Squared Score (R2)':<30} | {r2:<25.10f} | -")
print("="*line_width)

print(f"📊 Report CSV  : {csv_path}")
print("="*line_width)
print(f"\n✅ Validasi Selesai!\n")