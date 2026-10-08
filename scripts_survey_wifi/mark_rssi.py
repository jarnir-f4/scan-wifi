#!/usr/bin/env python3
"""
mark_rssi.py - (untuk asisten) menandai data RSSI hasil scan ke denah.

windows:
  python3 mark_rssi.py --denah data\\titik_L3.png --data-titik data\\titik_L3.csv --lantai 3  --hasil-pasif-a data\\passive_L3_Taqiya.csv --hasil-pasif-b data\\passive_L3_Maulana.csv --ssid "WiFi-UB.x" --out data\\rssi_L3.png
  
linux:
  python3 mark_rssi.py --denah data/titik_L3.png --data-titik data/titik_L3.csv --lantai 3  --hasil-pasif-a data/passive_L3_Taqiya.csv --hasil-pasif-b data/passive_L3_Maulana.csv --ssid "WiFi-UB.x" --out data/rssi_L3.png

"""
import argparse
import csv
import math
import os

import matplotlib.pyplot as plt

def process_passive_data(csv_path, target_ssid):
    if not csv_path or not os.path.exists(csv_path):
        return {}

    bssid_rssi_map = {}

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ssid = row.get("ssid", "").strip()
            if ssid != target_ssid:
                continue

            titik_id = row.get("titik_id", "").strip()
            bssid = row.get("bssid", "").strip()
            try:
                rssi = float(row.get("rssi_dbm"))
            except (ValueError, TypeError):
                continue

            key = (titik_id, bssid)
            if key not in bssid_rssi_map:
                bssid_rssi_map[key] = []
            bssid_rssi_map[key].append(rssi)

    titik_max_per_bssid = {}
    for (titik_id, bssid), rssi_list in bssid_rssi_map.items():
        max_rssi_bssid = max(rssi_list)
        if titik_id not in titik_max_per_bssid:
            titik_max_per_bssid[titik_id] = []
        titik_max_per_bssid[titik_id].append(max_rssi_bssid)

    result_rssi = {}
    for titik_id, max_list in titik_max_per_bssid.items():
        result_rssi[titik_id] = max(max_list)

    return result_rssi


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--denah", required=True)
    p.add_argument("--lantai", required=True)
    p.add_argument("--hasil-pasif-a", required=False, default=None)
    p.add_argument("--hasil-pasif-b", required=False, default=None)
    p.add_argument("--data-titik", required=True)
    p.add_argument("--ssid", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    pts = []
    with open(a.data_titik, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = row["titik_id"]
            x = float(row["x_px"])
            y = float(row["y_px"])
            pts.append((tid, x, y))

    rssi_a = process_passive_data(a.hasil_pasif_a, a.ssid)
    rssi_b = process_passive_data(a.hasil_pasif_b, a.ssid)

    img = plt.imread(a.denah)
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.imshow(img)

    for tid, x, y in pts:
        # Hanya kumpulkan teks RSSI saja
        labels = []
        if tid in rssi_a:
            labels.append("%.0f dBm" % rssi_a[tid])
        if tid in rssi_b:
            labels.append("%.0f dBm" % rssi_b[tid])

        # Plot teks RSSI di posisi y + 50 px
        if labels:
            text_str = "\n".join(labels)
            ax.text(x, y + 50, text_str, fontsize=7, color="blue", ha="center", va="top")

    ax.axis("off")
    fig.savefig(os.path.splitext(a.out)[0] + ".png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("Hasil plotting tersimpan -> %s" % (os.path.splitext(a.out)[0] + ".png"))


if __name__ == "__main__":
    main()
