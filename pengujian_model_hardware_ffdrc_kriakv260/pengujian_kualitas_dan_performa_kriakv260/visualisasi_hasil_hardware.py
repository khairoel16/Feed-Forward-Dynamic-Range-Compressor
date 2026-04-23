# visualisasi_hasil_hardware.py
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
root.withdraw()  # Sembunyikan jendela utama tkinter

print("\n" + "="*80)
print("--- VISUALISASI PERBANDINGAN HARDWARE VS INPUT ---")
print("="*80)

# Instruksi dan Pilih File Input (Original)
print("[Step 1] Pilih file audio WAV INPUT (Original)...")
file_input = filedialog.askopenfilename(
    title="Pilih File Audio INPUT (Original)", 
    filetypes=[("WAV files", "*.wav")]
)
if not file_input:
    print("❌ Error: Pemilihan file input dibatalkan.")
    exit()
print(f"✅ File Input Masuk: {file_input}")

# Instruksi dan Pilih File Output (Hasil Hardware)
print("\n[Step 2] Pilih file audio WAV OUTPUT (Hardware/DRC)...")
file_output = filedialog.askopenfilename(
    title="Pilih File Audio OUTPUT (Hardware/DRC)", 
    filetypes=[("WAV files", "*.wav")]
)
if not file_output:
    print("❌ Error: Pemilihan file output dibatalkan.")
    exit()
print(f"✅ File Output Masuk: {file_output}")

# Konfigurasi Path Penyimpanan (Sama dengan direktori script ini)
script_dir = os.path.dirname(os.path.abspath(__file__))
input_filename = os.path.splitext(os.path.basename(file_input))[0]
png_output = os.path.join(script_dir, f"{input_filename}_grafik.png")

EPS = 1e-12

# =========================================================
# 2. LOAD DATA & PRE-PROCESSING
# =========================================================
data_in, fs = sf.read(file_input)
data_out, fs_out = sf.read(file_output)

# Samakan panjang data jika ada selisih sedikit akibat proses hardware/DMA
min_len = min(len(data_in), len(data_out))
data_in = data_in[:min_len]
data_out = data_out[:min_len]

t_axis = np.linspace(0, len(data_in)/fs, len(data_in))

# Perhitungan Level dalam dBFS
db_in  = 20 * np.log10(np.abs(data_in) + EPS)
db_out = 20 * np.log10(np.abs(data_out) + EPS)

# Estimasi Gain Reduction (Observed Gain Change)
observed_gr = db_out - db_in
observed_gr[db_in < -60] = 0 

# =========================================================
# 3. VISUALISASI (3 PANEL)
# =========================================================
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 14), sharex=True)

# --- PANEL 1: WAVEFORM OVERLAY ---
ax1.plot(t_axis, data_in, color='gray', alpha=0.7, label="Input (Original)")
ax1.plot(t_axis, data_out, color='blue', alpha=0.7, label="Hardware Output (DRC)")
ax1.set_title(f"Waveform Comparison: {input_filename}", fontweight='bold')
ax1.set_ylabel("Amplitude")
ax1.legend(loc='upper right')
ax1.grid(True, alpha=0.2)

# --- PANEL 2: dBFS LEVEL OVERLAY ---
ax2.plot(t_axis, db_in, color='gray', alpha=0.7, label="Input Level (dBFS)")
ax2.plot(t_axis, db_out, color='red', alpha=0.7, label="Output Level (dBFS)")
ax2.set_title("Dynamic Range Comparison (dB Domain)", fontweight='bold')
ax2.set_ylabel("Level (dBFS)")
ax2.set_ylim([-60, 5])
ax2.legend(loc='upper right')
ax2.grid(True, alpha=0.2)

# --- PANEL 3: ESTIMATED GAIN REDUCTION ---
ax3.fill_between(t_axis, observed_gr, 0, where=(observed_gr < 0.1), 
                 color='green', alpha=0.4, label="Estimated Gain Reduction (dB)")
ax3.set_title("Estimated Gain Reduction Analysis", fontweight='bold')
ax3.set_ylabel("Reduction (dB)")
ax3.set_xlabel("Time (seconds)")
ax3.set_ylim([min(np.min(observed_gr), -10) - 2, 2])
ax3.grid(True, alpha=0.2)
ax3.legend(loc='upper right')

plt.tight_layout()
plt.savefig(png_output, dpi=300)
plt.close() # Menutup plot agar tidak muncul jendela pop-up

print("\n" + "-" * 80)
print(f"🖼️  Grafik Berhasil Dihasilkan: {png_output}")
print("-" * 80)
print(f"✅ Proses Selesai!\n")