import pandas as pd

INPUT_PATH = "data/active_L3.csv"
OUTPUT_PATH = "data/attachment_active_survei.csv"

def muat_data(filepath: str) -> pd.DataFrame:
    """Tahap 1: Membaca dataset CSV awal"""
    return pd.read_csv(filepath)


def olah_struktur(df: pd.DataFrame) -> pd.DataFrame:
    """Tahap 2: Grouping berdasarkan titik_id & BSSID, agregasi rata-rata, dan pengurutan"""
    # 1. Groupby titik_id & bssid_assoc, lalu hitung rata-rata parameter teknis
    df_grouped = (
        df.groupby(["titik_id", "bssid_assoc"], as_index=False)
        .agg(
            {
                "rssi_dbm": "mean",
                "rtt_avg_ms": "mean",
                "loss_pct": "mean",
                "down_mbps": "mean",
                "up_mbps": "mean",
            }
        )
        .sort_values(by="titik_id", ascending=True)
    )

    # 2. Pembulatan desimal agar rapi
    df_grouped["rssi_dbm"] = df_grouped["rssi_dbm"].round(2)
    df_grouped["rtt_avg_ms"] = df_grouped["rtt_avg_ms"].round(2)
    df_grouped["loss_pct"] = df_grouped["loss_pct"].round(2)

    # 3. Format kolom gabungan Down/Up (Mbps) dari nilai rata-rata
    df_grouped["Down/Up (Mbps)"] = (
        df_grouped["down_mbps"].round(2).astype(str)
        + " / "
        + df_grouped["up_mbps"].round(2).astype(str)
    )

    # 4. Inisialisasi kolom kosong untuk pengisian manual
    df_grouped["Alasan dipilih"] = ""

    # 5. Pemetaan nama kolom sesuai tabel target
    pemetaan_kolom = {
        "titik_id": "Titik",
        "Alasan dipilih": "Alasan dipilih",
        "bssid_assoc": "BSSID",
        "rssi_dbm": "RSSI",
        "rtt_avg_ms": "RTT avg",
        "loss_pct": "Loss",
        "Down/Up (Mbps)": "Down/Up (Mbps)",
    }

    return df_grouped[list(pemetaan_kolom.keys())].rename(
        columns=pemetaan_kolom
    )


def ekspor_hasil(df: pd.DataFrame, output_path: str = None) -> None:
    """Tahap 3: Menampilkan data ke konsol dan menyimpan file (opsional)"""
    print(df.to_string(index=False))

    if output_path:
        df.to_csv(output_path, index=False)
        print(f"\nTabel teragregasi berhasil disimpan ke: {output_path}")


def main() -> pd.DataFrame:
    """Fungsi utama (orchestrator) yang mengeksekusi seluruh tahap"""
    data_mentah = muat_data(INPUT_PATH)
    data_terolah = olah_struktur(data_mentah)
    ekspor_hasil(data_terolah, OUTPUT_PATH)
    return data_terolah


if __name__ == "__main__":
    main()
