# NAMA FILE : kria_karakteristik_dinamis_final.py
import numpy as np
import matplotlib.pyplot as plt
import math
import csv
import os
from pynq import Overlay, allocate

# --- KONFIGURASI HARDWARE ---
BITSTREAM_FILE = "/home/ubuntu/DRC/design_project_drc_1.bit"
DMA_NAME  = "axi_dma_0"
IP_ENV    = "drc_envelope_follower_0"
IP_COMP   = "drc_gain_computer_0"
IP_SMOOTH = "drc_gain_smoothing_0"
IP_APPLY  = "drc_makeup_apply_0"

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
    return math.exp(-math.log(9.0) / (sr * (ms / 1000.0)))

def get_linear_envelope(sig, window=64):
    abs_sig = np.abs(sig)
    env = np.zeros_like(sig)
    for i in range(len(sig)-window):
        env[i+window//2] = np.max(abs_sig[i:i+window])
    return env

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
    print("Overlay & IP Cores: OK")
except Exception as e:
    print(f"Gagal Inisialisasi: {e}")
    exit()

# --- 2. INPUT PARAMETER ---
print("\n" + "="*55)
print("PENGUJIAN 2: KARAKTERISTIK DINAMIS (HARDWARE)")
print("="*55)

def get_input(prompt, default, width=30):
    formatted_prompt = f"{prompt}".ljust(width)
    user_input = input(f"{formatted_prompt} (Default {default}): ").strip()
    return float(user_input) if user_input != "" else default

t_val     = get_input("Threshold (dB)", -20.0)
r_val     = get_input("Ratio", 6.0)
m_val     = get_input("Makeup Gain (dB)", 0.0)
at_env_ms = get_input("Attack Time Env (ms)", 50.0)
rt_env_ms = get_input("Release Time Env (ms)", 100.0)
at_gs_ms  = get_input("Attack Time GS (ms)", 50.0)
rt_gs_ms  = get_input("Release Time GS (ms)", 100.0)

# Modifikasi: Input durasi kustom dalam milidetik (ms)
print("-" * 35)
dur_low1_ms = get_input("Durasi Low 1 (ms)", 50.0)
dur_high_ms = get_input("Durasi High (ms)", 500.0)
dur_low2_ms = get_input("Durasi Low 2 (ms)", 700.0)
print("-" * 35)

# Modifikasi: Kontrol rentang penulisan CSV (Downsampling)
print("[CSV Option]")
csv_step_ms = get_input("Rentang CSV (ms)", 0.15)
csv_hop = max(1, int((csv_step_ms / 1000.0) * FS))
print("-" * 35)

# Update Hardware
ips['env'].write(0x00, to_q30(ms_to_alpha(at_env_ms, FS)))
ips['env'].write(0x04, to_q30(ms_to_alpha(rt_env_ms, FS)))
ips['comp'].write(0x00, to_q30(db_to_linear(t_val)))
ips['comp'].write(0x04, to_q30(1.0/r_val))
ips['smooth'].write(0x00, to_q30(ms_to_alpha(at_gs_ms, FS)))
ips['smooth'].write(0x04, to_q30(ms_to_alpha(rt_gs_ms, FS)))
ips['apply'].write(0x00, to_q30(db_to_linear(m_val)))

# --- 3. GENERASI SINYAL TONE BURST ---
amp_low = 10.0 ** (-40/20) 
amp_high = 10.0 ** (0/20)   

def gen_sine(dur_ms, amp, freq=1000):
    t = np.linspace(0, dur_ms/1000, int((dur_ms/1000) * FS), endpoint=False)
    return np.sin(2 * np.pi * freq * t) * amp

tone_burst = np.concatenate([
    gen_sine(dur_low1_ms, amp_low),
    gen_sine(dur_high_ms, amp_high),
    gen_sine(dur_low2_ms, amp_low)
])

# --- 4. PROSES HARDWARE DMA ---
num_samples = len(tone_burst)
in_buf = allocate(shape=(num_samples,), dtype=np.int16)
out_buf = allocate(shape=(num_samples,), dtype=np.int16)
in_buf[:] = (tone_burst * 32767).astype(np.int16)

dma.recvchannel.transfer(out_buf)
dma.sendchannel.transfer(in_buf)
dma.sendchannel.wait()
dma.recvchannel.wait()

output_lin = out_buf / 32767.0
input_lin = tone_burst

# --- 5. PERHITUNGAN ENVELOPE & GAIN ---
print("\n--- Mengolah Data Visualisasi ---")
env_lin_in = get_linear_envelope(input_lin)
env_lin_out = get_linear_envelope(output_lin)

win = 256 
gr_lin = np.ones_like(output_lin)
last_idx = 0

for i in range(len(output_lin) - win):
    rms_in  = np.sqrt(np.mean(input_lin[i:i+win]**2) + EPS)
    rms_out = np.sqrt(np.mean(output_lin[i:i+win]**2) + EPS)
    current_idx = i + win//2
    gr_lin[current_idx] = rms_out / (rms_in * db_to_linear(m_val) + EPS)
    last_idx = current_idx

gr_lin[last_idx:] = gr_lin[last_idx]
gr_lin[:win//2] = gr_lin[win//2]
gr_lin = np.clip(gr_lin, 0.0, 1.0)
gr_db = 20 * np.log10(gr_lin + EPS)

def get_envelope_db(sig, window=128):
    abs_sig = np.abs(sig)
    env = np.zeros_like(sig)
    last_val = 0
    for i in range(len(sig)-window):
        idx = i + window//2
        env[idx] = np.max(abs_sig[i:i+window])
        last_val = env[idx]
    env[len(sig)-window//2:] = last_val
    env[:window//2] = env[window//2]
    return 20 * np.log10(env + EPS)

input_db_env = get_envelope_db(input_lin)
output_db_env = get_envelope_db(output_lin)

# --- ANALISIS KARAKTERISTIK DINAMIS (HARDWARE) ---
print("\n" + "-"*40)
print("HASIL ANALISIS PARAMETER DINAMIS (HW)")
print("-"*40)

idx_start_high = int(dur_low1_ms / 1000 * FS)
idx_end_high = idx_start_high + int(dur_high_ms / 1000 * FS)

# MODIFIKASI: Pemisahan Toleransi Steady State
TOL_SS_ATK = 0.001 # Toleransi untuk phase Attack
TOL_SS_REL = 0.025  # Toleransi untuk phase Release

# --- ANALISIS ATTACK PHASE ---
gr_steady_atk_target = np.min(gr_db[idx_start_high:idx_end_high])
# Steady State Start: Menggunakan TOL_SS_ATK
idx_ss_atk_start = idx_start_high + np.where(gr_db[idx_start_high:idx_end_high] <= (gr_steady_atk_target + TOL_SS_ATK))[0][0]
t_ss_atk_start = idx_ss_atk_start / FS * 1000
t_ss_atk_end = idx_end_high / FS * 1000

gr_range_atk = 0 - gr_steady_atk_target
target_at_10 = 0 - (0.1 * gr_range_atk)
target_at_90 = 0 - (0.9 * gr_range_atk)

idx_at_10 = idx_start_high + np.where(gr_db[idx_start_high:idx_end_high] <= target_at_10)[0][0]
idx_at_90 = idx_start_high + np.where(gr_db[idx_start_high:idx_end_high] <= target_at_90)[0][0]
t_at_10, gr_at_10 = idx_at_10 / FS * 1000, gr_db[idx_at_10]
t_at_90, gr_at_90 = idx_at_90 / FS * 1000, gr_db[idx_at_90]
measured_attack_ms = t_at_90 - t_at_10

# --- ANALISIS RELEASE PHASE ---
gr_steady_rel_target = 0.0
try:
    # Steady State Start Release: Menggunakan TOL_SS_REL
    idx_ss_rel_start = idx_end_high + np.where(gr_db[idx_end_high:] >= (gr_steady_rel_target - TOL_SS_REL))[0][0]
except IndexError:
    idx_ss_rel_start = len(gr_db) - 1

t_ss_rel_start = idx_ss_rel_start / FS * 1000
t_ss_rel_end = (len(gr_db) / FS) * 1000

target_rel_10 = gr_steady_atk_target + (0.1 * gr_range_atk)
target_rel_90 = gr_steady_atk_target + (0.9 * gr_range_atk)

idx_rel_10 = idx_end_high + np.where(gr_db[idx_end_high:] >= target_rel_10)[0][0]
idx_rel_90 = idx_end_high + np.where(gr_db[idx_end_high:] >= target_rel_90)[0][0]
t_rel_10, gr_rel_10 = idx_rel_10 / FS * 1000, gr_db[idx_rel_10]
t_rel_90, gr_rel_90 = idx_rel_90 / FS * 1000, gr_db[idx_rel_90]
measured_release_ms = t_rel_90 - t_rel_10

print(f"[ATTACK PHASE]")
print(f"1. Steady State Start : {t_ss_atk_start:.5f} ms | GR: {gr_db[idx_ss_atk_start]:.5f} dB")
print(f"   Steady State End   : {t_ss_atk_end:.5f} ms   | GR: {gr_db[idx_end_high-1]:.5f} dB")
print(f"2. 10% Steady State   : t = {t_at_10:.5f} ms    | GR = {gr_at_10:.5f} dB")
print(f"3. 90% Steady State   : t = {t_at_90:.5f} ms    | GR = {gr_at_90:.5f} dB")
print(f"4. ATTACK TIME (sw)   : {measured_attack_ms:.5f} ms")

print(f"\n[RELEASE PHASE]")
print(f"1. Steady State Start : {t_ss_rel_start:.5f} ms | GR: {gr_db[idx_ss_rel_start]:.5f} dB")
print(f"   Steady State End   : {t_ss_rel_end:.5f} ms   | GR: {gr_db[-1]:.5f} dB")
print(f"2. 10% Recovery       : t = {t_rel_10:.5f} ms    | GR = {gr_rel_10:.5f} dB")
print(f"3. 90% Recovery       : t = {t_rel_90:.5f} ms    | GR = {gr_rel_90:.5f} dB")
print(f"4. RELEASE TIME (sw)  : {measured_release_ms:.5f} ms")
print("-" * 40)

# --- 6. VISUALISASI ---
time_axis = np.arange(len(tone_burst)) / FS * 1000 
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12), sharex=True)
props = dict(boxstyle='round', facecolor='white', alpha=0.9)
info_txt = f'T: {t_val}dB | R: {r_val}:1 | M: {m_val}dB\nEnv A/R: {at_env_ms}/{rt_env_ms}ms\nGS A/R: {at_gs_ms}/{rt_gs_ms}ms'

ax1.grid(True, alpha=0.3, zorder=0) 
ax1.fill_between(time_axis, -env_lin_in, env_lin_in, color='gray', alpha=0.3, label='Input (Linear)', zorder=1)
ax1.fill_between(time_axis, -env_lin_out, env_lin_out, color='red', alpha=1.0, label='Output (Linear)', zorder=3)
ax1.axhline(db_to_linear(t_val), color='black', linestyle='--', linewidth=2, label='Threshold', zorder=4)
ax1.set_title("Respon Waktu: Domain Linear (Waveform Envelope)", fontweight='bold')
ax1.set_ylabel("Amplitude"); ax1.set_ylim([-1.1, 1.1]); ax1.legend(loc='upper right')

ax3.grid(True, alpha=0.3, zorder=0)
ax3.fill_between(time_axis, -60, input_db_env, color='gray', alpha=0.3, label='Input Env (dB)', zorder=1)
ax3.fill_between(time_axis, -60, output_db_env, color='blue', alpha=1.0, label='Output Env (dB)', zorder=3)
ax3.axhline(t_val, color='black', linestyle='--', linewidth=2, label='Threshold (dB)', zorder=4)
ax3.set_title("Respon Waktu: Domain Desibel (dB Envelope)", fontweight='bold')
ax3.set_ylabel("Level (dB)"); ax3.set_xlabel("Time (ms)"); ax3.set_ylim([-60, 5]); ax3.legend(loc='upper right')

ax2.grid(True, alpha=0.3)
ax2.plot(time_axis, gr_lin, color='red', linewidth=2.5, zorder=3)
ax2.set_title("Respon Waktu: Gain Reduction (Linear)", fontweight='bold')
ax2.set_ylabel("Factor"); ax2.set_ylim([0, 1.1])

ax4.grid(True, alpha=0.3)
ax4.plot(time_axis, gr_db, color='blue', linewidth=2.5, zorder=3)
ax4.set_title("Respon Waktu: Gain Reduction (dB)", fontweight='bold')
ax4.set_xlabel("Time (ms)"); ax4.set_ylabel("Gain (dB)"); ax4.set_ylim([np.min(gr_db)-5, 5])

ax4.scatter([t_at_10, t_at_90], [gr_at_10, gr_at_90], color='red', zorder=5, label='Atk 10/90%')
ax4.scatter([t_rel_10, t_rel_90], [gr_rel_10, gr_rel_90], color='green', zorder=5, label='Rel 10/90%')
ax4.legend()

ax1.text(0.02, 0.05, info_txt, transform=ax1.transAxes, fontsize=10, 
          verticalalignment='bottom', bbox=props, family='monospace', zorder=5)

plt.tight_layout()
plot_path = os.path.join(base_dir, "grafik_kria_karakteristik_dinamis_final_G3.png")
plt.savefig(plot_path, dpi=300)

# --- 7. EKSPOR CSV ---
csv_path = os.path.join(base_dir, "hasil_uji_kria_karakteristik_dinamis_final_G3.csv")
def format_id(val): return str(round(val, 8)).replace('.', ',')

# Persiapkan Baris Analisis sesuai permintaan (Kolom I, J, K)
analisis_rows = [
    ["Phase", "time (ms)", "Gain Reduction (dB)"],
    ["ATTACK PHASE", "", ""],
    ["Steady State Start", format_id(t_ss_atk_start), format_id(gr_db[idx_ss_atk_start])],
    ["Steady State End", format_id(t_ss_atk_end), format_id(gr_db[idx_end_high-1])],
    ["10% Steady State", format_id(t_at_10), format_id(gr_at_10)],
    ["90% Steady State", format_id(t_at_90), format_id(gr_at_90)],
    ["ATTACK TIME (sw)", format_id(measured_attack_ms), ""],
    ["", "", ""],
    ["RELEASE PHASE", format_id(idx_end_high/FS*1000), format_id(gr_db[idx_end_high])],
    ["Steady State Start", format_id(t_ss_rel_start), format_id(gr_db[idx_ss_rel_start])],
    ["Steady State End", format_id(t_ss_rel_end), format_id(gr_db[-1])],
    ["10% Recovery", format_id(t_rel_10), format_id(gr_rel_10)],
    ["90% Recovery", format_id(t_rel_90), format_id(gr_rel_90)],
    ["Release TIME (sw)", format_id(measured_release_ms), ""]
]

with open(csv_path, mode='w', newline='') as f:
    f.write("sep=;\n")
    writer = csv.writer(f, delimiter=';')
    header = ["Time_ms", "Input_Lin", "Output_Lin", "Gain_Factor_Lin", "Input_dB", "Output_dB", "Gain_Reduction_dB", ""] 
    writer.writerow(header)
    
    idx_sample = 0
    max_idx = len(time_axis)
    analisis_count = len(analisis_rows)
    
    # Menggunakan csv_hop untuk mengatur rentang waktu sampel
    for i in range(0, max_idx, csv_hop):
        row = [
            format_id(time_axis[i]), format_id(input_lin[i]), format_id(output_lin[i]),
            format_id(gr_lin[i]), format_id(input_db_env[i]), format_id(output_db_env[i]), format_id(gr_db[i]),
            "" 
        ]
        if idx_sample < analisis_count:
            row.extend(analisis_rows[idx_sample])
            idx_sample += 1
        writer.writerow(row)

print(f"\n✅ PENGUJIAN SELESAI")
print(f"📁 CSV disimpan di      : {csv_path}")
print(f"🖼️  Grafik diperbarui di : {plot_path}")
print(f"📊 Rentang Penulisan  : {csv_step_ms} ms per baris\n")

# Cleanup
in_buf.freebuffer()
out_buf.freebuffer()
plt.show()