# pengujian_software_wav_drc.py
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import soundfile as sf
import pyloudnorm as pyln
import math
import csv
import os
import time
from tkinter import filedialog, Tk

# Menggunakan backend Agg untuk pemrosesan grafik tanpa antarmuka GUI (Headless)
matplotlib.use('Agg')

# =========================================================
# 1. ALGORITMA DRC (LINEAR MODEL UNTUK IMPLEMENTASI HARDWARE)
# =========================================================
EPS = 1e-12

def alpha_time(time_ms, fs):
    """Menghitung koefisien filter berdasarkan waktu (ms) dan sample rate"""
    if time_ms <= 0: return 0.0
    return math.exp(-math.log(9.0) / (fs * (time_ms / 1000.0)))

def linear_gain_computer(env, T_lin, R):
    """Menghitung faktor penguatan (Gain) pada domain linear"""
    if env <= T_lin or env <= EPS:
        return 1.0
    num = T_lin + ((env - T_lin) / R)
    return num / env

def process_drc_audio_linear(input_samples, fs, p):
    """Simulasi pemrosesan DRC Feed-Forward pada domain linear"""
    env_state = 0.0
    gs_prev = 1.0
    T_lin = 10.0 ** (p["threshold"] / 20.0)
    M_lin = 10.0 ** (p["makeup"] / 20.0)
    R = p["ratio"]
    aA_env, aR_env = p["alphaA_env"], p["alphaR_env"]
    aA_gs, aR_gs   = p["alphaA_gs"],  p["alphaR_gs"]

    output = np.zeros_like(input_samples)
    gr_history = np.zeros_like(input_samples)
    
    # Pencatatan waktu eksekusi perangkat lunak
    start_time = time.perf_counter()
    
    for i, x in enumerate(input_samples):
        ax = abs(x)
        # Jalur Envelope Detector
        if ax > env_state:
            env_state = aA_env * env_state + (1 - aA_env) * ax
        else:
            env_state = aR_env * env_state + (1 - aR_env) * ax
        
        # Jalur Gain Computer
        gc = linear_gain_computer(env_state, T_lin, R)
        
        # Jalur Gain Smoothing
        if gc < gs_prev:
            gs_prev = aA_gs * gs_prev + (1 - aA_gs) * gc
        else:
            gs_prev = aR_gs * gs_prev + (1 - aR_gs) * gc
        
        gr_history[i] = gs_prev
        # Penerapan Gain dan Makeup Gain
        raw_output = x * gs_prev * M_lin
        # Simulasi Hard Clipping pada batas PCM 16-bit
        output[i] = np.clip(raw_output, -1.0, 1.0)
    
    end_time = time.perf_counter()
    software_exec_ms = (end_time - start_time) * 1000
    
    return output, gr_history, software_exec_ms

# =========================================================
# 2. PEMILIHAN FILE & VALIDASI FORMAT HARDWARE
# =========================================================
root = Tk()
root.withdraw()
file_path = filedialog.askopenfilename(
    title="Pilih File Audio WAV (Standard: 48kHz, 16-bit, Mono)", 
    filetypes=[("WAV files", "*.wav")]
)

if not file_path:
    print("❌ Tidak ada file yang dipilih. Program berhenti.")
    exit()

info = sf.info(file_path)
data, fs = sf.read(file_path)

# Validasi kompatibilitas format terhadap spesifikasi desain hardware
errors = []
if fs != 48000:
    errors.append(f"Sample Rate: {fs} Hz (Wajib 48000 Hz)")
if info.channels != 1:
    errors.append(f"Channels: {info.channels} (Wajib Mono)")
if info.subtype != 'PCM_16':
    errors.append(f"Bit Depth: {info.subtype} (Wajib PCM_16)")

if errors:
    print("\n" + "!"*50)
    print("❌ FORMAT FILE TIDAK SESUAI SPESIFIKASI HARDWARE!")
    print("!"*50)
    for err in errors:
        print(f"   >> {err}")
    print("\n💡 Gunakan FFmpeg untuk konversi ke format standar:")
    print(f"   ffmpeg -i {os.path.basename(file_path)} -ac 1 -ar 48000 -acodec pcm_s16le output_ready.wav")
    print("!"*50 + "\n")
    exit()

# Konfigurasi path penyimpanan hasil output
script_dir = os.path.dirname(os.path.abspath(__file__))
file_name_no_ext = os.path.splitext(os.path.basename(file_path))[0]
suffix = "_output_golden_model"

out_wav_path = os.path.join(script_dir, f"{file_name_no_ext}{suffix}.wav")
csv_path     = os.path.join(script_dir, f"{file_name_no_ext}{suffix}.csv")
png_path     = os.path.join(script_dir, f"{file_name_no_ext}{suffix}.png")

def get_input(prompt, default):
    formatted = f"{prompt}".ljust(35)
    user = input(f"{formatted} (Default {default}): ").strip()
    return float(user) if user != "" else default

