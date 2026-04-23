# linear_karakteristik_dinamis_final.py
import numpy as np
import matplotlib.pyplot as plt
import math
import csv
import os

# --------------------------------
# 1. CORE DRC ENGINE (MODIFIKASI PADA GAIN COMPUTER)
# --------------------------------
EPS = 1e-12

def alpha_time(time_ms, fs):
    if time_ms <= 0: return 0.0
    return math.exp(-math.log(9.0) / (fs * (time_ms / 1000.0)))

def linear_gain_computer(env, T_lin, R):
    """
    MODIFIKASI: Menggunakan rumus Linear sesuai arsitektur Hardware/Verilog.
    G = (T + (env - T)/R) / env
    """
    if env <= T_lin or env <= EPS:
        return 1.0
    # Rumus linear untuk mempermudah implementasi fixed-point di Verilog
    num = T_lin + ((env - T_lin) / R)
    return num / env

def process_drc_dynamic(input_samples, fs, p):
    env_state = 0.0
    gs_prev = 1.0
    T_lin = 10.0 ** (p["threshold"] / 20.0)
    M_lin = 10.0 ** (p["makeup"] / 20.0)
    R = p["ratio"]
    aA_env, aR_env = p["alphaA_env"], p["alphaR_env"]
    aR_env_val = p["alphaR_env"] # Keep original reference
    aA_gs, aR_gs = p["alphaA_gs"], p["alphaR_gs"]
    
    output_samples = np.zeros_like(input_samples)
    gr_history = np.zeros_like(input_samples)
    
    for i, x in enumerate(input_samples):
        ax = abs(x)
        # Envelope follower
        if ax > env_state: env_state = aA_env * env_state + (1.0 - aA_env) * ax
        else: env_state = aR_env * env_state + (1.0 - aR_env) * ax
        
        # Menggunakan fungsi gain computer linear
        gc = linear_gain_computer(env_state, T_lin, R)
        
        # Gain smoothing
        if gc < gs_prev: gs_prev = aA_gs * gs_prev + (1.0 - aA_gs) * gc
        else: gs_prev = aR_gs * gs_prev + (1.0 - aR_gs) * gc
            
        gr_history[i] = gs_prev
        output_samples[i] = x * gs_prev * M_lin
    return output_samples, gr_history

