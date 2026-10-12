import pandas as pd

FILE_INPUT_1 = 'raw/roaming_L3_Dinda.csv'
FILE_OUTPUT_1 = 'archive/compressed_roaming_L3_Dinda.csv'

FILE_INPUT_2 = 'raw/roaming_L3_Deva.csv'
FILE_OUTPUT_2 = 'archive/compressed_roaming_L3_Deva.csv'

def baca_data(nama_file):
    return pd.read_csv(nama_file)

def filter_log_perpindahan(df):
    selected_indices = set()
    total_baris = len(df)
    
    # Cari indeks baris dengan nilai 'YA' (mengabaikan spasi dan huruf besar/kecil)
    indeks_ya = df[df['pindah'].fillna('').astype(str).str.strip().str.upper() == 'YA'].index
    
    for idx in indeks_ya:
        # 1 log sebelum
        if idx - 1 >= 0:
            selected_indices.add(idx - 1)
        # Log saat pindah
        selected_indices.add(idx)
        # 1 log setelah
        if idx + 1 < total_baris:
            selected_indices.add(idx + 1)
            
    # Urutkan indeks yang unik agar urutan log asli tetap terjaga
    indeks_terurut = sorted(selected_indices)
    return df.iloc[indeks_terurut]

def simpan_data(df_filtered, nama_file_output):
    df_filtered.to_csv(nama_file_output, index=False)

def proses(input_file, output_file):
    # Tahap 1: Baca data CSV
    df = baca_data(input_file)
    
    # Tahap 2: Ambil log sebelum, saat, dan sesudah perpindahan
    df_hasil = filter_log_perpindahan(df)
    
    # Tahap 3: Simpan data hasil filter
    simpan_data(df_hasil, output_file)
    print(f"Berhasil memfilter {len(df_hasil)} baris log tanpa duplikat ke '{output_file}'.")

def main():    
    proses(FILE_INPUT_1, FILE_OUTPUT_1)
    proses(FILE_INPUT_2, FILE_OUTPUT_2)

if __name__ == '__main__':
    main()