print("\n" + "="*70)
print("PENGUJIAN GOLDEN MODEL: STANDAR AUDIO RIIL")
print("="*70)

# Input Parameter Dynamic Range Compression
threshold = get_input("Threshold (dB)", -20.0)
ratio     = get_input("Ratio", 5.0)
makeup    = get_input("Makeup Gain (dB)", 0.0)
at_env    = get_input("Attack Env (ms)", 10.0)
rt_env    = get_input("Release Env (ms)", 100.0)
at_gs     = get_input("Attack Smooth (ms)", 10.0)
rt_gs     = get_input("Release Smooth (ms)", 100.0)

params = {
    "threshold": threshold, "ratio": ratio, "makeup": makeup,
    "alphaA_env": alpha_time(at_env, fs), "alphaR_env": alpha_time(rt_env, fs),
    "alphaA_gs": alpha_time(at_gs, fs),   "alphaR_gs": alpha_time(rt_gs, fs)
}

# =========================================================
# 3. PROSES SIMULASI & ANALISIS METRIK OBJEKTIF
# =========================================================
print(f"\n[Process] Memproses '{os.path.basename(file_path)}'...")
output_audio, gr_history, sw_time = process_drc_audio_linear(data, fs, params)

# Mengabaikan data awal (0.2 detik) untuk stabilisasi metrik
skip_samples = int(0.2 * fs)
data_stable = data[skip_samples:] if len(data) > skip_samples else data
output_stable = output_audio[skip_samples:] if len(output_audio) > skip_samples else output_audio

# Pengukuran Loudness berdasarkan standar EBU R128
meter = pyln.Meter(fs)
lufs_in = meter.integrated_loudness(data_stable)
lufs_out = meter.integrated_loudness(output_stable)

# Perhitungan Karakteristik Dinamika
def calculate_advanced_metrics(x, fs):
    sample_peak = np.max(np.abs(x))
    # Rekonstruksi sinyal untuk mendeteksi True Peak (4x Oversampling)
    x_oversampled = np.interp(np.linspace(0, len(x), len(x)*4), np.arange(len(x)), x)
    true_peak = np.max(np.abs(x_oversampled))
    # Perhitungan nilai RMS
    rms = np.sqrt(np.mean(x**2))
    rms_db = 20 * np.log10(rms + EPS)
    cf_db = 20 * np.log10((sample_peak + EPS) / (rms + EPS))
    return sample_peak, true_peak, rms_db, cf_db

p_in, tp_in, r_db_in, cf_in = calculate_advanced_metrics(data_stable, fs)
p_out, tp_out, r_db_out, cf_out = calculate_advanced_metrics(output_stable, fs)

tp_in_db = 20*np.log10(tp_in+EPS)
tp_out_db = 20*np.log10(tp_out+EPS)

# =========================================================
# 4. EVALUASI STATUS VALIDASI
# =========================================================

# Evaluasi Loudness: Gain Reduction
l_success = lufs_out < (lufs_in + makeup + 0.1)
l_text = "Effective Compression (Gain Reduction Applied)" if l_success else "No Reduction Detected"
l_status_console = f"{'✅' if l_success else '❌'} {l_text}"
l_status_csv = f"{'V' if l_success else 'X'} {l_text}"

# Evaluasi Crest Factor: Rentang Dinamika
cf_success = cf_out < cf_in
cf_text = "Dynamics Compressed" if cf_success else "Dynamics Expanded (Digital Ceiling Effect)"
cf_status_console = f"{'✅' if cf_success else '❌'} {cf_text}"
cf_status_csv = f"{'V' if cf_success else 'X'} {cf_text}"

# Evaluasi True Peak: Digital Clipping
tp_success = tp_out_db < 0.01
tp_text = "Safe (No Clipping)" if tp_success else "Saturated (Digital Clipping)"
tp_status_console = f"{'✅' if tp_success else '❌'} {tp_text}"
tp_status_csv = f"{'V' if tp_success else 'X'} {tp_text}"

# Evaluasi RMS: Atenuasi Sinyal
rms_success = r_db_out < (r_db_in + makeup + 0.1)
rms_text = "Signal Attenuated Correctly" if rms_success else "Gain Increase Dominates"
rms_status_console = f"{'✅' if rms_success else '❌'} {rms_text}"
rms_status_csv = f"{'V' if rms_success else 'X'} {rms_text}"

# =========================================================
# 5. EKSPOR DATA HASIL PENGUJIAN (CSV & WAV)
# =========================================================
# Fungsi internal untuk mengubah format titik ke koma agar sesuai regional Indonesia di CSV
def f_id(val):
    if isinstance(val, str): return val
    return f"{val:.5f}".replace('.', ',')

