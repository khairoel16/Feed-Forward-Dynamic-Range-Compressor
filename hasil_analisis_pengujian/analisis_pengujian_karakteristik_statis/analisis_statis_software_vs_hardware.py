# analisis_statis_software_vs_hardware.py
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, r2_score
import tkinter as tk
from tkinter import filedialog
import os
import csv

def pilih_file(judul):
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(title=judul, filetypes=[("CSV files", "*.csv")])
    root.destroy()
    return file_path

def analisis_drc():
    print("\n" + "="*60)
    print("   PROGRAM ANALISIS KOMPARASI DRC: SOFTWARE VS HARDWARE")
    print("="*60)
    
    # --- LANGKAH 1: SOFTWARE FILE ---
    print("\n[LANGKAH 1]: Pilih file CSV hasil pengujian STATIS SOFTWARE (Golden Model)")
    print(">> Menunggu pemilihan file...")
    file_sw = pilih_file("PILIH FILE HASIL SOFTWARE (GOLDEN)")
    
    if not file_sw: 
        print("!! Pemilihan file software dibatalkan. Program berhenti."); return
    print(f"✅ File SOFTWARE diterima: {os.path.abspath(file_sw)}")

    # --- LANGKAH 2: HARDWARE FILE ---
    print("\n[LANGKAH 2]: Pilih file CSV hasil pengujian STATIS HARDWARE (Kria/FPGA)")
    print(">> Menunggu pemilihan file...")
    file_hw = pilih_file("PILIH FILE HASIL HARDWARE (KRIA)")
    
    if not file_hw: 
        print("!! Pemilihan file hardware dibatalkan. Program berhenti."); return
    print(f"✅ File HARDWARE diterima: {os.path.abspath(file_hw)}")

    # --- LOAD & VALIDASI DATA ---
    print("\n[PROSES]: Membaca dan memvalidasi struktur data...")
    
    try:
        # Load data (Software & Hardware)
        sw = pd.read_csv(file_sw, sep=None, decimal=',', engine='python')
        hw = pd.read_csv(file_hw, sep=None, decimal=',', engine='python')

        # Proteksi Kolom
        required_columns = ['Input_dB', 'Output_dB', 'Gain_Reduction_dB']
        for col in required_columns:
            if col not in sw.columns or col not in hw.columns:
                print(f"\n❌ ERROR: Kolom '{col}' tidak ditemukan!")
                return

        # Proteksi Jumlah Baris
        if len(sw) != len(hw):
            print(f"\n⚠️ PERINGATAN: Jumlah baris data tidak sama! (SW: {len(sw)}, HW: {len(hw)})")
            return

        # --- KALKULASI METRIK ---
        err_out = np.abs(sw['Output_dB'] - hw['Output_dB'])
        
        metrics = {
            "Avg Error Output (dB)": np.mean(err_out),
            "Max Error Output (dB)": np.max(err_out),
            "MAE Output (dB)": np.mean(err_out),
            "RMSE Output (dB)": np.sqrt(mean_squared_error(sw['Output_dB'], hw['Output_dB'])),
            "R2 Score Output": r2_score(sw['Output_dB'], hw['Output_dB']),
            "Avg Error GR (dB)": np.mean(np.abs(sw['Gain_Reduction_dB'] - hw['Gain_Reduction_dB'])),
            "Max Error GR (dB)": np.max(np.abs(sw['Gain_Reduction_dB'] - hw['Gain_Reduction_dB']))
        }

        # --- OUTPUT TABEL KONSOL ---
        name_sw = os.path.basename(file_sw)
        name_hw = os.path.basename(file_hw)
        
        print("\n" + "╔" + "═"*58 + "╗")
        print("║" + "           HASIL ANALISIS VALIDASI STATIS DRC             " + "║")
        print("╠" + "═"*58 + "╣")
        print(f"║ SW File: {name_sw[:47].ljust(47)} ║")
        print(f"║ HW File: {name_hw[:47].ljust(47)} ║")
        print("╟" + "─"*35 + "┬" + "─"*22 + "╢")
        print(f"║ {'METRIK ANALISIS'.ljust(33)} ║ {'NILAI'.center(20)} ║")
        print("╟" + "─"*35 + "┼" + "─"*22 + "╢")
        for key, value in metrics.items():
            fmt = f"{value:.8f}" if "R2" in key else f"{value:.6f} dB"
            print(f"║ {key.ljust(33)} ║ {fmt.rjust(20)} ║")
        print("╚" + "═"*35 + "╧" + "═"*22 + "╝")

        # --- GENERASI FILE CSV ANALISIS (GABUNGAN) ---
        # 1. Tentukan Nama File (suffix dari file Hardware)
        suffix = name_hw.split('_')[-1].replace('.csv', '')
        output_name = f"hasil_analisis_statis_{suffix}.csv"
        
        # 2. PERBAIKAN: Gunakan path folder tempat script Python ini berada
        folder_script = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(folder_script, output_name)

        # Siapkan data metrik untuk ditulis ke kolom F dan G
        metrik_keys = list(metrics.keys())
        metrik_vals = [str(round(v, 8)).replace('.',',') if "R2" in k else str(round(v, 6)).replace('.',',') for k, v in metrics.items()]

        with open(output_path, mode='w', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            
            # Header Baris 1
            writer.writerow([
                "Input_dB", 
                "Output_dB_SW", 
                "Gain_Reduction_dB_SW", 
                "Output_dB_HW", 
                "Gain_Reduction_dB_HW", 
                "Metrik Analisis", 
                "Nilai"
            ])

            # Iterasi untuk menulis baris data
            for i in range(len(sw)):
                # Ambil data mentah (Kolom A-E)
                row = [
                    str(sw['Input_dB'].iloc[i]).replace('.',','),
                    str(sw['Output_dB'].iloc[i]).replace('.',','),
                    str(sw['Gain_Reduction_dB'].iloc[i]).replace('.',','),
                    str(hw['Output_dB'].iloc[i]).replace('.',','),
                    str(hw['Gain_Reduction_dB'].iloc[i]).replace('.',',')
                ]
                
                # Tambahkan data metrik jika masih tersedia (Kolom F-G)
                if i < len(metrik_keys):
                    row.append(metrik_keys[i])
                    row.append(metrik_vals[i])
                else:
                    row.append("")
                    row.append("")
                
                writer.writerow(row)

        print(f"\n✅ Analisis selesai!")
        print(f"📁 File hasil analisis disimpan di: {output_path}")

    except Exception as e:
        print(f"\n❌ TERJADI KESALAHAN: {e}")

if __name__ == "__main__":
    analisis_drc()