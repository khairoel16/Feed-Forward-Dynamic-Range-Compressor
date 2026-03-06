# kria_pengujian_wav_drc.py
import numpy as np
import soundfile as sf
import pyloudnorm as pyln
import math
import csv
import os
import time
from pynq import Overlay, allocate

# =========================================================
# 1. KONFIGURASI AKSES HARDWARE KRIA KV260
# =========================================================
BITSTREAM_PATH = "/home/ubuntu/DRC/design_project_drc_1.bit"
DMA_NAME       = "axi_dma_0"

# Nama IP Core sesuai dengan Address Editor di Vivado
IP_ENV         = "drc_envelope_follower_0"
IP_COMP        = "drc_gain_computer_0"
IP_SMOOTH      = "drc_gain_smoothing_0"
IP_APPLY       = "drc_makeup_apply_0"

ONE_Q30 = 1 << 30  # Faktor konversi ke Fixed-Point Q1.30
FS      = 48000    # Sample rate standar operasional hardware
EPS     = 1e-12

def to_q30(x):
    """Konversi nilai float ke format Fixed-Point 32-bit (Q1.30)"""
    val = int(x * ONE_Q30)
    return int(np.clip(val, -2147483648, 2147483647))

def alpha_time(time_ms, fs):
    """Menghitung koefisien filter (Exponential Decay)"""
    if time_ms <= 0: return 0.0
    return math.exp(-math.log(9.0) / (fs * (time_ms / 1000.0)))

# =========================================================
# 2. INISIALISASI OVERLAY & LOAD AUDIO
# =========================================================
print("\n" + "="*85)
print("📊 PENGUJIAN HARDWARE ACCELERATION: KRIA KV260 BITSTREAM")
print("="*85)

try:
    overlay = Overlay(BITSTREAM_PATH)
    dma = getattr(overlay, DMA_NAME)
    # Inisialisasi handle akses register untuk setiap blok IP Core
    ips = {
        'env': getattr(overlay, IP_ENV),
        'comp': getattr(overlay, IP_COMP),
        'smooth': getattr(overlay, IP_SMOOTH),
        'apply': getattr(overlay, IP_APPLY)
    }
    print("[System] Bitstream Overlay & IP Handles: OK\n")
except Exception as e:
    print(f"[System] Gagal Memuat Bitstream: {e}")
    exit()

# Pemilihan File via Terminal SSH
default_path = "/home/ubuntu/DRC/file_wav/alarm_16.wav"
file_path = input(f"{'Pilih File Audio WAV':<35} (Default {os.path.basename(default_path)}): ").strip()
if not file_path: file_path = default_path

if not os.path.exists(file_path):
    print(f"❌ File tidak ditemukan: {file_path}")
    exit()

# Load Audio (Standard: 48kHz, 16-bit, Mono)
data, fs = sf.read(file_path)
if fs != 48000:
    print("❌ Error: Sample rate input harus 48000 Hz")
    exit()

# =========================================================
# 3. KONFIGURASI PARAMETER & UPDATE REGISTER HARDWARE
# =========================================================
def get_input(prompt, default):
    formatted = f"{prompt}".ljust(35)
    user = input(f"{formatted} (Default {default}): ").strip()
    return float(user) if user != "" else default

threshold = get_input("\nThreshold (dB)", -20.0)
ratio     = get_input("Ratio", 5.0)
makeup    = get_input("Makeup Gain (dB)", 0.0)
at_env    = get_input("Attack Env (ms)", 10.0)
rt_env    = get_input("Release Env (ms)", 100.0)
at_gs     = get_input("Attack Smooth (ms)", 10.0)
rt_gs     = get_input("Release Smooth (ms)", 100.0)

# Penulisan parameter ke Register AXI-Lite
ips['env'].write(0x00, to_q30(alpha_time(at_env, fs)))
ips['env'].write(0x04, to_q30(alpha_time(rt_env, fs)))
ips['comp'].write(0x00, to_q30(10.0 ** (threshold / 20.0))) # T_lin
ips['comp'].write(0x04, to_q30(1.0 / ratio))                # 1/R
ips['smooth'].write(0x00, to_q30(alpha_time(at_gs, fs)))
ips['smooth'].write(0x04, to_q30(alpha_time(rt_gs, fs)))
ips['apply'].write(0x00, to_q30(10.0 ** (makeup / 20.0)))   # M_lin

# =========================================================
# 4. EKSEKUSI DATA TRANSFER (AXI DMA)
# =========================================================
num_samples = len(data)
# Alokasi buffer hardware (int16)
in_buffer = allocate(shape=(num_samples,), dtype=np.int16)
out_buffer = allocate(shape=(num_samples,), dtype=np.int16)

# Normalisasi float ke signed 16-bit integer
in_buffer[:] = (data * 32767).astype(np.int16)

print(f"\n[Process] Mengirim {num_samples} sampel ke FPGA via DMA...")
start_time = time.perf_counter()

# Transaksi data Full-Duplex
dma.recvchannel.transfer(out_buffer)
dma.sendchannel.transfer(in_buffer)
dma.sendchannel.wait()
dma.recvchannel.wait()

end_time = time.perf_counter()
hardware_exec_ms = (end_time - start_time) * 1000

# Konversi kembali hasil hardware ke float32
output_audio = np.array(out_buffer, dtype=np.float32) / 32767.0

# =========================================================
# 5. KALKULASI METRIK OBJEKTIF
# =========================================================
skip_samples = int(0.2 * fs)
data_stable = data[skip_samples:] if len(data) > skip_samples else data
output_stable = output_audio[skip_samples:] if len(output_audio) > skip_samples else output_audio