with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
    f.write("sep=;\n")
    writer = csv.writer(f, delimiter=';')
    writer.writerow(["CATEGORY", "METRIC", "INPUT", "OUTPUT", "DELTA", "UNIT", "STATUS"])
    writer.writerow(["LOUDNESS", "Integrated Loudness", f_id(lufs_in), f_id(lufs_out), f_id(lufs_out-lufs_in), "LUFS", l_status_csv])
    writer.writerow(["DYNAMICS", "Crest Factor", f_id(cf_in), f_id(cf_out), f_id(cf_out-cf_in), "dB", cf_status_csv])
    writer.writerow(["DYNAMICS", "True Peak", f_id(tp_in_db), f_id(tp_out_db), f_id(tp_out_db-tp_in_db), "dBTP", tp_status_csv])
    writer.writerow(["DYNAMICS", "RMS Level", f_id(r_db_in), f_id(r_db_out), f_id(r_db_out-r_db_in), "dBFS", rms_status_csv])
    writer.writerow(["SYSTEM", "SW Execution Time", "-", f_id(sw_time), "-", "ms", "-"])

sf.write(out_wav_path, output_audio, fs)

# =========================================================
# 6. VISUALISASI WAVEFORM & ANALISIS DOMAIN LEVEL
# =========================================================
t_axis = np.linspace(0, len(data)/fs, len(data))
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 14), sharex=True)

# Annotasi Parameter DRC pada Grafik
info_text = (f"DRC Parameters:\n"
             f"Threshold: {threshold} dB\n"
             f"Ratio: {ratio}:1\n"
             f"Makeup: {makeup} dB\n"
             f"Env A/R: {at_env}/{rt_env} ms\n"
             f"Smooth a/r: {at_gs}/{rt_gs} ms")

props = dict(boxstyle='round', facecolor='white', alpha=0.8)
ax1.text(0.02, 0.05, info_text, transform=ax1.transAxes, fontsize=10,
        verticalalignment='bottom', bbox=props, family='monospace')

# Plot Waveform Amplitudo
ax1.plot(t_axis, data, color='gray', alpha=0.8, label="Input (Original)")
ax1.plot(t_axis, output_audio, color='blue', alpha=0.8, label="Output (DRC)")
ax1.set_title(f"Waveform Analysis: {file_name_no_ext}", fontweight='bold')
ax1.set_ylabel("Amplitude")
ax1.legend(loc='upper right')

# Plot Level dBFS dan Threshold
ax2.plot(t_axis, 20*np.log10(np.abs(data)+EPS), color='gray', alpha=0.8, label="Input dB")
ax2.plot(t_axis, 20*np.log10(np.abs(output_audio)+EPS), color='red', alpha=0.8, label="Output dB")
ax2.axhline(threshold, color='black', linestyle='--', label='Threshold')
ax2.set_ylabel("Level (dBFS)")
ax2.set_ylim([-60, 5])
ax2.legend(loc='upper right')

# Plot Riwayat Gain Reduction
gr_db = 20 * np.log10(gr_history + EPS)
ax3.fill_between(t_axis, gr_db, 0, color='green', alpha=0.8, label="Gain Reduction (dB)")
ax3.set_ylabel("Reduction (dB)")
ax3.set_xlabel("Time (seconds)")
ax3.set_ylim([min(gr_db)-5, 5])
ax3.grid(True, alpha=0.2)
ax3.legend(loc='upper right')

plt.tight_layout()
plt.savefig(png_path, dpi=300)
plt.close(fig)

# Tampilan Ringkasan Laporan Akhir pada Konsol (Lebar disesuaikan untuk 5 angka di belakang koma)
line_width = 125
print("\n" + "="*line_width)
print("📊 LAPORAN VALIDASI GOLDEN MODEL (SOFTWARE)")
print("="*line_width)
print(f"{'Parameter':<25} | {'Input':<15} | {'Output':<15} | {'Delta':<12} | {'Status'}")
print("-" * line_width)
print(f"{'Integrated Loudness':<25} | {lufs_in:<15.5f} | {lufs_out:<15.5f} | {lufs_out-lufs_in:<+12.5f} | {l_status_console}")
print(f"{'Crest Factor (CF)':<25} | {cf_in:<15.5f} | {cf_out:<15.5f} | {cf_out-cf_in:<+12.5f} | {cf_status_console}")
print(f"{'True Peak (dBTP)':<25} | {tp_in_db:<15.5f} | {tp_out_db:<15.5f} | {tp_out_db-tp_in_db:<+12.5f} | {tp_status_console}")
print(f"{'RMS Level (dBFS)':<25} | {r_db_in:<15.5f} | {r_db_out:<15.5f} | {r_db_out-r_db_in:<+12.5f} | {rms_status_console}")
print("-" * line_width)
print(f"⏱️  Software Execution Time : {sw_time:.5f} ms")
print(f"🎵 WAV Output             : {os.path.basename(out_wav_path)}")
print(f"📊 Report CSV             : {os.path.basename(csv_path)}")
print(f"🖼️  Grafik PNG             : {os.path.basename(png_path)}")
print("="*line_width)

print(f"\n✅ Pengujian Selesai\n")