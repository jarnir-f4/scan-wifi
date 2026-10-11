#!/usr/bin/env python3
"""
analyze.py - analisis kualitas sinyal Wi-Fi 5 GHz satu lantai dalam satu perintah.

Contoh:
  python3 analyze.py --passive data/passive_L3.csv --ssid "NAMA_SSID" \
      --denah denah/L3.png --scale 20 --out output/L3 --titik data/titik_L3.csv \
      [--active data/active_L3.csv] [--ap-fisik data/ap_fisik_L3.csv]

Keluaran (prefix --out):
  _titik.csv       metrik + status + penyebab per titik ukur
  _ap.csv          estimasi posisi AP (radio) dari data RSSI; kompatibel dengan gabung_lantai.py
  _area_lemah.csv  kelompok titik lemah yang berdekatan (weak-spot area)
  _heatmap.png     heatmap RSSI AP terkuat + kontur -67/-75 dBm
  _status.png      peta status titik, area lemah, dan posisi AP
  _kanal.png       distribusi kanal 5 GHz
  _ringkasan.txt   ringkasan angka untuk laporan (format ringkas, sama dengan stdout)
  _analisis.json   analisis lengkap per langkah interpretasi (1-6), kualitas data, jejak input

Skema opsional:
  passive: timestamp (untuk peringatan rentang waktu per titik), width_mhz, noise_dbm,
           ch_util_pct, sta_count, band, x_px, y_px
  active : timestamp / scan_ke (urutan; wajib relevan untuk hitung roaming), bssid_assoc,
           metode_rtt, device, rtt_avg_ms, rtt_max_ms, jitter_ms, loss_pct,
           down_mbps, up_mbps
  titik  : kolom opsional `ruang` (label ruangan) agar blank spot dipetakan ke ruangan
  ap_fisik: x_px, y_px, ap_id (opsional) untuk perbandingan AP estimasi vs AP fisik
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sys
from datetime import datetime
from functools import cache
from typing import Any, NoReturn

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.patches import Circle
from numpy.typing import NDArray
from scipy.interpolate import griddata
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import KDTree

# Backend non-interaktif. Aman dipanggil setelah import pyplot selama belum ada figure,
# dan menghindari impor yang terpecah oleh pernyataan (E402/I001).
matplotlib.use("Agg")

FloatArr = NDArray[np.float64]

# ---------------- Ambang kriteria (lihat Bagian 4 modul) ----------------
RSSI_BAIK = -67  # >= : baik untuk semua aplikasi
RSSI_LEMAH = -70  # <  : lemah
RSSI_KRITIS = -80  # <  : blank spot
RSSI_SEKUNDER = -75  # AP kedua minimal (roaming/redundansi)
CCI_RSSI = -85  # radio lain di kanal overlap yang dihitung sebagai CCI
CCI_MAX = 2  # > : co-channel interference tinggi
SNR_BAIK, SNR_BURUK = 25, 15
UTIL_MAX = 50  # % channel utilization (BSS Load)
DOWN_MIN = 10  # Mbps
LOSS_MAX = 2  # % (loss ICMP rata-rata per titik)
RTT_MAX = 50  # ms (median per titik)
RTT_SPIKE = 300  # ms (RTT maks di satu titik; lonjakan)
PROBE_GAGAL_MAX = 20  # % scan active tanpa RTT / loss 100%
RSSI_STD_MAX = 6.0  # dB, simpangan baku RSSI antar-sampel di satu titik
MAKS_SPAN_MENIT = 60  # rentang waktu sampel passive per titik sebelum diberi peringatan
AP_JARAK_M = 15.0  # titik ukur dipakai untuk estimasi AP hanya bila <= jarak ini dari titik terkuat
AP_COCOK_M = 10.0  # AP fisik (□) dan estimasi (▲/△) dianggap sama bila berjarak <= ini
AP_TETANGGA_M = (
    20.0  # dua AP dianggap bertetangga (cek kanal sama) bila berjarak <= ini
)
JARAK_AP_JAUH_M = (
    20.0  # titik lemah lebih jauh dari ini dari AP terdekat: "jauh dari AP"
)
JARAK_AP_DEKAT_M = 10.0  # titik lemah sedekat ini dari AP: dugaan penghalang
DFS_MIN, DFS_MAX = 52, 144  # kanal 5 GHz yang tunduk pada DFS (UNII-2A dan UNII-2C)

AP_TINGGI, AP_SEDANG = (
    -55,
    -65,
)  # RSSI maks radio: di lantai ini / mungkin tembus dari lantai lain

LEVEL: dict[str, int] = {"BAIK": 0, "PERHATIAN": 1, "BURUK": 2, "KRITIS": 3}
WARNA: dict[str, str] = {
    "BAIK": "#1a9850",
    "PERHATIAN": "#fee08b",
    "BURUK": "#f46d43",
    "KRITIS": "#a50026",
}

# aturan -> (kolom di _titik.csv, nama aturan) untuk laporan cakupan data
KOLOM_ATURAN: dict[str, str] = {
    "rssi1": "RSSI SSID target",
    "rssi2": "AP cadangan",
    "snr": "SNR",
    "util1": "util kanal",
    "down_mbps": "throughput",
    "loss_pct": "packet loss",
    "rtt_ms": "latensi",
    "probe_gagal_pct": "probe gagal",
}

KOLOM_AREA = [
    "area",
    "jumlah_titik",
    "titik",
    "x_px",
    "y_px",
    "rssi_rata",
    "status_terburuk",
    "penyebab_dominan",
]
KOLOM_AP = [
    "radio",
    "channel",
    "width",
    "rssi_maks",
    "titik_terkuat",
    "n_titik_dipakai",
    "x_est",
    "y_est",
    "keyakinan",
]

# Kontrak kolom yang dikonsumsi gabung_lantai.py. Kolom detail lain tetap disimpan
# supaya keluaran _titik.csv / _ap.csv tetap berguna untuk analisis per lantai.
KOLOM_GABUNG_AP = ("radio", "channel", "rssi_maks")
KOLOM_GABUNG_TITIK = ("titik_id", "rssi1", "radio1")

BLOK_40 = [
    (36, 40),
    (44, 48),
    (52, 56),
    (60, 64),
    (100, 104),
    (108, 112),
    (116, 120),
    (124, 128),
    (132, 136),
    (140, 144),
    (149, 153),
    (157, 161),
]
BLOK_80 = [(36, 48), (52, 64), (100, 112), (116, 128), (132, 144), (149, 161)]
BLOK_160 = [(36, 64), (100, 128)]


# ---------------------------------------------------------------- utilitas
@cache
def _kanal_terpakai(ch: int, width: int) -> frozenset[int]:
    if ch <= 14:  # 2,4 GHz: 22 MHz, overlap +-4 kanal
        return frozenset(range(ch - 4, ch + 5))
    blok = {40: BLOK_40, 80: BLOK_80, 160: BLOK_160}.get(width)
    if blok:
        for lo, hi in blok:
            if lo <= ch <= hi:
                return frozenset(range(lo, hi + 1, 4))
    return frozenset({ch})


def kanal_terpakai(ch: float, width: float) -> frozenset[int]:
    """Himpunan kanal 20 MHz yang diduduki (untuk menghitung overlap/CCI)."""
    return _kanal_terpakai(int(ch), int(width) if pd.notna(width) else 20)


def dbm_ke_mw(dbm: pd.Series) -> pd.Series:
    """dBm -> mW (domain linear), indeks Series dipertahankan."""
    return pd.Series(np.power(10.0, dbm.to_numpy(float) / 10.0), index=dbm.index)


def mw_ke_dbm(mw: pd.Series) -> pd.Series:
    """mW -> dBm, indeks Series dipertahankan."""
    return pd.Series(10.0 * np.log10(mw.to_numpy(float)), index=mw.index)


LOG: list[dict[str, str]] = []  # info/peringatan selama eksekusi; ikut ditulis ke JSON


def catat_info(pesan: str) -> None:
    """Diagnostik ke stderr agar stdout hanya berisi ringkasan."""
    LOG.append({"tingkat": "info", "pesan": pesan})
    print("Info: " + pesan, file=sys.stderr)


def catat_peringatan(pesan: str) -> None:
    LOG.append({"tingkat": "peringatan", "pesan": pesan})
    print("PERINGATAN: " + pesan, file=sys.stderr)


def keluar(pesan: str) -> NoReturn:
    print("ERROR: " + pesan, file=sys.stderr)
    sys.exit(1)


def jejak_input(**paths: str | None) -> dict[str, dict[str, str]]:
    """Path dan hash (sha256, 12 hex awal) tiap file input, agar hasil bisa dilacak ke datanya."""
    out: dict[str, dict[str, str]] = {}
    for nama, p in paths.items():
        if p and os.path.exists(p):
            with open(p, "rb") as f:
                out[nama] = {
                    "path": p,
                    "sha256": hashlib.sha256(f.read()).hexdigest()[:12],
                }
    return out


def judul(teks: str) -> str:
    """Buang karakter di luar BMP (emoji) yang tidak ada di font matplotlib."""
    return "".join(ch for ch in teks if ord(ch) < 0x10000)


# ---------------------------------------------------------------- pemuatan data
def muat_passive(
    path: str, band: str, titik: str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Kembalikan (baris passive pada band terpilih, daftar semua titik ber-koordinat).

    Daftar titik dibentuk SEBELUM baris NaN dan filter band dibuang, sehingga titik yang
    tidak menghasilkan bacaan valid tetap dianalisis (sebagai blank spot), bukan lenyap.
    """
    df = pd.read_csv(
        path, dtype={"band": str, "bssid": str, "ssid": str, "titik_id": str}
    )
    for c in ("titik_id", "ssid", "bssid", "channel", "rssi_dbm"):
        if c not in df:
            keluar(f"kolom '{c}' tidak ada di {path}")
    df["titik_id"] = df["titik_id"].str.strip()
    if (
        titik
    ):  # koordinat dari titik_L{n}.csv (hasil mark_points.py) menggantikan isi passive
        t = pd.read_csv(titik, dtype={"titik_id": str, "ruang": str})
        for c in ("titik_id", "x_px", "y_px"):
            if c not in t:
                keluar(f"kolom '{c}' tidak ada di {titik}")
        t = t[[c for c in ("titik_id", "x_px", "y_px", "ruang") if c in t]].copy()
        t["titik_id"] = t["titik_id"].str.strip()
        dup = t.titik_id[t.titik_id.duplicated()].unique()
        if len(dup):
            catat_peringatan(
                f"titik_id ganda di {titik}, dipakai yang pertama: {', '.join(dup)}"
            )
            t = t.drop_duplicates("titik_id")
        tanpa_passive = sorted(set(t.titik_id) - set(df.titik_id))
        if tanpa_passive:
            catat_peringatan(
                "titik ada di file titik tetapi tanpa baris passive "
                f"(tidak dianalisis; belum diukur?): {', '.join(tanpa_passive)}"
            )
        buang = [c for c in ("x_px", "y_px", "ruang") if c in df and c in t]
        df = df.drop(columns=buang).merge(t, on="titik_id", how="left")
    elif "x_px" not in df or "y_px" not in df:
        keluar("kolom x_px/y_px tidak ada. Sertakan --titik data/titik_L{n}.csv")
    df["x_px"] = pd.to_numeric(df["x_px"], errors="coerce")
    df["y_px"] = pd.to_numeric(df["y_px"], errors="coerce")
    hilang = sorted(df.loc[df.x_px.isna() | df.y_px.isna(), "titik_id"].unique())
    if hilang and len(hilang) == df.titik_id.nunique():
        keluar(
            "semua titik tidak punya koordinat. Sertakan --titik data/titik_L{n}.csv "
            "(hasil mark_points.py) atau isi kolom x_px/y_px"
        )
    if hilang:
        catat_peringatan(f"titik tanpa koordinat (diabaikan): {', '.join(hilang)}")
        df = df.dropna(subset=["x_px", "y_px"])

    kolom_semua = [c for c in ("titik_id", "x_px", "y_px", "ruang") if c in df]
    semua = df[kolom_semua].drop_duplicates("titik_id").reset_index(drop=True)
    if "ruang" in semua:
        semua["ruang"] = semua["ruang"].fillna("").astype(str).str.strip()

    df["rssi_dbm"] = pd.to_numeric(df["rssi_dbm"], errors="coerce")
    df["channel"] = pd.to_numeric(df["channel"], errors="coerce")
    nan_baris = df["rssi_dbm"].isna() | df["channel"].isna()
    if nan_baris.any():
        catat_peringatan(
            f"{int(nan_baris.sum())} baris passive tanpa rssi/channel dibuang"
        )
        df = df[~nan_baris].copy()
    df["ssid"] = df["ssid"].fillna("")
    df["bssid"] = df["bssid"].fillna("").str.lower().str.strip()
    kosong = df["bssid"] == ""
    if kosong.any():
        catat_peringatan(
            f"{int(kosong.sum())} baris tanpa BSSID diabaikan (BSSID wajib dicatat)"
        )
        df = df[~kosong].copy()

    dari_kanal = pd.Series(np.where(df["channel"] >= 32, "5", "2.4"), index=df.index)
    if "band" not in df:
        df["band"] = dari_kanal
    df["band"] = df["band"].str.strip().str.replace(r"\.0$", "", regex=True)
    df["band"] = df["band"].where(df["band"].notna() & (df["band"] != ""), dari_kanal)
    if "width_mhz" not in df:
        df["width_mhz"] = 20
    df["width_mhz"] = pd.to_numeric(df["width_mhz"], errors="coerce").fillna(20)
    for c in ("noise_dbm", "ch_util_pct", "sta_count"):
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan

    hasil = df[df["band"] == band].copy()
    if hasil.empty:
        keluar(
            f"tidak ada data band {band} GHz. Band yang ada di data: "
            f"{', '.join(sorted(df['band'].dropna().unique())) or '-'}"
        )

    # ---- pemeriksaan konsistensi sesi (tidak mengubah data, hanya memperingatkan)
    ganti = hasil.groupby("bssid")["channel"].nunique()
    ganti = ganti[ganti > 1]
    if len(ganti):
        catat_peringatan(
            f"{len(ganti)} BSSID berpindah kanal di antara sampel "
            "(AP reboot/auto-channel?). Kanal yang dilaporkan = yang tersering."
        )
    if "timestamp" in hasil:
        ts = pd.to_datetime(hasil["timestamp"], errors="coerce")
        span = (
            ts.groupby(hasil["titik_id"]).agg(
                lambda s: (s.max() - s.min()).total_seconds()
            )
            / 60.0
        )
        panjang = span[span > MAKS_SPAN_MENIT]
        if len(panjang):
            catat_peringatan(
                f"{len(panjang)} titik punya sampel passive membentang > "
                f"{MAKS_SPAN_MENIT} menit (sesi ganda?): {', '.join(panjang.index[:10])}"
            )
    return hasil, semua


