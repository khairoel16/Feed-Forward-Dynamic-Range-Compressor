# linear_karakteristik_statis_final.py
import numpy as np
import matplotlib.pyplot as plt
import math
import csv
import os

# --------------------------------
# 1. ALGORITMA CORE DRC (MODIFIKASI PADA GAIN COMPUTER)
# --------------------------------
EPS = 1e-12

def alpha_time(time_ms, fs):
    if time_ms <= 0: return 0.0
    return math.exp(-math.log(9.0) / (fs * (time_ms / 1000.0)))

def linear_gain_computer(env, T_lin, R):
    """
    Menggunakan rumus dari Kode-2 untuk perbandingan hardware (Verilog).
    G = (T + (env - T)/R) / env
    """
    if env <= T_lin or env <= EPS:
        return 1.0
    else:
        # Rumus Aritmatika Linear (Sama dengan implementasi Fixed-Point di Hardware)
        num = T_lin + ((env - T_lin) / R)
        return num / env

def process_drc_static_ideal(input_samples, fs, p):
    env_state = 0.0
    gs_prev = 1.0
    T_lin = 10.0 ** (p["threshold"] / 20.0)
    M_lin = 10.0 ** (p["makeup"] / 20.0)
    R = p["ratio"]
    aA_env, aR_env = p["alphaA_env"], p["alphaR_env"]
    aA_gs, aR_gs = p["alphaA_gs"], p["alphaR_gs"]
    
    output_samples = np.zeros_like(input_samples)
    gr_history = np.zeros_like(input_samples)
    
    for i, x in enumerate(input_samples):
        ax = abs(x)
        if ax > env_state: env_state = aA_env * env_state + (1.0 - aA_env) * ax
        else: env_state = aR_env * env_state + (1.0 - aR_env) * ax
            
        # Memanggil fungsi gain computer yang sudah diubah ke rumus linear
        gc = linear_gain_computer(env_state, T_lin, R)
        
        if gc < gs_prev: gs_prev = aA_gs * gs_prev + (1.0 - aA_gs) * gc
        else: gs_prev = aR_gs * gs_prev + (1.0 - aR_gs) * gc
            
        gr_history[i] = gs_prev
        output_samples[i] = x * gs_prev * M_lin
        
    return output_samples, gr_history

# --------------------------------
# 2. INPUT PARAMETER (TIDAK BERUBAH)
# --------------------------------
print("") 
print("="*55)
print("PENGUJIAN 1: KARAKTERISTIK STATIS (LINEAR GAIN MODEL)")
print("="*55)

def get_input(prompt, default, width=25):
    formatted_prompt = f"{prompt}".ljust(width)
    user_input = input(f"{formatted_prompt} (Default {default}): ").strip()
    return float(user_input) if user_input != "" else default

fs = 48000
t_db      = get_input("Threshold (dB)", -20.0)
r_val     = get_input("Ratio", 4.0)
m_db      = get_input("Makeup Gain (dB)", 0.0)
at_env_ms = get_input("Attack Time Env (ms)", 5.0)
rt_env_ms = get_input("Release Time Env (ms)", 50.0)
at_gs_ms  = get_input("Attack Time GS (ms)", 10.0)
rt_gs_ms  = get_input("Release Time GS (ms)", 100.0)

test_params = {
    "threshold": t_db, "ratio": r_val, "makeup": m_db,
    "alphaA_env": alpha_time(at_env_ms, fs),
    "alphaR_env": alpha_time(rt_env_ms, fs),
    "alphaA_gs":  alpha_time(at_gs_ms, fs),
    "alphaR_gs":  alpha_time(rt_gs_ms, fs)
}

# --------------------------------
# 3. PROSES SIMULASI (MODIFIKASI UNTUK MENGHAPUS -60dB)
# --------------------------------
num_steps = 100
# Mengambil indeks dari 1 sampai akhir agar -60dB (indeks 0) tidak diikutkan
test_levels_db = np.linspace(-60, 0, num_steps)[1:]
test_levels_lin = 10.0 ** (test_levels_db / 20.0)

res_out_lin, res_out_db, res_gr_lin, res_gr_db = [], [], [], []

