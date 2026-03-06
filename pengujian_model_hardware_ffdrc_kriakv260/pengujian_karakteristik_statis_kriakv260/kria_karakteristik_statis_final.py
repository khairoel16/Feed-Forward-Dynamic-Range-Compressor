# NAMA FILE : kria_karakteristik_statis_final.py
import numpy as np
import matplotlib.pyplot as plt
import math
import csv
import os
from pynq import Overlay, allocate

# --- KONFIGURASI HARDWARE ---
BITSTREAM_FILE = "/home/ubuntu/DRC/design_project_drc_1.bit"
DMA_NAME       = "axi_dma_0"
IP_ENV         = "drc_envelope_follower_0"
IP_COMP        = "drc_gain_computer_0"
IP_SMOOTH      = "drc_gain_smoothing_0"
IP_APPLY       = "drc_makeup_apply_0"

ONE_Q30 = 1 << 30
FS = 48000
EPS = 1e-12

def to_q30(x):
    val = int(x * ONE_Q30)
    return int(np.clip(val, -2147483648, 2147483647))

def db_to_linear(db):
    return 10**(db/20)

def ms_to_alpha(ms, sr):
    if ms <= 0: return 0.0
    # Menggunakan rumus exponential decay log(9) agar sesuai dengan pengujian dinamis
    return math.exp(-math.log(9.0) / (sr * (ms / 1000.0)))

# Direktori kerja otomatis
base_dir = os.path.dirname(os.path.abspath(__file__))

# --- 1. INISIALISASI HARDWARE ---
print("\n--- Menginisialisasi FPGA ---")
try:
    overlay = Overlay(BITSTREAM_FILE)
    dma = getattr(overlay, DMA_NAME)
    ips = {
        'env': getattr(overlay, IP_ENV),
        'comp': getattr(overlay, IP_COMP),
        'smooth': getattr(overlay, IP_SMOOTH),
        'apply': getattr(overlay, IP_APPLY)
    }
    print("\nOverlay & IP Cores: OK")
except Exception as e:
    print(f"Gagal Inisialisasi: {e}")
    exit()

# --- 2. INPUT PARAMETER (7 PARAMETER LENGKAP) ---
print("\n" + "="*50)
print("PENGUJIAN 1: KARAKTERISTIK STATIS (HARDWARE)")
print("="*50)

t_db      = float(input("Threshold (dB) [-20.0]         => ") or -20.0)
r_val     = float(input("Ratio [4.0]                   => ") or 4.0)
m_db      = float(input("Makeup Gain (dB) [0.0]        => ") or 0.0)
at_env_ms = float(input("Attack Time Env (ms) [5.0]    => ") or 5.0)
rt_env_ms = float(input("Release Time Env (ms) [50.0]  => ") or 50.0)
at_gs_ms  = float(input("Attack Time GS (ms) [10.0]    => ") or 10.0)
rt_gs_ms  = float(input("Release Time GS (ms) [100.0]  => ") or 100.0)

# Konversi dan Update Register Hardware
ips['env'].write(0x00, to_q30(ms_to_alpha(at_env_ms, FS)))
ips['env'].write(0x04, to_q30(ms_to_alpha(rt_env_ms, FS)))
ips['comp'].write(0x00, to_q30(db_to_linear(t_db)))
ips['comp'].write(0x04, to_q30(1.0/r_val))
ips['smooth'].write(0x00, to_q30(ms_to_alpha(at_gs_ms, FS)))
ips['smooth'].write(0x04, to_q30(ms_to_alpha(rt_gs_ms, FS)))
ips['apply'].write(0x00, to_q30(db_to_linear(m_db)))

# --- 3. PROSES PENGUJIAN (MODIFIKASI UNTUK MENGHAPUS -60dB) ---
num_steps = 100
# Mengambil indeks dari 1 sampai akhir agar -60dB (indeks 0) tidak diikutkan
test_levels_db = np.linspace(-60, 0, num_steps)[1:]
test_levels_lin = 10.0 ** (test_levels_db / 20.0)

# Buffer besar (16384) untuk memastikan hardware mencapai steady-state
CHUNK_SIZE = 16384 
in_buf = allocate(shape=(CHUNK_SIZE,), dtype=np.int16)
out_buf = allocate(shape=(CHUNK_SIZE,), dtype=np.int16)

res_out_lin = []
res_out_db = []
res_gr_lin = []
res_gr_db = []