def muat_aktif(
    path: str, radio_map: dict[str, str], titik_pasif: set[str]
) -> pd.DataFrame:
    """Agregasi uji aktif per titik, tahan terhadap probe gagal, campuran metode, dan roaming."""
    act = pd.read_csv(
        path,
        dtype={"titik_id": str, "bssid_assoc": str, "metode_rtt": str, "device": str},
    )
    if "titik_id" not in act:
        keluar(f"kolom 'titik_id' tidak ada di {path}")
    act["titik_id"] = act["titik_id"].str.strip()
    angka = [
        "down_mbps",
        "up_mbps",
        "rtt_avg_ms",
        "rtt_max_ms",
        "jitter_ms",
        "loss_pct",
    ]
    for c in angka:
        if c in act:
            act[c] = pd.to_numeric(act[c], errors="coerce")
        else:
            act[c] = np.nan

    # urutan hanya relevan untuk hitung perpindahan AP; urutkan eksplisit, jangan percaya file
    kunci_urut = ["titik_id"]
    if "timestamp" in act:
        act["timestamp"] = pd.to_datetime(act["timestamp"], errors="coerce")
        kunci_urut.append("timestamp")
    elif "scan_ke" in act:
        kunci_urut.append("scan_ke")
    act = act.sort_values(kunci_urut, kind="stable").reset_index(drop=True)

    tanpa = sorted(set(act.titik_id) - titik_pasif)
    if tanpa:
        catat_peringatan(
            f"titik uji aktif tanpa data pasif (diabaikan): {', '.join(tanpa)}"
        )
        act = act[act.titik_id.isin(titik_pasif)]

    metode = (
        act["metode_rtt"].fillna("").str.lower().str.strip()
        if "metode_rtt" in act
        else pd.Series("icmp", index=act.index)
    )
    ic = metode.isin(["icmp", ""])  # metode kosong dianggap icmp
    if (~ic).any():
        catat_info(
            f"{int((~ic).sum())} baris active memakai metode non-ICMP "
            "(dikeluarkan dari RTT/jitter/loss, dihitung sebagai probe gagal bila RTT kosong)"
        )
    gagal = act["rtt_avg_ms"].isna() | (act["loss_pct"] >= 100)
    act["_gagal"] = gagal.astype(float) * 100.0
    for sumber, tujuan in (
        ("rtt_avg_ms", "_rtt"),
        ("rtt_max_ms", "_rttmax"),
        ("jitter_ms", "_jit"),
        ("loss_pct", "_loss"),
    ):
        act[tujuan] = act[sumber].where(ic)

    if "device" in act and act["device"].nunique() > 1:
        catat_peringatan(
            "uji aktif memakai >1 perangkat "
            f"({', '.join(act['device'].dropna().unique())}); RTT/tx-rate tidak sebanding antar titik"
        )

    if "bssid_assoc" in act:
        assoc = act["bssid_assoc"].str.lower().str.strip()
        act["_assoc"] = assoc.map(radio_map).fillna(assoc)
    else:
        act["_assoc"] = pd.Series(np.nan, index=act.index, dtype=object)
    # baris tempat asosiasi berganti dibanding scan (ber-asosiasi) sebelumnya di titik yang sama
    sebelum = act.groupby("titik_id")["_assoc"].transform(lambda s: s.ffill().shift())
    pindah = act["_assoc"].notna() & sebelum.notna() & (act["_assoc"] != sebelum)
    act["_loss_pindah"] = act["_loss"].where(pindah)
    act["_gagal_pindah"] = act["_gagal"].where(pindah)

    def n_pindah(s: pd.Series) -> int:
        s = s.dropna()
        return int((s != s.shift()).iloc[1:].sum())

    def modus(s: pd.Series) -> str:
        m = s.dropna().mode()
        return str(m.iloc[0]) if len(m) else ""

    def riwayat(s: pd.Series) -> str:
        s = s.dropna()
        return " > ".join(str(v) for v in s[s != s.shift()])

    g = act.groupby("titik_id")
    agg = pd.DataFrame(
        {
            "n_scan_active": g.size(),
            "rtt_ms": g["_rtt"].median(),
            "rtt_maks_ms": g["_rttmax"].max(),
            "jitter_ms": g["_jit"].median(),
            "loss_pct": g["_loss"].mean(),
            "probe_gagal_pct": g["_gagal"].mean(),
            "down_mbps": g["down_mbps"].median(),
            "up_mbps": g["up_mbps"].median(),
            "radio_assoc": g["_assoc"].agg(modus),
            "n_pindah_ap": g["_assoc"].agg(n_pindah),
            "riwayat_assoc": g["_assoc"].agg(riwayat),
            "loss_saat_pindah_pct": g["_loss_pindah"].max(),
            "probe_gagal_saat_pindah_pct": g["_gagal_pindah"].max(),
        }
    )
    if "device" in act:
        agg["device_aktif"] = g["device"].agg(modus)
    return agg.reset_index()