# Pengukuran Integrated Loudness (EBU R128)
meter = pyln.Meter(fs)
lufs_in = meter.integrated_loudness(data_stable)
lufs_out = meter.integrated_loudness(output_stable)

# Pengukuran Karakteristik Dinamika
def calculate_advanced_metrics(x):
    sample_peak = np.max(np.abs(x))
    rms = np.sqrt(np.mean(x**2))
    rms_db = 20 * np.log10(rms + EPS)
    cf_db = 20 * np.log10((sample_peak + EPS) / (rms + EPS))
    return sample_peak, rms_db, cf_db

p_in_val, r_db_in, cf_in = calculate_advanced_metrics(data_stable)
p_out_val, r_db_out, cf_out = calculate_advanced_metrics(output_stable)

tp_in_db = 20 * np.log10(p_in_val + EPS)
tp_out_db = 20 * np.log10(p_out_val + EPS)

# =========================================================
# 6. PENENTUAN STATUS VALIDASI
# =========================================================
l_success = lufs_out < (lufs_in + makeup + 0.1)
l_text = "Effective Compression (Gain Reduction Applied)" if l_success else "No Reduction Detected"
l_status_console = f"{'✅' if l_success else '❌'} {l_text}"
l_status_csv = f"{'V' if l_success else 'X'} {l_text}"

cf_success = cf_out < cf_in
cf_text = "Dynamics Compressed" if cf_success else "Dynamics Expanded (Digital Ceiling Effect)"
cf_status_console = f"{'✅' if cf_success else '❌'} {cf_text}"
cf_status_csv = f"{'V' if cf_success else 'X'} {cf_text}"

tp_success = tp_out_db < 0.01
tp_text = "Safe (No Clipping)" if tp_success else "Saturated (Digital Clipping)"
tp_status_console = f"{'✅' if tp_success else '❌'} {tp_text}"
tp_status_csv = f"{'V' if tp_success else 'X'} {tp_text}"

rms_success = r_db_out < (r_db_in + makeup + 0.1)
rms_text = "Signal Attenuated Correctly" if rms_success else "Gain Increase Dominates"
rms_status_console = f"{'✅' if rms_success else '❌'} {rms_text}"
rms_status_csv = f"{'V' if rms_success else 'X'} {rms_text}"

# =========================================================
# 7. EKSPOR DATA HASIL PENGUJIAN (CSV & WAV)
# =========================================================
script_dir = os.path.dirname(os.path.abspath(__file__))
base_name = os.path.splitext(os.path.basename(file_path))[0]
out_wav_path = os.path.join(script_dir, f"{base_name}_hw_out.wav")
csv_path     = os.path.join(script_dir, f"{base_name}_hw_report.csv")

# Fungsi internal untuk konversi titik ke koma (Regional Indo)
def f_id(val):
    if isinstance(val, str): return val
    return f"{val:.5f}".replace('.', ',')

# Penyimpanan audio hasil hardware
sf.write(out_wav_path, output_audio, fs)

# Penulisan laporan CSV
with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
    f.write("sep=;\n")
    writer = csv.writer(f, delimiter=';')
    writer.writerow(["CATEGORY", "METRIC", "INPUT", "OUTPUT", "DELTA", "UNIT", "STATUS"])
    writer.writerow(["LOUDNESS", "Integrated Loudness", f_id(lufs_in), f_id(lufs_out), f_id(lufs_out-lufs_in), "LUFS", l_status_csv])
    writer.writerow(["DYNAMICS", "Crest Factor", f_id(cf_in), f_id(cf_out), f_id(cf_out-cf_in), "dB", cf_status_csv])
    writer.writerow(["DYNAMICS", "True Peak", f_id(tp_in_db), f_id(tp_out_db), f_id(tp_out_db - tp_in_db), "dBTP", tp_status_csv])
    writer.writerow(["DYNAMICS", "RMS Level", f_id(r_db_in), f_id(r_db_out), f_id(r_db_out-r_db_in), "dBFS", rms_status_csv])
    writer.writerow(["SYSTEM", "HW Execution Time", "-", f_id(hardware_exec_ms), "-", "ms", "Accelerated"])

# Ringkasan Laporan Akhir pada Konsol
line_width = 125
print("\n" + "="*line_width)
print("📊 LAPORAN VALIDASI HARDWARE ACCELERATION (KRIA KV260)")
print("="*line_width)
print(f"{'Parameter':<25} | {'Input':<15} | {'Output':<15} | {'Delta':<12} | {'Status'}")
print("-" * line_width)
print(f"{'Integrated Loudness':<25} | {lufs_in:<15.5f} | {lufs_out:<15.5f} | {lufs_out-lufs_in:<+12.5f} | {l_status_console}")
print(f"{'Crest Factor (CF)':<25} | {cf_in:<15.5f} | {cf_out:<15.5f} | {cf_out-cf_in:<+12.5f} | {cf_status_console}")
print(f"{'True Peak (dBTP)':<25} | {tp_in_db:<15.5f} | {tp_out_db:<15.5f} | {tp_out_db-tp_in_db:<+12.5f} | {tp_status_console}")
print(f"{'RMS Level (dBFS)':<25} | {r_db_in:<15.5f} | {r_db_out:<15.5f} | {r_db_out-r_db_in:<+12.5f} | {rms_status_console}")
print("-" * line_width)
print(f"⏱️  Hardware Execution Time (PL) : {hardware_exec_ms:.5f} ms")
print(f"🎵 WAV Output Hardware          : {os.path.basename(out_wav_path)}")
print(f"📊 Report CSV Hardware          : {os.path.basename(csv_path)}")
print("="*line_width)

print(f"✅ Pengujian Selesai\n")

# Pembebasan buffer memori
in_buffer.freebuffer()
out_buffer.freebuffer()