print("\n--- Memproses Data via Hardware DMA ---")
for amp in test_levels_lin:
    in_buf[:] = np.full(CHUNK_SIZE, int(amp * 32767), dtype=np.int16)
    
    dma.recvchannel.transfer(out_buf)
    dma.sendchannel.transfer(in_buf)
    dma.sendchannel.wait()
    dma.recvchannel.wait()
    
    # Ambil sampel absolut terakhir (nilai statis)
    out_val_lin = abs(out_buf[-1]) / 32767.0
    # Gain factor = Output / (Input * Makeup)
    gr_factor_lin = out_val_lin / (max(amp, EPS) * db_to_linear(m_db))
    
    res_out_lin.append(out_val_lin)
    res_out_db.append(20 * math.log10(max(out_val_lin, EPS)))
    res_gr_lin.append(gr_factor_lin)
    res_gr_db.append(20 * math.log10(max(gr_factor_lin, EPS)))

# --- 4. VISUALISASI QUAD-PLOT (2x2) ---
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
plt.subplots_adjust(hspace=0.3, wspace=0.2)

# Plot 1: Karakteristik I/O (Linear)
ax1.plot([0, 1], [0, 1], '--', color='gray', label='Ideal (1:1)')
ax1.plot(test_levels_lin, res_out_lin, 'g-', linewidth=2, label='Hardware Output')
ax1.axvline(db_to_linear(t_db), color='black', linestyle=':', label='Threshold')
ax1.set_title("Karakteristik I/O (Linear)", fontweight='bold')
ax1.set_xlabel("Input Amplitude"); ax1.set_ylabel("Output Amplitude")
ax1.grid(True, alpha=0.3); ax1.legend()

# Plot 2: Karakteristik I/O (Desibel)
ax2.plot(test_levels_db, test_levels_db, '--', color='gray', label='Ideal (1:1)')
ax2.plot(test_levels_db, res_out_db, 'b-', linewidth=2, label='Hardware Output')
ax2.axvline(t_db, color='black', linestyle=':', label='Threshold')
ax2.set_title("Karakteristik I/O (Desibel)", fontweight='bold')
ax2.set_xlabel("Input Level (dBFS)"); ax2.set_ylabel("Output Level (dBFS)")
ax2.set_xlim([-60, 5]); ax2.set_ylim([-60, 5])
ax2.grid(True, alpha=0.3); ax2.legend()

# Plot 3: Gain Factor (Linear)
ax3.plot(test_levels_lin, res_gr_lin, 'r-', linewidth=2, label='Gain Multiplier')
ax3.axvline(db_to_linear(t_db), color='black', linestyle=':')
ax3.set_title("Gain Factor (Linear)", fontweight='bold')
ax3.set_xlabel("Input Amplitude"); ax3.set_ylabel("Factor")
ax3.set_ylim([0, 1.1])
ax3.grid(True, alpha=0.3); ax3.legend()

# Plot 4: Gain Reduction (Desibel)
ax4.plot(test_levels_db, res_gr_db, 'r-', linewidth=2, label='Gain Reduction (dB)')
ax4.axvline(t_db, color='black', linestyle=':')
ax4.set_title("Gain Reduction (Desibel)", fontweight='bold')
ax4.set_xlabel("Input Level (dBFS)"); ax4.set_ylabel("Gain (dB)")
ax4.set_ylim([min(res_gr_db)-5, 5])
ax4.grid(True, alpha=0.3); ax4.legend()

fig.suptitle(f"Karakteristik Statis DRC Hardware\nT:{t_db}dB, R:{r_val}:1, M:{m_db}dB", fontsize=16, fontweight='bold')

plot_path = os.path.join(base_dir, "grafik_kria_karakteristik_statis_final_C5.png")
plt.savefig(plot_path, dpi=250)

# --- 5. EKSPOR CSV ---
csv_path = os.path.join(base_dir, "hasil_uji_kria_karakteristik_statis_final_C5.csv")
with open(csv_path, mode='w', newline='') as f:
    writer = csv.writer(f, delimiter=';')
    writer.writerow(["Input_dB", "Output_dB", "Gain_Reduction_dB"])
    for i in range(len(test_levels_db)):
        writer.writerow([
            str(round(test_levels_db[i], 4)).replace('.',','), 
            str(round(res_out_db[i], 4)).replace('.',','), 
            str(round(res_gr_db[i], 4)).replace('.',',')
        ])

print(f"\n✅ PENGUJIAN SELESAI")
print(f"📁 CSV disimpan di              : {csv_path}")
print(f"🖼️  Grafik Quad-Plot disimpan di : {plot_path}\n")

# Cleanup
in_buf.freebuffer()
out_buf.freebuffer()