# Helper untuk Envelope Visualisasi (Tetap sama)
def get_linear_envelope(sig, window=64):
    abs_sig = np.abs(sig)
    env = np.zeros_like(sig)
    for i in range(len(sig)-window):
        env[i+window//2] = np.max(abs_sig[i:i+window])
    env[:window//2] = env[window//2]
    env[len(sig)-window//2:] = env[len(sig)-window//2-1]
    return env

def get_envelope_db(sig, window=128):
    env_lin = get_linear_envelope(sig, window)
    return 20 * np.log10(env_lin + EPS)

# --------------------------------
# 2. INPUT PARAMETER (FORMAT KONSOL RAPI)
# --------------------------------
print("\n" + "="*55)
print("PENGUJIAN 2: KARAKTERISTIK DINAMIS (LINEAR MODEL)")
print("="*55)

def get_input(prompt, default, width=25):
    formatted_prompt = f"{prompt}".ljust(width)
    user_input = input(f"{formatted_prompt} (Default {default}): ").strip()
    return float(user_input) if user_input != "" else default

fs = 48000
t_val     = get_input("Threshold (dB)", -20.0)
r_val     = get_input("Ratio", 6.0)
m_val     = get_input("Makeup Gain (dB)", 0.0)
at_env_ms = get_input("Attack Time Env (ms)", 50.0)
rt_env_ms = get_input("Release Time Env (ms)", 100.0)
at_gs_ms  = get_input("Attack Time GS (ms)", 50.0)
rt_gs_ms  = get_input("Release Time GS (ms)", 100.0)

# Modifikasi: Input durasi kustom dalam milidetik (ms)
print("-" * 30)
dur_low1_ms = get_input("Durasi Low 1 (ms)", 50.0)
dur_high_ms = get_input("Durasi High (ms)", 500.0)
dur_low2_ms = get_input("Durasi Low 2 (ms)", 700.0)
print("-" * 30)

# Modifikasi: Kontrol rentang penulisan CSV (Downsampling)
print("[CSV Option]")
csv_step_ms = get_input("Rentang CSV (ms)", 0.15)
# Menghitung hop/step indeks berdasarkan ms yang diinginkan
csv_hop = max(1, int((csv_step_ms / 1000.0) * fs))
print("-" * 30)

params = {
    "threshold": t_val, "ratio": r_val, "makeup": m_val,
    "alphaA_env": alpha_time(at_env_ms, fs), "alphaR_env": alpha_time(rt_env_ms, fs),
    "alphaA_gs":  alpha_time(at_gs_ms, fs),  "alphaR_gs":  alpha_time(rt_gs_ms, fs)
}

# --------------------------------
# 3. GENERASI SINYAL TONE BURST (MODIFIKASI DURASI KUSTOM)
# --------------------------------
amp_low = 10.0 ** (-40/20) 
amp_high = 10.0 ** (0/20)   

def gen_sine(dur_ms, amp, freq=1000):
    t = np.linspace(0, dur_ms/1000, int((dur_ms/1000) * fs), endpoint=False)
    return np.sin(2 * np.pi * freq * t) * amp

tone_burst = np.concatenate([
    gen_sine(dur_low1_ms, amp_low),
    gen_sine(dur_high_ms, amp_high),
    gen_sine(dur_low2_ms, amp_low)
])

# --------------------------------
# 4. PROSES SIMULASI
# --------------------------------
print("\n[Process] Calculating Dynamic Response (Linear Formula)...")
output, gr_lin = process_drc_dynamic(tone_burst, fs, params)

input_lin = tone_burst
env_lin_in = get_linear_envelope(input_lin)
env_lin_out = get_linear_envelope(output)
input_db_env = get_envelope_db(input_lin)
output_db_env = get_envelope_db(output)
gr_db = 20 * np.log10(gr_lin + EPS)

# --------------------------------
# ANALISIS KARAKTERISTIK DINAMIS
# --------------------------------
print("\n" + "-"*40)
print("HASIL ANALISIS PARAMETER DINAMIS")
print("-"*40)

# Identifikasi Index Transisi
idx_start_high = int(dur_low1_ms / 1000 * fs)
idx_end_high = idx_start_high + int(dur_high_ms / 1000 * fs)

# MODIFIKASI: Pemisahan Toleransi Steady State agar 1:1 dengan Hardware
TOL_SS_ATK = 0.001 
TOL_SS_REL = 0.025 

# --- ANALISIS ATTACK PHASE ---
gr_steady_atk_target = np.min(gr_db[idx_start_high:idx_end_high])
# Steady State Start: Menggunakan TOL_SS_ATK
idx_ss_atk_start = idx_start_high + np.where(gr_db[idx_start_high:idx_end_high] <= (gr_steady_atk_target + TOL_SS_ATK))[0][0]
t_ss_atk_start = idx_ss_atk_start / fs * 1000
t_ss_atk_end = idx_end_high / fs * 1000

gr_range_atk = 0 - gr_steady_atk_target
target_at_10 = 0 - (0.1 * gr_range_atk)
target_at_90 = 0 - (0.9 * gr_range_atk)

idx_at_10 = idx_start_high + np.where(gr_db[idx_start_high:idx_end_high] <= target_at_10)[0][0]
idx_at_90 = idx_start_high + np.where(gr_db[idx_start_high:idx_end_high] <= target_at_90)[0][0]
t_at_10, gr_at_10 = idx_at_10 / fs * 1000, gr_db[idx_at_10]
t_at_90, gr_at_90 = idx_at_90 / fs * 1000, gr_db[idx_at_90]
measured_attack_ms = t_at_90 - t_at_10

# --- ANALISIS RELEASE PHASE ---
gr_steady_rel_target = 0.0
try:
    # Steady State Start Release: Menggunakan TOL_SS_REL
    idx_ss_rel_start = idx_end_high + np.where(gr_db[idx_end_high:] >= (gr_steady_rel_target - TOL_SS_REL))[0][0]
except IndexError:
    idx_ss_rel_start = len(gr_db) - 1

t_ss_rel_start = idx_ss_rel_start / fs * 1000
t_ss_rel_end = (len(gr_db) / fs) * 1000

target_rel_10 = gr_steady_atk_target + (0.1 * gr_range_atk)
target_rel_90 = gr_steady_atk_target + (0.9 * gr_range_atk)

idx_rel_10 = idx_end_high + np.where(gr_db[idx_end_high:] >= target_rel_10)[0][0]
idx_rel_90 = idx_end_high + np.where(gr_db[idx_end_high:] >= target_rel_90)[0][0]
t_rel_10, gr_rel_10 = idx_rel_10 / fs * 1000, gr_db[idx_rel_10]
t_rel_90, gr_rel_90 = idx_rel_90 / fs * 1000, gr_db[idx_rel_90]
measured_release_ms = t_rel_90 - t_rel_10

# Format Output dengan 5 angka di belakang koma (:.5f)
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

# --------------------------------
# 5. VISUALISASI (PLOT DINAMIS)
# --------------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
time_axis = np.arange(len(tone_burst)) / fs * 1000 
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12), sharex=True)
props = dict(boxstyle='round', facecolor='white', alpha=0.9)
info_txt = f'T: {t_val}dB | R: {r_val}:1 | M: {m_val}dB\nEnv A/R: {at_env_ms}/{rt_env_ms}ms\nGS A/R: {at_gs_ms}/{rt_gs_ms}ms'

# Plot 1: Domain Linear
ax1.grid(True, alpha=0.3, zorder=0) 
ax1.fill_between(time_axis, -env_lin_in, env_lin_in, color='gray', alpha=0.3, label='Input (Linear)', zorder=1)
ax1.fill_between(time_axis, -env_lin_out, env_lin_out, color='red', alpha=1.0, label='Linear Output (Linear)', zorder=3)
ax1.axhline(10**(t_val/20), color='black', linestyle='--', linewidth=2, label='Threshold', zorder=4)
ax1.set_title("Respon Waktu: Domain Linear (Formula Linear)", fontweight='bold')
ax1.set_ylabel("Amplitude"); ax1.set_ylim([-1.1, 1.1]); ax1.legend(loc='upper right')

# Plot 3: Domain DB
ax3.grid(True, alpha=0.3, zorder=0)
ax3.fill_between(time_axis, -60, input_db_env, color='gray', alpha=0.3, label='Input Env (dB)', zorder=1)
ax3.fill_between(time_axis, -60, output_db_env, color='blue', alpha=1.0, label='Linear Output Env (dB)', zorder=3)
ax3.axhline(t_val, color='black', linestyle='--', linewidth=2, label='Threshold (dB)', zorder=4)
ax3.set_title("Respon Waktu: Domain Desibel (dB Envelope)", fontweight='bold')
ax3.set_ylabel("Level (dB)"); ax3.set_xlabel("Time (ms)"); ax3.set_ylim([-60, 5]); ax3.legend(loc='upper right')

# Plot 2: Gain Reduction Linear
ax2.grid(True, alpha=0.3)
ax2.plot(time_axis, gr_lin, color='red', linewidth=2.5, zorder=3)
ax2.set_title("Respon Waktu: Gain Reduction (Linear)", fontweight='bold')
ax2.set_ylabel("Factor"); ax2.set_ylim([0, 1.1])

# Plot 4: Gain Reduction dB
ax4.grid(True, alpha=0.3)
ax4.plot(time_axis, gr_db, color='blue', linewidth=2.5, zorder=3)
ax4.set_title("Respon Waktu: Gain Reduction (dB)", fontweight='bold')
ax4.set_xlabel("Time (ms)"); ax4.set_ylabel("Gain (dB)"); ax4.set_ylim([np.min(gr_db)-5, 5])

# Marker Tambahan pada Plot 4 untuk visualisasi t10 dan t90
ax4.scatter([t_at_10, t_at_90], [gr_at_10, gr_at_90], color='red', zorder=5, label='Atk 10/90%')
ax4.scatter([t_rel_10, t_rel_90], [gr_rel_10, gr_rel_90], color='green', zorder=5, label='Rel 10/90%')
ax4.legend()

ax1.text(0.02, 0.05, info_txt, transform=ax1.transAxes, fontsize=10, 
          verticalalignment='bottom', bbox=props, family='monospace', zorder=5)

plt.tight_layout()
plot_path = os.path.join(base_dir, "grafik_linear_karakteristik_dinamis_final_g3.png")
plt.savefig(plot_path, dpi=300)

# --------------------------------
# 6. EKSPOR CSV
# --------------------------------
csv_path = os.path.join(base_dir, "hasil_uji_linear_karakteristik_dinamis_final_g3.csv")
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
    ["RELEASE PHASE", format_id(idx_end_high/fs*1000), format_id(gr_db[idx_end_high])],
    ["Steady State Start", format_id(t_ss_rel_start), format_id(gr_db[idx_ss_rel_start])],
    ["Steady State End", format_id(t_ss_rel_end), format_id(gr_db[-1])],
    ["10% Recovery", format_id(t_rel_10), format_id(gr_rel_10)],
    ["90% Recovery", format_id(t_rel_90), format_id(gr_rel_90)],
    ["Release TIME (sw)", format_id(measured_release_ms), ""]
]