print("\n[Process] Calculating Static Characteristics...")
for amp in test_levels_lin:
    chunk = np.ones(int(fs * 0.2)) * amp 
    processed, gr_vec = process_drc_static_ideal(chunk, fs, test_params)
    out_val_lin, gr_final = abs(processed[-1]), gr_vec[-1]
    
    res_out_lin.append(out_val_lin)
    res_out_db.append(20 * math.log10(max(out_val_lin, EPS)))
    res_gr_lin.append(gr_final)
    res_gr_db.append(20 * math.log10(max(gr_final, EPS)))

# --------------------------------
# 4. VISUALISASI QUAD-PLOT (TIDAK BERUBAH)
# --------------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
plt.subplots_adjust(hspace=0.3, wspace=0.2)

ax1.plot([0, 1], [0, 1], '--', color='gray', label='Ideal (1:1)')
ax1.plot(test_levels_lin, res_out_lin, 'g-', linewidth=2, label='Golden Output')
ax1.axvline(10**(t_db/20), color='black', linestyle=':', label='Threshold')
ax1.set_title("Karakteristik I/O (Linear)", fontweight='bold')
ax1.set_xlabel("Input Amplitude"); ax1.set_ylabel("Output Amplitude")
ax1.grid(True, alpha=0.3); ax1.legend()

ax2.plot(test_levels_db, test_levels_db, '--', color='gray', label='Ideal (1:1)')
ax2.plot(test_levels_db, res_out_db, 'b-', linewidth=2, label='Golden Output')
ax2.axvline(t_db, color='black', linestyle=':', label='Threshold')
ax2.set_title("Karakteristik I/O (Desibel)", fontweight='bold')
ax2.set_xlabel("Input Level (dBFS)"); ax2.set_ylabel("Output Level (dBFS)")
ax2.set_xlim([-60, 5]); ax2.set_ylim([-60, 5])
ax2.grid(True, alpha=0.3); ax2.legend()

ax3.plot(test_levels_lin, res_gr_lin, 'r-', linewidth=2, label='Gain Multiplier')
ax3.axvline(10**(t_db/20), color='black', linestyle=':')
ax3.set_title("Gain Factor (Linear)", fontweight='bold')
ax3.set_xlabel("Input Amplitude"); ax3.set_ylabel("Factor")
ax3.set_ylim([0, 1.1])
ax3.grid(True, alpha=0.3); ax3.legend()

ax4.plot(test_levels_db, res_gr_db, 'r-', linewidth=2, label='Gain Reduction (dB)')
ax4.axvline(t_db, color='black', linestyle=':')
ax4.set_title("Gain Reduction (Desibel)", fontweight='bold')
ax4.set_xlabel("Input Level (dBFS)"); ax4.set_ylabel("Gain (dB)")
ax4.set_ylim([min(res_gr_db)-5, 5])
ax4.grid(True, alpha=0.3); ax4.legend()

fig.suptitle(f"Karakteristik Statis DRC Golden Model (Linear Formula)\nT:{t_db}dB, R:{r_val}:1, M:{m_db}dB", fontsize=11, fontweight='bold')

plot_path = os.path.join(base_dir, "grafik_golden_karakteristik_statis_final_c5.png")
plt.savefig(plot_path, dpi=250)

# --------------------------------
# 5. EKSPOR CSV (TIDAK BERUBAH)
# --------------------------------
csv_path = os.path.join(base_dir, "hasil_uji_golden_karakteristik_statis_final_c5.csv")
with open(csv_path, mode='w', newline='') as f:
    writer = csv.writer(f, delimiter=';')
    writer.writerow(["Input_dB", "Output_dB", "Gain_Reduction_dB"])
    for i in range(len(test_levels_db)):
        writer.writerow([
            str(round(test_levels_db[i], 4)).replace('.',','), 
            str(round(res_out_db[i], 4)).replace('.',','), 
            str(round(res_gr_db[i], 4)).replace('.',',')
        ])

print("\n" + "="*45)
print("✅ SIMULASI SELESAI")
print(f"📁 Lokasi File CSV    : {csv_path}")
print(f"🖼️  Lokasi Grafik PNG  : {plot_path}")
print("="*45 + "\n")

plt.show()