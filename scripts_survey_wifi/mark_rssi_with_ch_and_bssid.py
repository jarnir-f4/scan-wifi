#!/usr/bin/env python3
"""
mark_rssi_with_ch_and_bssid.py - (untuk asisten) menandai data RSSI hasil scan ke denah.

windows:
  python3 mark_rssi_with_ch_and_bssid.py --denah data\\titik_L3.png --data-titik data\\titik_L3.csv --lantai 3  --hasil-pasif-a data\\passive_L3_Taqiya.csv --hasil-pasif-b data\\passive_L3_Maulana.csv --ssid "WiFi-UB.x" --out data\\archive\\img\\rssi_with_bssid_ch_L3.png
  
linux:
  python3 mark_rssi_with_ch_and_bssid.py --denah data/titik_L3.png --data-titik data/titik_L3.csv --lantai 3  --hasil-pasif-a data/passive_L3_Taqiya.csv --hasil-pasif-b data/passive_L3_Maulana.csv --ssid "WiFi-UB.x" --out data/archive/img/rssi_with_bssid_ch_L3.png

"""

import argparse
import csv
import math
import os

import matplotlib.pyplot as plt

x_offset = 50
y_offset = 50
x_scale = 1.3
y_scale = 1.3

def process_passive_data(csv_path, target_ssid):
    if not csv_path or not os.path.exists(csv_path):
        return {}

    bssid_rssi_map = {}

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            band = row.get("band", "").strip()
            try:
                if float(band) != 5.0:
                    continue
            except (ValueError, TypeError):
                continue

            ssid = row.get("ssid", "").strip()
            if ssid != target_ssid:
                continue

            channel = row.get("channel", "").strip()
            titik_id = row.get("titik_id", "").strip()
            bssid = row.get("bssid", "").strip()
            try:
                rssi = float(row.get("rssi_dbm"))
            except (ValueError, TypeError):
                continue

            key = (titik_id, bssid)
            if key not in bssid_rssi_map:
                bssid_rssi_map[key] = []
            # Simpan tuple (rssi, channel)
            bssid_rssi_map[key].append((rssi, channel))

    # Ambil data dengan RSSI terkuat (max) untuk tiap pasangan (titik_id, bssid)
    titik_bssid_max = {}
    for (titik_id, bssid), entries in bssid_rssi_map.items():
        # Cari entry dengan RSSI tertinggi
        max_entry = max(entries, key=lambda item: item[0])
        if titik_id not in titik_bssid_max:
            titik_bssid_max[titik_id] = {}
        titik_bssid_max[titik_id][bssid] = {
            "rssi": max_entry[0],
            "channel": max_entry[1]
        }

    return titik_bssid_max


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
        # Gabungkan data BSSID dari pasif-a dan pasif-b (ambil RSSI tertinggi jika BSSID sama)
        merged_bssid_data = {}

        bssid_dict_a = rssi_a.get(tid, {})
        for bssid, data in bssid_dict_a.items():
            merged_bssid_data[bssid] = data

        bssid_dict_b = rssi_b.get(tid, {})
        for bssid, data in bssid_dict_b.items():
            if bssid in merged_bssid_data:
                if data["rssi"] > merged_bssid_data[bssid]["rssi"]:
                    merged_bssid_data[bssid] = data
            else:
                merged_bssid_data[bssid] = data

        if merged_bssid_data:
            # Urutkan BSSID secara leksikografik (A-Z)
            # sorted_bssids = sorted(merged_bssid_data.keys())

            sorted_bssids = sorted(
                merged_bssid_data.keys(),
                key=lambda bssid: merged_bssid_data[bssid]["rssi"],
                reverse=True
            )

            for idx, bssid in enumerate(sorted_bssids):
                rssi_val = merged_bssid_data[bssid]["rssi"]
                channel_val = merged_bssid_data[bssid]["channel"]

                # Ambil 2 segmen terakhir BSSID
                bssid_parts = bssid.split(":")
                short_bssid = ":".join(bssid_parts[-2:]) if len(bssid_parts) >= 2 else bssid

                # Format teks: "RSSI (channel) (xx:xx)"
                # text_str = f"{rssi_val:.0f} dBm ({channel_val}) ({short_bssid})"
                text_str = f"{rssi_val:.0f} dBm ({channel_val})"

                # Offset pertama +50,offset BSSID berikutnya cukup +10
                current_y_offset = 50 + (idx * 20)

                ax.text(
                    x * x_scale + x_offset,
                    y * y_scale + current_y_offset,
                    text_str,
                    fontsize=7,
                    color="blue",
                    ha="center",
                    va="top"
                )

    ax.axis("off")
    fig.savefig(os.path.splitext(a.out)[0] + ".png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("Hasil plotting tersimpan -> %s" % (os.path.splitext(a.out)[0] + ".png"))


if __name__ == "__main__":
    main()