# ---------------------------------------------------------------- inti analisis
def kelompok_radio(
    df: pd.DataFrame, target: str | None = None, maks_selisih: float = 4.0
) -> pd.Series:
    """Kelompokkan BSSID menjadi radio fisik. Satu radio AP bisa memancarkan beberapa SSID
    (di FILKOM: WiFi-UB.x, eduroam, FILKOM EVENT) dengan BSSID yang mirip. Dua BSSID dianggap
    satu radio bila: kanal sama, SSID berbeda, MAC hanya beda 1 oktet, dan median selisih
    RSSI di titik yang sama <= maks_selisih dB. BSSID ber-SSID sama TIDAK pernah digabung.
    Nama radio = BSSID milik SSID target (konsisten antar-lantai), selain itu BSSID terkecil."""
    info = df.groupby("bssid").agg(
        ssid=("ssid", "first"), channel=("channel", lambda c: c.mode().iloc[0])
    )
    rssi = df.groupby(["bssid", "titik_id"])["rssi_dbm"].mean().unstack()
    induk: dict[str, str] = {b: b for b in info.index}

    def akar(b: str) -> str:
        while induk[b] != b:
            induk[b] = induk[induk[b]]
            b = induk[b]
        return b

    for _, grup in info.groupby("channel"):
        anggota = list(grup.index)
        for i, b1 in enumerate(anggota):
            o1 = b1.split(":")
            for b2 in anggota[i + 1 :]:
                o2 = b2.split(":")
                if (
                    info.at[b1, "ssid"] == info.at[b2, "ssid"]
                    or len(o1) != 6
                    or len(o2) != 6
                ):
                    continue
                if sum(x != y for x, y in zip(o1, o2, strict=True)) > 1:
                    continue
                beda = (rssi.loc[b1] - rssi.loc[b2]).abs().dropna()
                if len(beda) and beda.median() <= maks_selisih:
                    induk[akar(b1)] = akar(b2)
    kelompok: dict[str, list[str]] = {}
    for b in info.index:
        kelompok.setdefault(akar(b), []).append(b)
    nama: dict[str, str] = {}
    for anggota in kelompok.values():
        tg = [b for b in anggota if info.at[b, "ssid"] == target]
        wakil = max(tg, key=lambda b: rssi.loc[b].mean()) if tg else min(anggota)
        for b in anggota:
            nama[b] = wakil
    multi = [g for g in kelompok.values() if len(g) > 1]
    if multi:
        catat_info(f"{len(multi)} radio memancarkan >1 SSID (BSSID digabung per radio)")
    return df["bssid"].map(nama)


