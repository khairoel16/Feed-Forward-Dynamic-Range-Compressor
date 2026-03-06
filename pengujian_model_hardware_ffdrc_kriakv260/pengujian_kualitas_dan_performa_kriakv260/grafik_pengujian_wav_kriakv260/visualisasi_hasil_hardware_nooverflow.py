# visualisasi_hasil_hardware_nooverflow.py
import numpy as np
import matplotlib
# Menggunakan backend Agg agar tidak memunculkan jendela pop-up grafik
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import soundfile as sf
import os
from tkinter import filedialog, Tk

# =========================================================
# 1. PEMILIHAN FILE VIA FILE EXPLORER
# =========================================================
root = Tk()
root.withdraw()

print("\n" + "="*80)
print("--- VISUALISASI PERBANDINGAN HARDWARE VS INPUT (OPTIMIZED) ---")
print("="*80)

print("[Step 1] Pilih file audio WAV INPUT (Original)...")
file_input = filedialog.askopenfilename(
    title="Pilih File Audio INPUT (Original)", 
    filetypes=[("WAV files", "*.wav")]
)
if not file_input:
    print("❌ Error: Pemilihan file input dibatalkan.")
    exit()

print("\n[Step 2] Pilih file audio WAV OUTPUT (Hardware/DRC)...")
file_output = filedialog.askopenfilename(
    title="Pilih File Audio OUTPUT (Hardware/DRC)", 
    filetypes=[("WAV files", "*.wav")]
)
if not file_output:
    print("❌ Error: Pemilihan file output dibatalkan.")
    exit()

script_dir = os.path.dirname(os.path.abspath(__file__))
input_filename = os.path.splitext(os.path.basename(file_input))[0]
png_output = os.path.join(script_dir, f"{input_filename}_grafik.png")

EPS = 1e-12

# =========================================================
# 2. LOAD DATA & OPTIMIZED PROCESSING
# =========================================================
data_in, fs = sf.read(file_input)
data_out, fs_out = sf.read(file_output)

# Penanganan file Stereo: Ambil salah satu channel saja (Mono) jika file stereo
if len(data_in.shape) > 1:
    data_in = data_in[:, 0]
if len(data_out.shape) > 1:
    data_out = data_out[:, 0]

# Samakan panjang data
min_len = min(len(data_in), len(data_out))
data_in = data_in[:min_len]
data_out = data_out[:min_len]

# --- STRATEGI DOWNSAMPLING UNTUK MENGATASI OVERFLOW ---
# Kita batasi jumlah titik maksimal yang digambar (misal 100.000 titik)
# Ini menjaga PNG tetap tajam tanpa membuat sistem crash.
target_points = 100000
if min_len > target_points:
    step = min_len // target_points
    data_in_plot = data_in[::step]
    data_out_plot = data_out[::step]
    print(f"ℹ️  Optimasi: Downsampling diterapkan (1 setiap {step} sample)")
else:
    data_in_plot = data_in
    data_out_plot = data_out
    step = 1

# Sumbu waktu disesuaikan dengan downsampling
t_axis = np.linspace(0, min_len/fs, len(data_in_plot))

# Perhitungan Level dalam dBFS (Gunakan data hasil downsampling agar hemat memori)
db_in  = 20 * np.log10(np.abs(data_in_plot) + EPS)
db_out = 20 * np.log10(np.abs(data_out_plot) + EPS)

# Estimasi Gain Reduction
observed_gr = db_out - db_in
observed_gr[db_in < -60] = 0 

# =========================================================
# 3. VISUALISASI (3 PANEL)
# =========================================================
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 14), sharex=True)

# --- PANEL 1: WAVEFORM OVERLAY ---
ax1.plot(t_axis, data_in_plot, color='gray', alpha=0.5, label="Input (Original)", linewidth=0.8)
ax1.plot(t_axis, data_out_plot, color='blue', alpha=0.7, label="Hardware Output (DRC)", linewidth=0.8)
ax1.set_title(f"Waveform Comparison: {input_filename}", fontweight='bold', fontsize=14)
ax1.set_ylabel("Amplitude")
ax1.legend(loc='upper right')
ax1.grid(True, alpha=0.3)

# --- PANEL 2: dBFS LEVEL OVERLAY ---
ax2.plot(t_axis, db_in, color='gray', alpha=0.5, label="Input Level (dBFS)", linewidth=0.8)
ax2.plot(t_axis, db_out, color='red', alpha=0.7, label="Output Level (dBFS)", linewidth=0.8)
ax2.set_title("Dynamic Range Comparison (dB Domain)", fontweight='bold', fontsize=14)
ax2.set_ylabel("Level (dBFS)")
ax2.set_ylim([-65, 5])
ax2.legend(loc='upper right')
ax2.grid(True, alpha=0.3)

# --- PANEL 3: ESTIMATED GAIN REDUCTION ---
# Gunakan fill_between untuk visualisasi GR yang lebih intuitif
ax3.fill_between(t_axis, observed_gr, 0, where=(observed_gr < 0.1), 
                 color='green', alpha=0.5, label="Estimated Gain Reduction (dB)")
ax3.set_title("Estimated Gain Reduction Analysis", fontweight='bold', fontsize=14)
ax3.set_ylabel("Reduction (dB)")
ax3.set_xlabel("Time (seconds)")
ax3.set_ylim([min(np.min(observed_gr), -15) - 2, 2])
ax3.grid(True, alpha=0.3)
ax3.legend(loc='upper right')

plt.tight_layout()
# Simpan dengan DPI tinggi untuk hasil PNG yang tajam
plt.savefig(png_output, dpi=300)
plt.close()

print("\n" + "-" * 80)
print(f"🖼️  Grafik Berhasil Dihasilkan: {png_output}")
print("-" * 80)
print(f"✅ Proses Selesai!\n")