with open(csv_path, mode='w', newline='') as f:
    f.write("sep=;\n")
    writer = csv.writer(f, delimiter=';')
    
    # Header utama (A-G) + H kosong + Header Analisis (I-K)
    header = ["Time_ms", "Input_Lin", "Output_Lin", "Gain_Factor_Lin", "Input_dB", "Output_dB", "Gain_Reduction_dB", ""] 
    writer.writerow(header)
    
    idx_sample = 0
    max_idx = len(time_axis)
    analisis_count = len(analisis_rows)
    
    # MODIFIKASI: Loop menggunakan csv_hop untuk mengatur rentang waktu sampel
    for i in range(0, max_idx, csv_hop):
        # Data Sampel Utama
        row = [
            format_id(time_axis[i]), format_id(input_lin[i]), format_id(output[i]),
            format_id(gr_lin[i]), format_id(input_db_env[i]), format_id(output_db_env[i]), format_id(gr_db[i]),
            "" 
        ]
        
        # Tambahkan data analisis di kolom I, J, K
        if idx_sample < analisis_count:
            row.extend(analisis_rows[idx_sample])
            idx_sample += 1
            
        writer.writerow(row)

print("\n" + "="*45)
print("✅ SIMULASI SELESAI")
print(f"📁 Lokasi File CSV    : {csv_path}")
print(f"🖼️  Lokasi Grafik PNG  : {plot_path}")
print(f"📊 Rentang Penulisan  : {csv_step_ms} ms per baris")
print("="*45 + "\n")

plt.show()