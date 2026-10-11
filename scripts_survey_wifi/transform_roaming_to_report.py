import pandas as pd

# Variabel Global Path
INPUT_PATH_1 = 'raw/roaming_L3_Dinda.csv'
OUTPUT_PATH_1 = 'archive/attachment_roaming_L3_A.csv'

INPUT_PATH_2 = 'raw/roaming_L3_Deva.csv'
OUTPUT_PATH_2 = 'archive/attachment_roaming_L3_B.csv'


def proses_data_perpindahan(input_path, output_path):
    df = pd.read_csv(input_path)

    # Ambil nilai BSSID dan sinyal dari baris sebelumnya
    df['bssid_lama'] = df['bssid'].shift(1)
    df['sinyal_sebelum'] = df['rssi_dbm'].shift(1)

    # Filter baris perpindahan
    hasil = df[df['pindah'].astype(str).str.strip().str.upper() == 'YA'].copy()

    # Pemetaan kolom target
    hasil['Perpindahan ke-'] = range(1, len(hasil) + 1)
    hasil['BSSID lama'] = hasil['bssid_lama']
    hasil['BSSID baru'] = hasil['bssid']
    hasil['Sinyal sebelum pindah'] = hasil['sinyal_sebelum']
    hasil['Ping hilang'] = (
        hasil['ping_hilang'] if 'ping_hilang' in df.columns else 0
    )

    kolom_target = [
        'Perpindahan ke-',
        'BSSID lama',
        'BSSID baru',
        'Sinyal sebelum pindah',
        'Ping hilang',
    ]

    hasil_final = hasil[kolom_target]
    hasil_final.to_csv(output_path, index=False)


def main():
    proses_data_perpindahan(INPUT_PATH_1, OUTPUT_PATH_1)
    proses_data_perpindahan(INPUT_PATH_2, OUTPUT_PATH_2)


if __name__ == '__main__':
    main()