def metrik_titik(
    df: pd.DataFrame, ssid: str, semua: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Metrik per titik untuk SSID target. Setiap titik di `semua` muncul tepat sekali;
    titik tanpa bacaan SSID target diberi rssi1 = NaN (dinilai sebagai blank spot)."""
    df = df.assign(_mw=dbm_ke_mw(df["rssi_dbm"]))
    per_bssid = (
        df.groupby(["titik_id", "x_px", "y_px", "ssid", "bssid", "radio"], sort=False)
        .agg(
            mw=("_mw", "mean"),
            rssi_std=("rssi_dbm", "std"),
            channel=("channel", "first"),
            width=("width_mhz", "max"),
            noise=("noise_dbm", "mean"),
            util=("ch_util_pct", "mean"),
            sta=("sta_count", "mean"),
        )
        .reset_index()
    )
    per_bssid["rssi"] = mw_ke_dbm(per_bssid["mw"])
    per_bssid = per_bssid.drop(columns="mw")

    # satu BARIS UTUH per radio fisik (drop_duplicates, bukan groupby.first() yang
    # mengambil nilai non-null pertama per kolom dan bisa mencampur dua BSSID)
    urut = per_bssid.sort_values("rssi", ascending=False)
    per_radio = urut.drop_duplicates(["titik_id", "radio"])
    target = urut[urut.ssid == ssid].drop_duplicates(["titik_id", "radio"])
    radio_per_titik = dict(tuple(per_radio.groupby("titik_id")))
    target_per_titik = dict(tuple(target.groupby("titik_id")))

    kosong: dict[str, object] = {
        "rssi1": np.nan,
        "rssi2": np.nan,
        "rssi1_std": np.nan,
        "bssid1": "",
        "radio1": "",
        "channel1": np.nan,
        "width1": np.nan,
        "cci": np.nan,
        "snr": np.nan,
        "util1": np.nan,
        "sta1": np.nan,
    }
    rows: list[dict[str, object]] = []
    for rec in semua.to_dict("records"):
        tid = rec["titik_id"]
        g = radio_per_titik.get(tid)
        tg = target_per_titik.get(tid)
        r: dict[str, object] = {
            "titik_id": tid,
            "x_px": rec["x_px"],
            "y_px": rec["y_px"],
        }
        if "ruang" in rec:
            r["ruang"] = rec["ruang"]
        r["n_radio_terlihat"] = 0 if g is None else len(g)
        if g is None or tg is None:
            r.update(kosong)
            rows.append(r)
            continue
        p = tg.iloc[0]
        occ = kanal_terpakai(p.channel, p.width)
        lain = g[(g.radio != p.radio) & (g.rssi >= CCI_RSSI)]
        cci = sum(
            1
            for ch, w in zip(lain.channel, lain.width, strict=True)
            if occ & kanal_terpakai(ch, w)
        )
        r.update(
            rssi1=round(p.rssi, 1),
            rssi2=round(tg.iloc[1].rssi, 1) if len(tg) > 1 else np.nan,
            rssi1_std=round(p.rssi_std, 1) if pd.notna(p.rssi_std) else np.nan,
            bssid1=p.bssid,
            radio1=p.radio,
            channel1=int(p.channel),
            width1=p.width,
            cci=cci,
            snr=round(p.rssi - p.noise, 1) if pd.notna(p.noise) else np.nan,
            util1=p.util,
            sta1=p.sta,
        )
        rows.append(r)
    return pd.DataFrame(rows), per_bssid


def nilai_status(r: pd.Series) -> pd.Series:
    lv, utama = "BAIK", ""
    sebab: list[str] = []

    def naik(level: str, alasan: str) -> None:
        nonlocal lv, utama
        sebab.append(alasan)
        if LEVEL[level] > LEVEL[lv]:
            lv, utama = level, alasan

    def ada(k: str) -> bool:
        return pd.notna(r.get(k))

    if pd.isna(r.rssi1):
        naik("KRITIS", "blank spot (SSID tidak terdeteksi)")
    elif r.rssi1 < RSSI_KRITIS:
        naik("KRITIS", f"blank spot (RSSI<{RSSI_KRITIS})")
    elif r.rssi1 < RSSI_LEMAH:
        naik("BURUK", f"cakupan lemah (RSSI<{RSSI_LEMAH})")
    elif r.rssi1 < RSSI_BAIK:
        naik("PERHATIAN", "RSSI marginal")
    if ada("rssi1") and (pd.isna(r.rssi2) or r.rssi2 < RSSI_SEKUNDER):
        naik("PERHATIAN", "tanpa AP cadangan (roaming)")
    if ada("rssi1_std") and r.rssi1_std > RSSI_STD_MAX:
        naik("PERHATIAN", f"RSSI fluktuatif (std {r.rssi1_std:.1f} dB)")
    if ada("cci") and r.cci > CCI_MAX:
        naik("PERHATIAN", f"co-channel interference ({int(r.cci)} radio)")
    if ada("snr"):
        if r.snr < SNR_BURUK:
            naik("BURUK", "SNR rendah")
        elif r.snr < SNR_BAIK:
            naik("PERHATIAN", "SNR marginal")
    if ada("util1") and r.util1 > UTIL_MAX:
        naik("PERHATIAN", f"kanal padat (util {r.util1:.0f}%)")
    if ada("down_mbps") and r.down_mbps < DOWN_MIN:
        naik("BURUK", "throughput rendah")
    if ada("loss_pct") and r.loss_pct > LOSS_MAX:
        naik("BURUK", "packet loss")
    if ada("probe_gagal_pct") and r.probe_gagal_pct >= PROBE_GAGAL_MAX:
        naik("BURUK", f"probe gagal ({r.probe_gagal_pct:.0f}% scan)")
    if ada("rtt_ms") and r.rtt_ms > RTT_MAX:
        naik("PERHATIAN", "latensi tinggi")
    if ada("rtt_maks_ms") and r.rtt_maks_ms > RTT_SPIKE:
        naik("PERHATIAN", "lonjakan latensi")
    if ada("n_pindah_ap") and r.n_pindah_ap > 0:
        naik("PERHATIAN", "perpindahan AP saat uji statis")
    return pd.Series(
        {"status": lv, "penyebab_utama": utama, "penyebab": "; ".join(sebab)}
    )


def kelompok_lemah(t: pd.DataFrame, scale: float, radius_m: float) -> pd.DataFrame:
    lemah = t[t.status.isin(["BURUK", "KRITIS"])].reset_index(drop=True)
    if lemah.empty:
        return pd.DataFrame(columns=KOLOM_AREA)
    n = len(lemah)
    xy = lemah[["x_px", "y_px"]].to_numpy(float) / scale
    pasang = KDTree(xy).query_pairs(radius_m, output_type="ndarray")
    if len(pasang):
        m = coo_matrix(
            (np.ones(len(pasang)), (pasang[:, 0], pasang[:, 1])), shape=(n, n)
        )
    else:
        m = coo_matrix((n, n))
    _, label = connected_components(m, directed=False)
    lemah["area"] = label
    out: list[dict[str, object]] = []
    for k, (_, g) in enumerate(lemah.groupby("area"), 1):
        sebab = g.penyebab_utama.str.replace(r" \(.*\)", "", regex=True).value_counts()
        out.append(
            {
                "area": f"A{k}",
                "jumlah_titik": len(g),
                "titik": ", ".join(g.titik_id),
                "x_px": g.x_px.mean(),
                "y_px": g.y_px.mean(),
                "rssi_rata": round(g.rssi1.mean(), 1)
                if g.rssi1.notna().any()
                else np.nan,
                "status_terburuk": max(g.status, key=lambda s: LEVEL[s]),
                "penyebab_dominan": sebab.index[0],
            }
        )
    return pd.DataFrame(out, columns=KOLOM_AREA)


def estimasi_ap(
    per_bssid: pd.DataFrame, ssid: str, scale: float, top: int = 3
) -> pd.DataFrame:
    """Weighted centroid dari `top` titik terkuat per radio, dibatasi AP_JARAK_M dari
    titik terkuat agar titik yang berjauhan tidak menghasilkan centroid di tengah-tengah."""
    t = per_bssid[per_bssid.ssid == ssid]
    rows: list[dict[str, object]] = []
    for radio, g in t.groupby("radio"):
        g = g.sort_values("rssi", ascending=False).drop_duplicates("titik_id").head(top)
        j = np.hypot(g.x_px - g.x_px.iloc[0], g.y_px - g.y_px.iloc[0]) / scale
        g = g[j <= AP_JARAK_M]
        w = np.power(10, g.rssi / 10)
        rows.append(
            {
                "radio": radio,
                "channel": int(g.channel.iloc[0]),
                "width": g.width.iloc[0],
                "rssi_maks": round(g.rssi.iloc[0], 1),
                "titik_terkuat": g.titik_id.iloc[0],
                "n_titik_dipakai": len(g),
                "x_est": np.average(g.x_px, weights=w),
                "y_est": np.average(g.y_px, weights=w),
                "keyakinan": "tinggi"
                if g.rssi.iloc[0] >= AP_TINGGI
                else (
                    "sedang (mungkin lantai lain)"
                    if g.rssi.iloc[0] >= AP_SEDANG
                    else "rendah (lantai/area lain)"
                ),
            }
        )
    return pd.DataFrame(rows, columns=KOLOM_AP)


def interpolasi(
    xy: FloatArr,
    z: FloatArr,
    gx: NDArray[np.int_],
    gy: NDArray[np.int_],
    scale: float,
    radius_m: float = 5.0,
    maks_linear_m: float = 6.0,
) -> tuple[FloatArr, str]:
    """Linear (Delaunay) bila titik tersebar 2D; bila gagal (mis. titik segaris di koridor)
    pakai IDW (8 titik terdekat dalam radius_m). Sel yang jauh dari titik ukur dikosongkan."""
    pts = np.column_stack([gx.ravel(), gy.ravel()]).astype(float)
    tree = KDTree(xy)
    if len(xy) >= 3:
        try:
            gz = griddata(xy, z, (gx, gy), method="linear")
            jarak, _ = tree.query(pts)
            gz[(jarak > maks_linear_m * scale).reshape(gz.shape)] = np.nan
            if np.isfinite(gz).any():
                return gz, f"linear (maks {maks_linear_m:.0f} m dari titik)"
        except (RuntimeError, ValueError) as e:
            # scipy.spatial.QhullError adalah subclass RuntimeError (titik segaris/terlalu
            # sedikit). Menangkap induknya menghindari impor QhullError yang berbeda antar versi.
            catat_peringatan(
                f"interpolasi linear gagal ({type(e).__name__}); pakai IDW"
            )

    k = min(len(xy), 8)
    d, idx = tree.query(pts, k=k, distance_upper_bound=radius_m * scale)
    d = d.reshape(len(pts), -1)
    idx = np.minimum(
        idx.reshape(len(pts), -1), len(z) - 1
    )  # idx == n untuk tetangga kosong
    ok = np.isfinite(d)
    w = np.where(ok, 1.0 / np.maximum(np.where(ok, d, 1.0), 1.0) ** 2, 0.0)
    den = w.sum(axis=1)
    val = np.where(
        den > 0, (w * z[idx]).sum(axis=1) / np.where(den > 0, den, 1.0), np.nan
    )
    return val.reshape(gx.shape), f"IDW (radius {radius_m:.0f} m)"


# ---------------------------------------------------------------- gambar
def latar(ax: Axes, denah: str | None, t: pd.DataFrame) -> tuple[int, int]:
    if denah and os.path.exists(denah):
        img = plt.imread(denah)
        ax.imshow(img)
        return int(img.shape[1]), int(img.shape[0])
    w, h = int(t.x_px.max() * 1.1 + 1), int(t.y_px.max() * 1.1 + 1)
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.set_aspect("equal")
    return w, h


def gambar_heatmap(
    t: pd.DataFrame, out: str, denah: str | None, ssid: str, band: str, scale: float
) -> None:
    v = t.dropna(subset=["rssi1"])
    fig, ax = plt.subplots(figsize=(14, 7))
    w, h = latar(ax, denah, t)
    gx, gy = np.mgrid[0:w:3, 0:h:3]
    metode = "-"
    if len(v):
        gz, metode = interpolasi(
            v[["x_px", "y_px"]].to_numpy(float), v.rssi1.to_numpy(float), gx, gy, scale
        )
    else:
        gz = np.full(gx.shape, np.nan)
    hm = ax.pcolormesh(
        gx,
        gy,
        np.ma.masked_invalid(gz),
        cmap="RdYlGn",
        vmin=-90,
        vmax=-40,
        alpha=0.6,
        shading="auto",
    )
    fin = gz[np.isfinite(gz)]
    levels = [
        lv
        for lv in (RSSI_SEKUNDER, RSSI_BAIK)
        if fin.size and fin.min() < lv < fin.max()
    ]
    if levels:
        cs = ax.contour(
            gx,
            gy,
            gz,
            levels=levels,
            linewidths=1.5,
            linestyles="--",
            colors=["#d73027" if lv == RSSI_SEKUNDER else "#1a9850" for lv in levels],
        )
        ax.clabel(cs, fmt="%d dBm", fontsize=8)
    ax.scatter(t.x_px, t.y_px, c="k", s=10)
    for r in t.to_dict("records"):
        nilai = "-" if pd.isna(r["rssi1"]) else f"{r['rssi1']:.0f}"
        ax.annotate(
            f"{r['titik_id']}\n{nilai}",
            (r["x_px"], r["y_px"]),
            fontsize=6,
            xytext=(3, 3),
            textcoords="offset points",
        )
    fig.colorbar(hm, ax=ax, label="RSSI AP terkuat (dBm)", shrink=0.7)
    ax.set_title(
        judul(f"Heatmap RSSI {band} GHz - SSID {ssid} (interpolasi: {metode})")
    )
    ax.axis("off")
    fig.savefig(out + "_heatmap.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def gambar_status(
    t: pd.DataFrame,
    area: pd.DataFrame,
    ap: pd.DataFrame,
    out: str,
    denah: str | None,
    scale: float,
    ap_fisik: pd.DataFrame | None,
) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    latar(ax, denah, t)
    for st in LEVEL:
        s = t[t.status == st]
        ax.scatter(
            s.x_px,
            s.y_px,
            c=WARNA[st],
            s=90,
            edgecolors="k",
            label=f"{st} ({len(s)})",
            zorder=3,
        )
    kotak = {"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.8}
    posisi = t.set_index("titik_id")[["x_px", "y_px"]]
    for r in area.to_dict("records"):  # arsir 3 m di sekitar setiap titik anggota area
        anggota = posisi.loc[str(r["titik"]).split(", ")]
        for x, y in anggota.itertuples(index=False):
            ax.add_patch(
                Circle((x, y), 3 * scale, fc="#d73027", ec="none", alpha=0.18, zorder=2)
            )
        ax.annotate(
            str(r["area"]),
            (anggota.x_px.mean(), anggota.y_px.min() - 3 * scale),
            fontsize=11,
            weight="bold",
            color="#a50026",
            ha="center",
            va="center",
            zorder=6,
            bbox=kotak,
        )
    if not ap.empty:
        yakin = ap[ap.rssi_maks >= AP_TINGGI]
        mungkin = ap[(ap.rssi_maks < AP_TINGGI) & (ap.rssi_maks >= AP_SEDANG)]
        ax.scatter(
            yakin.x_est,
            yakin.y_est,
            marker="^",
            s=180,
            c="#2166ac",
            edgecolors="w",
            label="AP estimasi (di lantai ini)",
            zorder=5,
        )
        ax.scatter(
            mungkin.x_est,
            mungkin.y_est,
            marker="^",
            s=180,
            facecolors="none",
            edgecolors="#2166ac",
            lw=1.5,
            label="AP estimasi (mungkin lantai lain)",
            zorder=5,
        )
        for r in pd.concat([yakin, mungkin]).to_dict("records"):
            ax.annotate(
                f"ch{int(r['channel'])}",
                (r["x_est"], r["y_est"]),
                fontsize=8,
                color="#2166ac",
                xytext=(8, 6 if r["rssi_maks"] >= AP_TINGGI else -14),
                textcoords="offset points",
                zorder=6,
                bbox=kotak,
            )
    if ap_fisik is not None and len(ap_fisik):
        ax.scatter(
            ap_fisik.x_px,
            ap_fisik.y_px,
            marker="s",
            s=120,
            facecolors="none",
            edgecolors="#2166ac",
            lw=2,
            label="AP (observasi fisik)",
            zorder=5,
        )
    if len(area):
        ax.scatter(
            [], [], s=200, c="#d73027", alpha=0.3, label="Area lemah (A1, A2, ...)"
        )
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9)
    ax.set_title(
        "Status kualitas sinyal per titik, area lemah (A1, A2, ...) dan posisi AP"
    )
    ax.axis("off")
    fig.savefig(out + "_status.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def gambar_kanal(per_bssid: pd.DataFrame, ssid: str, band: str, out: str) -> None:
    tab = tabel_kanal(per_bssid, ssid)
    if tab.empty:
        return
    warna = {"SSID kampus": "#2166ac", "lainnya": "#bababa"}
    ax = tab.plot(
        kind="bar", stacked=True, figsize=(9, 4), color=[warna[c] for c in tab.columns]
    )
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.set_xlabel("Kanal primer")
    ax.set_ylabel("Jumlah radio")
    ax.set_title(f"Distribusi kanal {band} GHz")
    plt.tight_layout()
    plt.savefig(out + "_kanal.png", dpi=150)
    plt.close()


# ---------------------------------------------------------------- ringkasan (stdout + _ringkasan.txt)
def susun_ringkasan(
    t: pd.DataFrame,
    area: pd.DataFrame,
    ap: pd.DataFrame,
    a: argparse.Namespace,
) -> list[str]:
    n = len(t)

    def pct(m: pd.Series) -> float:
        return 100.0 * float(m.sum()) / n if n else 0.0

    kanal_ap = sorted(ap.channel.unique().tolist()) if len(ap) else "-"
    L = [
        f"Ringkasan analisis {a.out} (band {a.band} GHz, SSID {a.ssid})",
        f"Jumlah titik ukur          : {n}",
        f"RSSI >= {RSSI_BAIK} dBm (baik)     : {pct(t.rssi1 >= RSSI_BAIK):.1f}%",
        f"RSSI >= {RSSI_LEMAH} dBm            : {pct(t.rssi1 >= RSSI_LEMAH):.1f}%",
        f"RSSI <  {RSSI_KRITIS} dBm (blank)    : {pct(t.rssi1.isna() | (t.rssi1 < RSSI_KRITIS)):.1f}%",
        f"AP cadangan >= {RSSI_SEKUNDER} dBm     : {pct(t.rssi2 >= RSSI_SEKUNDER):.1f}%",
        f"CCI > {CCI_MAX} radio             : {pct(t.cci > CCI_MAX):.1f}%",
        f"RSSI median / min          : {t.rssi1.median():.1f} / {t.rssi1.min():.1f} dBm",
        f"Radio SSID kampus terdeteksi: {len(ap)}, kanal: {kanal_ap}",
        "",
        "Status titik:",
    ]
    L += [f"  {s:<10}: {int((t.status == s).sum())}" for s in LEVEL]
    L += ["", "Area lemah:"]
    L += [
        f"  {r['area']}: {r['jumlah_titik']} titik ({r['titik']}), "
        f"RSSI rata {r['rssi_rata']:.1f}, {r['status_terburuk']}, "
        f"penyebab dominan: {r['penyebab_dominan']}"
        for r in area.to_dict("records")
    ] or ["  (tidak ada)"]
    return L


# ---------------------------------------------------------------- analisis per langkah interpretasi
# kode -> (label, jenis bukti, tindakan yang disarankan). "terukur" = langsung dari data;
# "inferensi" = kesimpulan dari jarak/posisi, bukan pengukuran langsung.
PENYEBAB: dict[str, tuple[str, str, str]] = {
    "tanpa_ap_lantai": (
        "Tidak ada AP SSID target yang terdeteksi kuat di lantai ini",
        "terukur",
        "Tambah AP di lantai/area ini.",
    ),
    "jauh_dari_ap": (
        "Jauh dari AP terdekat di lantai ini",
        "inferensi",
        "Tambah atau relokasi AP agar mendekati area ini.",
    ),
    "terhalang": (
        "Dekat AP tetapi sinyal lemah (dugaan penghalang: dinding/lantai)",
        "inferensi",
        "Periksa penghalang fisik dan orientasi antena; pertimbangkan AP di dalam ruangan.",
    ),
    "jarak_sedang": (
        "Jarak sedang dari AP; pengaruh jarak dan penghalang tidak terpisahkan dari data RSSI",
        "inferensi",
        "Survei ulang dengan titik lebih rapat atau uji dengan AP sementara.",
    ),
    "bocor_lantai_lain": (
        "Sinyal terkuat berasal dari AP yang kemungkinan berada di lantai lain",
        "inferensi",
        "Tambah AP di lantai ini; sinyal yang diterima tidak berasal dari lantai ini.",
    ),
    "cci": (
        "Co-channel interference",
        "terukur",
        "Susun ulang channel plan; kurangi lebar kanal.",
    ),
    "beban": (
        "Kanal padat / beban tinggi",
        "terukur",
        "Tambah kapasitas (AP/radio) atau kurangi lebar kanal; pertimbangkan band steering.",
    ),
    "tanpa_cadangan": (
        "Tidak ada AP cadangan memadai untuk roaming",
        "terukur",
        f"Tambah AP agar ada tumpang tindih >= {RSSI_SEKUNDER} dBm.",
    ),
    "snr_rendah": (
        "SNR rendah (noise atau interferensi non-Wi-Fi)",
        "terukur",
        "Cari sumber noise; evaluasi kanal dan daya AP.",
    ),
    "kinerja_aktif": (
        "Uji aktif bermasalah (throughput, packet loss, latensi, atau probe gagal)",
        "terukur",
        "Telusuri penyebabnya per titik (lihat detail): CCI, beban kanal, atau roaming.",
    ),
    "roaming_tidak_stabil": (
        "Klien berpindah AP saat uji statis (asosiasi tidak stabil)",
        "terukur",
        "Periksa tumpang tindih sel antar-AP dan keseimbangan daya; hindari titik di batas sel.",
    ),
}


def bersih(x: Any) -> Any:
    """Ubah tipe numpy/pandas menjadi tipe JSON murni; NaN/inf menjadi null."""
    if isinstance(x, dict):
        return {str(k): bersih(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set):
        return [bersih(v) for v in x]
    if isinstance(x, bool | np.bool_):
        return bool(x)
    if isinstance(x, int | np.integer):
        return int(x)
    if isinstance(x, float | np.floating):
        f = float(x)
        return round(f, 2) if math.isfinite(f) else None
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    if x is None or x is pd.NA or x is pd.NaT:
        return None
    return x


def siapkan_keluaran_gabung(
    t: pd.DataFrame, ap: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pastikan CSV hasil analisis memenuhi kontrak yang dibaca gabung_lantai.py.

    `radio` pada _ap.csv dan `radio1` pada _titik.csv harus memakai identitas radio
    yang sama. BSSID dinormalisasi ke huruf kecil agar pencocokan antar-lantai stabil.
    Kolom detail lain tidak dihapus.
    """
    for kolom in KOLOM_GABUNG_TITIK:
        if kolom not in t.columns:
            keluar(f"kolom wajib '{kolom}' tidak tersedia pada keluaran _titik.csv")
    for kolom in KOLOM_GABUNG_AP:
        if kolom not in ap.columns:
            keluar(f"kolom wajib '{kolom}' tidak tersedia pada keluaran _ap.csv")

    titik = t.copy()
    titik["titik_id"] = titik["titik_id"].fillna("").astype(str).str.strip()
    titik["radio1"] = titik["radio1"].fillna("").astype(str).str.strip().str.lower()
    titik["rssi1"] = pd.to_numeric(titik["rssi1"], errors="coerce")

    estimasi = ap.copy()
    estimasi["radio"] = estimasi["radio"].fillna("").astype(str).str.strip().str.lower()
    estimasi["channel"] = pd.to_numeric(estimasi["channel"], errors="coerce")
    estimasi["rssi_maks"] = pd.to_numeric(estimasi["rssi_maks"], errors="coerce")
    tidak_valid = (
        estimasi["radio"].eq("")
        | estimasi["channel"].isna()
        | estimasi["rssi_maks"].isna()
    )
    if tidak_valid.any():
        catat_peringatan(
            f"{int(tidak_valid.sum())} baris AP tanpa radio/channel/rssi_maks valid "
            "dikeluarkan dari _ap.csv agar tidak menyebabkan gabung_lantai.py gagal"
        )
        estimasi = estimasi.loc[~tidak_valid].copy()
    if not estimasi.empty:
        estimasi["channel"] = estimasi["channel"].astype(int)

    # Letakkan kolom kontrak di depan agar format mudah diperiksa, tetapi pertahankan
    # seluruh kolom tambahan yang dipakai untuk peta/laporan.
    titik = titik[
        [
            *KOLOM_GABUNG_TITIK,
            *[c for c in titik.columns if c not in KOLOM_GABUNG_TITIK],
        ]
    ]
    estimasi = estimasi[
        [*KOLOM_GABUNG_AP, *[c for c in estimasi.columns if c not in KOLOM_GABUNG_AP]]
    ]
    return titik, estimasi


def muat_ap_fisik(path: str | None) -> pd.DataFrame | None:
    """Baca CSV observasi AP fisik (x_px, y_px, ap_id opsional); None bila tidak ada/tidak valid."""
    if not path:
        return None
    if not os.path.exists(path):
        catat_peringatan(f"file AP fisik tidak ditemukan, dilewati: {path}")
        return None
    f = pd.read_csv(path)
    if "x_px" not in f or "y_px" not in f:
        catat_peringatan(f"{path} harus punya kolom x_px dan y_px; AP fisik dilewati")
        return None
    f = f.copy()
    if "ap_id" not in f:
        f["ap_id"] = [f"AP{i + 1}" for i in range(len(f))]
    f["ap_id"] = f["ap_id"].astype(str)
    f["x_px"] = pd.to_numeric(f["x_px"], errors="coerce")
    f["y_px"] = pd.to_numeric(f["y_px"], errors="coerce")
    return f.dropna(subset=["x_px", "y_px"]).reset_index(drop=True)


def tabel_kanal(per_bssid: pd.DataFrame, ssid: str) -> pd.DataFrame:
    """Jumlah radio per kanal primer; kolom 'SSID kampus' dan 'lainnya'."""
    rad = per_bssid.drop_duplicates("radio")
    rad = rad.assign(
        jenis=np.where(
            rad.radio.isin(per_bssid[per_bssid.ssid == ssid].radio),
            "SSID kampus",
            "lainnya",
        )
    )
    tab = rad.groupby(["channel", "jenis"]).size().unstack(fill_value=0)
    tab.index = tab.index.astype(int)
    return tab


def kanal_dfs(ch: float, width: float) -> bool:
    """True bila salah satu kanal 20 MHz yang diduduki berada di rentang DFS."""
    return any(DFS_MIN <= c <= DFS_MAX for c in kanal_terpakai(ch, width))


def penanda_ap(rssi_maks: float) -> str:
    if rssi_maks >= AP_TINGGI:
        return "▲ (di lantai ini)"
    if rssi_maks >= AP_SEDANG:
        return "△ (mungkin tembus dari lantai lain)"
    return "tidak digambar (keyakinan rendah)"


def analisis_cakupan(t: pd.DataFrame, area: pd.DataFrame) -> dict[str, Any]:
    """Langkah 1: berapa % titik baik, dan di mana blank spot berada."""
    n = len(t)

    def pct(m: pd.Series) -> float:
        return round(100.0 * float(m.sum()) / n, 1) if n else 0.0

    ke_area: dict[str, str] = {}
    for r in area.to_dict("records"):
        for tid in str(r["titik"]).split(", "):
            ke_area[tid] = str(r["area"])

    blank = t[t.rssi1.isna() | (t.rssi1 < RSSI_KRITIS)]
    blank_spot: list[dict[str, Any]] = [
        {
            "titik_id": r["titik_id"],
            "ruang": r.get("ruang") or None,
            "x_px": r["x_px"],
            "y_px": r["y_px"],
            "rssi1_dbm": r["rssi1"],
            "alasan": "SSID target tidak terdeteksi"
            if pd.isna(r["rssi1"])
            else f"RSSI < {RSSI_KRITIS} dBm",
            "area": ke_area.get(str(r["titik_id"])),
        }
        for r in blank.to_dict("records")
    ]
    ada_ruang = "ruang" in t
    per_ruang: dict[str, list[str]] | None = None
    if ada_ruang:
        per_ruang = {}
        for b in blank_spot:
            per_ruang.setdefault(b["ruang"] or "(tanpa label ruang)", []).append(
                b["titik_id"]
            )

    return {
        "definisi": {
            "persen_rssi_baik": f"RSSI AP terkuat SSID target >= {RSSI_BAIK} dBm",
            "persen_status_baik": "status BAIK: lolos semua aturan (RSSI, cadangan, CCI, SNR, aktif)",
            "blank_spot": f"SSID target tidak terdeteksi atau RSSI < {RSSI_KRITIS} dBm",
        },
        "jumlah_titik": n,
        "persen_rssi_baik": pct(t.rssi1 >= RSSI_BAIK),
        "persen_rssi_ge_lemah": pct(t.rssi1 >= RSSI_LEMAH),
        "persen_blank_spot": pct(t.rssi1.isna() | (t.rssi1 < RSSI_KRITIS)),
        "persen_ap_cadangan_ok": pct(t.rssi2 >= RSSI_SEKUNDER),
        "persen_status_baik": pct(t.status == "BAIK"),
        "titik_ssid_tidak_terdeteksi": int(t.rssi1.isna().sum()),
        "rssi_median_dbm": t.rssi1.median(),
        "rssi_min_dbm": t.rssi1.min(),
        "distribusi_status": {s: int((t.status == s).sum()) for s in LEVEL},
        "blank_spot": {
            "jumlah": len(blank_spot),
            "titik": blank_spot,
            "per_ruang": per_ruang,
            "catatan": None
            if ada_ruang
            else "Kolom 'ruang' tidak ada di file titik; tambahkan kolom tersebut pada "
            "--titik agar blank spot dapat dipetakan ke ruangan.",
        },
    }


def analisis_pemetaan_ap(
    ap: pd.DataFrame, ap_fisik: pd.DataFrame | None, scale: float, jarak_cocok_m: float
) -> dict[str, Any]:
    """Langkah 2: bandingkan AP estimasi (▲/△) dengan AP fisik (□)."""
    rows = ap.to_dict("records")
    estimasi: list[dict[str, Any]] = [
        {
            "radio": r["radio"],
            "channel": int(r["channel"]),
            "lebar_mhz": r["width"],
            "rssi_maks_dbm": r["rssi_maks"],
            "titik_terkuat": r["titik_terkuat"],
            "n_titik_dipakai": r["n_titik_dipakai"],
            "x_est": r["x_est"],
            "y_est": r["y_est"],
            "keyakinan": r["keyakinan"],
            "penanda_peta": penanda_ap(r["rssi_maks"]),
        }
        for r in rows
    ]
    hasil: dict[str, Any] = {
        "jumlah_estimasi": len(rows),
        "jumlah_di_lantai_ini": sum(1 for r in rows if r["rssi_maks"] >= AP_TINGGI),
        "jumlah_mungkin_lantai_lain": sum(
            1 for r in rows if AP_SEDANG <= r["rssi_maks"] < AP_TINGGI
        ),
        "jumlah_keyakinan_rendah": sum(1 for r in rows if r["rssi_maks"] < AP_SEDANG),
        "estimasi": estimasi,
        "perbandingan_dengan_fisik": None,
    }
    if ap_fisik is None:
        hasil["catatan"] = (
            "Tanpa --ap-fisik, perbandingan ▲ dengan □ tidak dapat dilakukan."
        )
        return hasil

    est_xy = ap[["x_est", "y_est"]].to_numpy(float)
    fis_xy = ap_fisik[["x_px", "y_px"]].to_numpy(float)
    d = (
        np.hypot(
            est_xy[:, None, 0] - fis_xy[None, :, 0],
            est_xy[:, None, 1] - fis_xy[None, :, 1],
        )
        / scale
    )
    fisik: list[dict[str, Any]] = []
    for j, f in enumerate(ap_fisik.to_dict("records")):
        terdekat: str | None = None
        jarak: float | None = None
        if d.shape[0]:
            i = int(d[:, j].argmin())
            terdekat, jarak = str(rows[i]["radio"]), float(d[i, j])
        cocok = jarak is not None and jarak <= jarak_cocok_m
        fisik.append(
            {
                "ap_id": f["ap_id"],
                "x_px": f["x_px"],
                "y_px": f["y_px"],
                "estimasi_terdekat": terdekat,
                "jarak_m": jarak,
                "cocok": cocok,
                "interpretasi": "cocok dengan estimasi ▲/△"
                if cocok
                else "AP fisik tanpa ▲ di dekatnya: kemungkinan AP mati, memakai SSID lain, "
                "atau hanya memancarkan 2,4 GHz",
            }
        )
    tanpa_fisik: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        fisik_terdekat: str | None = None
        jarak_f: float | None = None
        if d.shape[1]:
            j = int(d[i, :].argmin())
            fisik_terdekat, jarak_f = str(ap_fisik.iloc[j]["ap_id"]), float(d[i, j])
        if jarak_f is not None and jarak_f <= jarak_cocok_m:
            continue
        if r["rssi_maks"] >= AP_TINGGI:
            teks = (
                "▲ tanpa □: kemungkinan AP tersembunyi di dalam ruangan (tidak tercatat pada "
                "observasi fisik); bisa juga berasal dari lantai lain"
            )
        elif r["rssi_maks"] >= AP_SEDANG:
            teks = (
                "△ tanpa □: kemungkinan sinyal tembus dari lantai lain; bisa juga AP "
                "tersembunyi di dalam ruangan"
            )
        else:
            teks = f"keyakinan rendah (RSSI maks < {AP_SEDANG} dBm): kemungkinan AP berada di lantai/area lain"
        tanpa_fisik.append(
            {
                "radio": r["radio"],
                "penanda_peta": penanda_ap(r["rssi_maks"]),
                "fisik_terdekat": fisik_terdekat,
                "jarak_fisik_terdekat_m": jarak_f,
                "interpretasi": teks,
            }
        )
    hasil["perbandingan_dengan_fisik"] = {
        "jarak_cocok_m": jarak_cocok_m,
        "jumlah_fisik": len(fisik),
        "jumlah_fisik_cocok": sum(1 for f in fisik if f["cocok"]),
        "jumlah_fisik_tanpa_estimasi": sum(1 for f in fisik if not f["cocok"]),
        "jumlah_estimasi_tanpa_fisik": len(tanpa_fisik),
        "fisik": fisik,
        "estimasi_tanpa_fisik": tanpa_fisik,
    }
    return hasil


def analisis_kanal(
    ap: pd.DataFrame, per_bssid: pd.DataFrame, t: pd.DataFrame, ssid: str, scale: float
) -> dict[str, Any]:
    """Langkah 3: kanal AP bertetangga, lebar kanal, pemanfaatan DFS."""
    rows = ap.to_dict("records")
    occ = [kanal_terpakai(r["channel"], r["width"]) for r in rows]
    radio: list[dict[str, Any]] = [
        {
            "radio": r["radio"],
            "channel": int(r["channel"]),
            "lebar_mhz": int(r["width"]),
            "dfs": kanal_dfs(r["channel"], r["width"]),
            "kanal_diduduki": sorted(o),
            "keyakinan": r["keyakinan"],
        }
        for r, o in zip(rows, occ, strict=True)
    ]
    lebar: dict[str, int] = {}
    for r in radio:
        k = str(r["lebar_mhz"])
        lebar[k] = lebar.get(k, 0) + 1
    n_dfs = sum(1 for r in radio if r["dfs"])

    bentrok: list[dict[str, Any]] = []
    n_tetangga = 0
    for i in range(len(rows)):
        if rows[i]["rssi_maks"] < AP_SEDANG:
            continue
        for j in range(i + 1, len(rows)):
            if rows[j]["rssi_maks"] < AP_SEDANG:
                continue
            jarak = float(
                np.hypot(
                    rows[i]["x_est"] - rows[j]["x_est"],
                    rows[i]["y_est"] - rows[j]["y_est"],
                )
                / scale
            )
            if jarak > AP_TETANGGA_M:
                continue
            n_tetangga += 1
            irisan = occ[i] & occ[j]
            if irisan:
                bentrok.append(
                    {
                        "radio_a": rows[i]["radio"],
                        "radio_b": rows[j]["radio"],
                        "jarak_m": jarak,
                        "channel_a": radio[i]["channel"],
                        "channel_b": radio[j]["channel"],
                        "kanal_beririsan": sorted(irisan),
                        "kanal_sama": radio[i]["channel"] == radio[j]["channel"],
                    }
                )
    bentrok.sort(key=lambda b: b["jarak_m"])

    tab = tabel_kanal(per_bssid, ssid)
    distribusi = {
        int(ch): {
            "ssid_kampus": int(row.get("SSID kampus", 0)),
            "lainnya": int(row.get("lainnya", 0)),
        }
        for ch, row in zip(tab.index.tolist(), tab.to_dict("records"), strict=True)
    }
    cci_tinggi = [
        {
            "titik_id": r["titik_id"],
            "ruang": r.get("ruang") or None,
            "kanal": r["channel1"],
            "cci": r["cci"],
        }
        for r in t[t.cci > CCI_MAX].to_dict("records")
    ]
    return {
        "jumlah_radio_ssid_target": len(radio),
        "radio": radio,
        "lebar_kanal_mhz": lebar,
        "dfs": {
            "jumlah_radio": n_dfs,
            "persen": round(100.0 * n_dfs / len(radio), 1) if radio else 0.0,
            "dimanfaatkan": n_dfs > 0,
            "rentang_kanal": f"{DFS_MIN}-{DFS_MAX}",
        },
        "distribusi_kanal": distribusi,
        "ap_bertetangga": {
            "jarak_maks_m": AP_TETANGGA_M,
            "hanya_radio_dengan_rssi_maks_dbm_ge": AP_SEDANG,
            "jumlah_pasangan": n_tetangga,
            "ada_kanal_beririsan": bool(bentrok),
            "pasangan_kanal_beririsan": bentrok,
        },
        "titik_cci_tinggi": cci_tinggi,
    }


def analisis_area(
    t: pd.DataFrame, area: pd.DataFrame, ap: pd.DataFrame, scale: float
) -> list[dict[str, Any]]:
    """Langkah 4: akar masalah tiap area lemah. Tiap titik anggota dinilai sendiri, lalu
    dihitung berapa anggota yang terkena tiap penyebab (lihat PENYEBAB)."""
    di_lantai = ap[ap.rssi_maks >= AP_TINGGI]
    ap_xy = di_lantai[["x_est", "y_est"]].to_numpy(float)
    ap_nama = [str(x) for x in di_lantai["radio"].tolist()]
    set_lantai = set(ap_nama)
    ada_ruang = "ruang" in t
    hasil: list[dict[str, Any]] = []
    for ar in area.to_dict("records"):
        ids = str(ar["titik"]).split(", ")
        anggota = t[t.titik_id.isin(ids)].to_dict("records")
        n = len(anggota)
        jarak: list[float] = []
        for m in anggota:
            if len(ap_xy):
                dd = np.hypot(ap_xy[:, 0] - m["x_px"], ap_xy[:, 1] - m["y_px"]) / scale
                jarak.append(float(dd.min()))
            else:
                jarak.append(math.inf)

        terkena: dict[str, list[str]] = {k: [] for k in PENYEBAB}
        detail_aktif: dict[str, list[str]] = {}
        for m, d in zip(anggota, jarak, strict=True):
            tid = str(m["titik_id"])
            rssi = m["rssi1"]
            if pd.isna(rssi) or rssi < RSSI_LEMAH:
                if not len(ap_xy):
                    terkena["tanpa_ap_lantai"].append(tid)
                elif d > JARAK_AP_JAUH_M:
                    terkena["jauh_dari_ap"].append(tid)
                elif d <= JARAK_AP_DEKAT_M:
                    terkena["terhalang"].append(tid)
                else:
                    terkena["jarak_sedang"].append(tid)
            radio1 = m.get("radio1")
            if isinstance(radio1, str) and radio1 and radio1 not in set_lantai:
                terkena["bocor_lantai_lain"].append(tid)
            if pd.notna(m["cci"]) and m["cci"] > CCI_MAX:
                terkena["cci"].append(tid)
            if pd.notna(m["util1"]) and m["util1"] > UTIL_MAX:
                terkena["beban"].append(tid)
            if pd.notna(rssi) and (pd.isna(m["rssi2"]) or m["rssi2"] < RSSI_SEKUNDER):
                terkena["tanpa_cadangan"].append(tid)
            if pd.notna(m["snr"]) and m["snr"] < SNR_BURUK:
                terkena["snr_rendah"].append(tid)
            masalah = masalah_aktif(m)
            if masalah:
                terkena["kinerja_aktif"].append(tid)
                detail_aktif[tid] = masalah
            if pd.notna(m.get("n_pindah_ap")) and m["n_pindah_ap"] > 0:
                terkena["roaming_tidak_stabil"].append(tid)

        diagnosis: list[dict[str, Any]] = []
        for kode, (label, jenis, tindakan) in PENYEBAB.items():
            ids_k = terkena[kode]
            if not ids_k:
                continue
            diagnosis.append(
                {
                    "kode": kode,
                    "penyebab": label,
                    "jenis_bukti": jenis,
                    "titik": ids_k,
                    "anggota_terkena": len(ids_k),
                    "dari": n,
                    "dominan": len(ids_k) * 2 >= n,
                    "tindakan": tindakan,
                    **({"detail": detail_aktif} if kode == "kinerja_aktif" else {}),
                }
            )
        diagnosis.sort(
            key=lambda x: -x["anggota_terkena"]
        )  # urutan katalog dipertahankan

        hingga = [d for d in jarak if math.isfinite(d)]
        pusat: dict[str, Any] | None = None
        if len(ap_xy):
            dc = np.hypot(ap_xy[:, 0] - ar["x_px"], ap_xy[:, 1] - ar["y_px"]) / scale
            k = int(dc.argmin())
            pusat = {"radio": ap_nama[k], "jarak_m": float(dc[k])}
        hasil.append(
            {
                "area": ar["area"],
                "titik": ids,
                "jumlah_titik": n,
                "ruang": sorted({str(m["ruang"]) for m in anggota if m.get("ruang")})
                if ada_ruang
                else None,
                "x_px": ar["x_px"],
                "y_px": ar["y_px"],
                "rssi_rata_dbm": ar["rssi_rata"],
                "status_terburuk": ar["status_terburuk"],
                "penyebab_dominan_skrip": ar["penyebab_dominan"],
                "jarak_ap_terdekat_m": {
                    "median": float(np.median(hingga)),
                    "min": min(hingga),
                    "maks": max(hingga),
                }
                if hingga
                else None,
                "ap_terdekat_dari_pusat": pusat,
                "penyebab_utama": diagnosis[0]["penyebab"]
                if diagnosis and diagnosis[0]["dominan"]
                else None,
                "diagnosis": diagnosis,
            }
        )
    return hasil


def masalah_aktif(r: dict[Any, Any]) -> list[str]:
    """Masalah pada metrik uji aktif satu titik (ambang sama dengan nilai_status)."""

    def ada(k: str) -> bool:
        return pd.notna(r.get(k))

    out: list[str] = []
    if ada("down_mbps") and r["down_mbps"] < DOWN_MIN:
        out.append("throughput rendah")
    if ada("loss_pct") and r["loss_pct"] > LOSS_MAX:
        out.append("packet loss")
    if ada("probe_gagal_pct") and r["probe_gagal_pct"] >= PROBE_GAGAL_MAX:
        out.append("probe gagal")
    if ada("rtt_ms") and r["rtt_ms"] > RTT_MAX:
        out.append("latensi tinggi")
    if ada("rtt_maks_ms") and r["rtt_maks_ms"] > RTT_SPIKE:
        out.append("lonjakan latensi")
    return out


def analisis_aktif(t: pd.DataFrame) -> dict[str, Any]:
    """Langkah 5: apakah titik buruk memang menunjukkan masalah pada uji aktif, dan adakah
    titik "RSSI bagus tetapi lambat"."""
    if "n_scan_active" not in t:
        return {
            "tersedia": False,
            "catatan": "Tanpa --active, verifikasi aktif tidak dapat dilakukan.",
        }
    metrik = (
        "down_mbps",
        "rtt_ms",
        "rtt_maks_ms",
        "jitter_ms",
        "loss_pct",
        "probe_gagal_pct",
    )
    recs = t.to_dict("records")

    def baris(r: dict[Any, Any], masalah: list[str]) -> dict[str, Any]:
        return {
            "titik_id": r["titik_id"],
            "ruang": r.get("ruang") or None,
            "rssi1_dbm": r["rssi1"],
            "status": r["status"],
            "n_scan_active": int(r["n_scan_active"]),
            **{k: r.get(k) for k in metrik},
            "masalah_aktif": masalah,
        }

    rssi_buruk = [r for r in recs if pd.isna(r["rssi1"]) or r["rssi1"] < RSSI_LEMAH]
    buruk_diuji: list[dict[str, Any]] = []
    for r in rssi_buruk:
        if r["n_scan_active"] > 0:
            m = masalah_aktif(r)
            buruk_diuji.append({**baris(r, m), "terkonfirmasi": bool(m)})
    tanpa_uji = [str(r["titik_id"]) for r in rssi_buruk if r["n_scan_active"] == 0]
    bagus_lambat: list[dict[str, Any]] = []
    for r in recs:
        if r["n_scan_active"] > 0 and pd.notna(r["rssi1"]) and r["rssi1"] >= RSSI_BAIK:
            m = masalah_aktif(r)
            if m:
                bagus_lambat.append(baris(r, m))
    n_konf = sum(1 for e in buruk_diuji if e["terkonfirmasi"])
    return {
        "tersedia": True,
        "ringkasan": {
            "titik_diuji": sum(1 for r in recs if r["n_scan_active"] > 0),
            "titik_tanpa_uji": sum(1 for r in recs if r["n_scan_active"] == 0),
            "titik_rssi_buruk_diuji": len(buruk_diuji),
            "titik_rssi_buruk_terkonfirmasi_aktif": n_konf,
            "persen_terkonfirmasi": round(100.0 * n_konf / len(buruk_diuji), 1)
            if buruk_diuji
            else None,
            "titik_rssi_bagus_tetapi_bermasalah": len(bagus_lambat),
        },
        "metrik_tersedia": {k: bool(k in t and t[k].notna().any()) for k in metrik},
        "titik_rssi_buruk_diuji": buruk_diuji,
        "titik_rssi_buruk_tanpa_uji": tanpa_uji,
        "rssi_bagus_tetapi_lambat": bagus_lambat,
        "catatan": (
            f"'RSSI buruk' = SSID tidak terdeteksi atau RSSI < {RSSI_LEMAH} dBm (status tidak "
            "dipakai agar tidak sirkular). 'Lambat/bermasalah' = throughput, packet loss, "
            "probe gagal, latensi, atau lonjakan latensi melewati ambang."
        ),
    }


def analisis_roaming(t: pd.DataFrame) -> dict[str, Any]:
    """Langkah 6: di mana AP berpindah, dan apakah ada ping yang hilang."""
    cad = t[t.rssi1.notna() & (t.rssi2.isna() | (t.rssi2 < RSSI_SEKUNDER))]
    hasil: dict[str, Any] = {
        "cadangan_ap": {
            "ambang_dbm": RSSI_SEKUNDER,
            "jumlah_titik_tanpa_cadangan": len(cad),
            "persen": round(100.0 * len(cad) / len(t), 1) if len(t) else 0.0,
            "titik": [
                {
                    "titik_id": r["titik_id"],
                    "ruang": r.get("ruang") or None,
                    "x_px": r["x_px"],
                    "y_px": r["y_px"],
                    "rssi1_dbm": r["rssi1"],
                    "rssi2_dbm": r["rssi2"],
                }
                for r in cad.to_dict("records")
            ],
        }
    }
    if "n_pindah_ap" not in t:
        hasil["uji_aktif"] = {
            "tersedia": False,
            "catatan": "Tanpa --active (kolom bssid_assoc), perpindahan AP tidak dapat dideteksi.",
        }
        return hasil

    def positif(v: Any) -> bool:
        return bool(pd.notna(v) and v > 0)

    kejadian: list[dict[str, Any]] = []
    for r in t[t.n_pindah_ap.fillna(0) > 0].to_dict("records"):
        kejadian.append(
            {
                "titik_id": r["titik_id"],
                "ruang": r.get("ruang") or None,
                "x_px": r["x_px"],
                "y_px": r["y_px"],
                "n_pindah": int(r["n_pindah_ap"]),
                "riwayat_asosiasi": r.get("riwayat_assoc"),
                "loss_saat_pindah_pct": r.get("loss_saat_pindah_pct"),
                "probe_gagal_saat_pindah_pct": r.get("probe_gagal_saat_pindah_pct"),
                "loss_titik_pct": r.get("loss_pct"),
                "ping_hilang": positif(r.get("loss_saat_pindah_pct"))
                or positif(r.get("probe_gagal_saat_pindah_pct")),
            }
        )
    non_terkuat = [
        {
            "titik_id": r["titik_id"],
            "radio_asosiasi": r["radio_assoc"],
            "radio_terkuat": r["radio1"],
        }
        for r in t[t.assoc_non_terkuat.astype(bool)].to_dict("records")
    ]
    hasil["uji_aktif"] = {
        "tersedia": True,
        "jumlah_titik_pindah": len(kejadian),
        "jumlah_titik_ping_hilang": sum(1 for k in kejadian if k["ping_hilang"]),
        "titik_dengan_perpindahan_ap": kejadian,
        "titik_asosiasi_bukan_ap_terkuat": non_terkuat,
        "catatan": "loss_saat_pindah = loss pada scan pertama setelah asosiasi berganti "
        "(scan ICMP; scan non-ICMP dihitung lewat probe_gagal).",
    }
    return hasil


def kualitas_data(t: pd.DataFrame) -> dict[str, Any]:
    """Aturan mana yang benar-benar aktif (punya data), dan peringatan selama eksekusi."""
    n = len(t)
    aturan: dict[str, Any] = {}
    for kol, nama in KOLOM_ATURAN.items():
        ada = kol in t
        terukur = int(t[kol].notna().sum()) if ada else 0
        aturan[nama] = {
            "kolom": kol,
            "ada_di_data": ada,
            "titik_terukur": terukur,
            "persen": round(100.0 * terukur / n, 1) if n else 0.0,
            "aktif": terukur > 0,
        }
    return {
        "cakupan_aturan": aturan,
        "titik_tanpa_uji_aktif": t.loc[t.n_scan_active == 0, "titik_id"].tolist()
        if "n_scan_active" in t
        else None,
        "log": LOG,
    }


def susun_analisis(
    t: pd.DataFrame,
    area: pd.DataFrame,
    ap: pd.DataFrame,
    per_bssid: pd.DataFrame,
    ap_fisik: pd.DataFrame | None,
    a: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "meta": {
            "dijalankan": datetime.now().astimezone().isoformat(timespec="seconds"),
            "ssid": a.ssid,
            "band_ghz": a.band,
            "prefix_keluaran": a.out,
            "input": jejak_input(
                passive=a.passive, titik=a.titik, active=a.active, ap_fisik=a.ap_fisik
            ),
            "parameter": {
                "skala_px_per_m": a.scale,
                "radius_area_lemah_m": a.radius,
                "jarak_cocok_ap_m": a.cocok_ap,
                "jarak_ap_jauh_m": JARAK_AP_JAUH_M,
                "jarak_ap_dekat_m": JARAK_AP_DEKAT_M,
                "jarak_tetangga_ap_m": AP_TETANGGA_M,
            },
            "ambang": {
                "rssi_baik": RSSI_BAIK,
                "rssi_lemah": RSSI_LEMAH,
                "rssi_kritis": RSSI_KRITIS,
                "rssi_sekunder": RSSI_SEKUNDER,
                "cci_rssi": CCI_RSSI,
                "cci_max": CCI_MAX,
                "snr_baik": SNR_BAIK,
                "snr_buruk": SNR_BURUK,
                "util_max_pct": UTIL_MAX,
                "down_min_mbps": DOWN_MIN,
                "loss_max_pct": LOSS_MAX,
                "rtt_max_ms": RTT_MAX,
                "rtt_spike_ms": RTT_SPIKE,
                "probe_gagal_max_pct": PROBE_GAGAL_MAX,
                "rssi_std_max_db": RSSI_STD_MAX,
                "ap_tinggi_dbm": AP_TINGGI,
                "ap_sedang_dbm": AP_SEDANG,
            },
        },
        "kualitas_data": kualitas_data(t),
        "langkah_1_cakupan": analisis_cakupan(t, area),
        "langkah_2_pemetaan_ap": analisis_pemetaan_ap(
            ap, ap_fisik, a.scale, a.cocok_ap
        ),
        "langkah_3_kanal": analisis_kanal(ap, per_bssid, t, a.ssid, a.scale),
        "langkah_4_area_lemah": analisis_area(t, area, ap, a.scale),
        "langkah_5_verifikasi_aktif": analisis_aktif(t),
        "langkah_6_roaming": analisis_roaming(t),
        "catatan_batasan": [
            "Posisi AP adalah weighted centroid dari maksimal 3 titik terkuat, bukan lokasi pasti.",
            "Penyebab 'jauh dari AP', 'dugaan penghalang', dan 'bocor dari lantai lain' adalah inferensi dari posisi dan RSSI; keberadaan dinding tidak diukur langsung.",
            "Tindakan per area berbasis penyebab; usulan koordinat AP baru tidak dihitung.",
        ],
    }


def tulis_json(path: str, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bersih(data), f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


# ---------------------------------------------------------------- main
def buat_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--passive", required=True)
    p.add_argument("--ssid", required=True)
    p.add_argument("--band", default="5")
    p.add_argument("--denah")
    p.add_argument(
        "--scale", type=float, required=True, help="piksel per meter pada denah"
    )
    p.add_argument("--out", required=True, help="prefix keluaran, mis. output/L3")
    p.add_argument(
        "--titik", help="titik_L{n}.csv: sumber koordinat titik (disarankan)"
    )
    p.add_argument("--active")
    p.add_argument("--ap-fisik", help="CSV ap_id,x_px,y_px hasil observasi fisik")
    p.add_argument(
        "--radius", type=float, default=8, help="radius (m) pengelompokan area lemah"
    )
    p.add_argument(
        "--cocok-ap",
        type=float,
        default=AP_COCOK_M,
        help="jarak maks (m) agar AP fisik dan AP estimasi dianggap sama",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    a = buat_parser().parse_args(argv)
    LOG.clear()
    for aliran in (
        sys.stdout,
        sys.stderr,
    ):  # konsol Windows: jangan crash karena emoji SSID
        if isinstance(aliran, io.TextIOWrapper):
            aliran.reconfigure(encoding="utf-8")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    df, semua = muat_passive(a.passive, a.band, a.titik)
    if not (df["ssid"] == a.ssid).any():
        top = (
            df.groupby("ssid").titik_id.nunique().sort_values(ascending=False).head(10)
        )
        daftar = "\n".join(f"  {k} ({v})" for k, v in top.items())
        keluar(
            f"SSID '{a.ssid}' tidak ditemukan di band {a.band} GHz (cek ejaan/huruf besar-kecil).\n"
            f"SSID yang terdeteksi (jumlah titik):\n{daftar}"
        )
    df["radio"] = kelompok_radio(df, a.ssid)
    t, per_bssid = metrik_titik(df, a.ssid, semua)

    if a.active:
        uniq = df.drop_duplicates("bssid")
        radio_map: dict[str, str] = {
            str(b): str(r) for b, r in zip(uniq["bssid"], uniq["radio"], strict=True)
        }
        agg = muat_aktif(a.active, radio_map, set(t.titik_id))
        t = t.merge(agg, on="titik_id", how="left")
        t["n_scan_active"] = t["n_scan_active"].fillna(0).astype(int)  # 0 = tidak diuji
        t["assoc_non_terkuat"] = (
            t["radio_assoc"].fillna("").ne("")
            & t["radio1"].ne("")
            & t["radio_assoc"].ne(t["radio1"])
        )

    t = pd.concat([t, t.apply(nilai_status, axis=1)], axis=1)
    area = kelompok_lemah(t, a.scale, a.radius)
    ap = estimasi_ap(per_bssid, a.ssid, a.scale)
    ap_fisik = muat_ap_fisik(a.ap_fisik)
    # Skema ekspor eksplisit untuk gabung_lantai.py: titik membutuhkan titik_id/rssi1/radio1;
    # AP membutuhkan radio/channel/rssi_maks. Seluruh kolom detail tetap disertakan.
    titik_csv, ap_csv = siapkan_keluaran_gabung(t, ap)
    titik_csv.to_csv(a.out + "_titik.csv", index=False)
    ap_csv.to_csv(a.out + "_ap.csv", index=False)
    area.to_csv(a.out + "_area_lemah.csv", index=False)

    gambar_heatmap(t, a.out, a.denah, a.ssid, a.band, a.scale)
    gambar_status(t, area, ap, a.out, a.denah, a.scale, ap_fisik)
    gambar_kanal(per_bssid, a.ssid, a.band, a.out)

    L = susun_ringkasan(t, area, ap, a)
    with open(a.out + "_ringkasan.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))

    tulis_json(
        a.out + "_analisis.json", susun_analisis(t, area, ap, per_bssid, ap_fisik, a)
    )
    print(f"Analisis lengkap: {a.out}_analisis.json", file=sys.stderr)


if __name__ == "__main__":
    main()
