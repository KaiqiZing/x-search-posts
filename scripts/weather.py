#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weather.py — 为 HTML 报告提供「当日天气」数据（免密钥，open-meteo）。

定位优先级（前面的赢）：
    1. 显式参数 --lat/--lon 或 --city
    2. 环境变量 X_WEATHER_CITY
    3. 技能目录下的 weather.json 配置文件（{"city":"深圳"} 或 {"lat":..,"lon":..}）
    4. IP 归属地（ipwho.is → ipapi.co → ip-api.com，逐个降级）
    5. 本地时区推算的兜底城市（配置 fallback_city，默认深圳）

IP 与本地时区冲突时的处理：
    本机时区是 UTC+8 的中国时区，但 IP 落在境外（常见于机房/代理出口）→ 判定 IP 不可信，
    直接走第 5 步兜底城市，避免把新加坡/东京的天气贴到深圳的报告上。

单独调试：
    python weather.py                 # 人类可读
    python weather.py --json          # 一行 JSON
    python weather.py --city 北京 --json
    python weather.py --refresh       # 忽略缓存，重新定位 + 取数
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

CONFIG_PATH = SKILL_DIR / "weather.json"
CACHE_DIR = Path.home() / ".workbuddy" / "skill-data" / "x-search-posts"
CACHE_PATH = CACHE_DIR / "weather_cache.json"

CACHE_TTL = 30 * 60          # 实况缓存 30 分钟（批量渲染 7 组时只打一次接口）
UA = "Mozilla/5.0 (compatible; x-search-posts/1.0; +https://x.com)"
TIMEOUT = 12

# 时区兜底城市（经纬度 + IANA 时区）
FALLBACK_CITIES: Dict[str, Tuple[float, float, str]] = {
    "深圳": (22.5455, 114.0683, "Asia/Shanghai"),
    "北京": (39.9042, 116.4074, "Asia/Shanghai"),
    "上海": (31.2304, 121.4737, "Asia/Shanghai"),
    "香港": (22.3193, 114.1694, "Asia/Hong_Kong"),
    "台北": (25.0330, 121.5654, "Asia/Taipei"),
    "东京": (35.6762, 139.6503, "Asia/Tokyo"),
    "新加坡": (1.3521, 103.8198, "Asia/Singapore"),
}

# WMO 天气代码 → (中文描述, 图标键)
WMO: Dict[int, Tuple[str, str]] = {
    0: ("晴", "sun"),
    1: ("晴间多云", "sun-cloud"),
    2: ("多云", "sun-cloud"),
    3: ("阴", "cloud"),
    45: ("有雾", "fog"),
    48: ("雾凇", "fog"),
    51: ("小毛毛雨", "drizzle"),
    53: ("毛毛雨", "drizzle"),
    55: ("大毛毛雨", "drizzle"),
    56: ("冻毛毛雨", "drizzle"),
    57: ("强冻毛毛雨", "drizzle"),
    61: ("小雨", "rain"),
    63: ("中雨", "rain"),
    65: ("大雨", "rain"),
    66: ("冻雨", "rain"),
    67: ("强冻雨", "rain"),
    71: ("小雪", "snow"),
    73: ("中雪", "snow"),
    75: ("大雪", "snow"),
    77: ("雪粒", "snow"),
    80: ("阵雨", "rain"),
    81: ("强阵雨", "rain"),
    82: ("暴雨", "rain"),
    85: ("阵雪", "snow"),
    86: ("强阵雪", "snow"),
    95: ("雷阵雨", "thunder"),
    96: ("雷阵雨伴冰雹", "thunder"),
    99: ("强雷暴伴冰雹", "thunder"),
}

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------------------------------------------------------------- 基础工具

def describe(code: Any) -> Tuple[str, str]:
    """WMO 代码 → (中文描述, 图标键)；未知代码回退「—」。"""
    try:
        return WMO.get(int(code), ("—", "cloud"))
    except (TypeError, ValueError):
        return ("—", "cloud")


def _get_json(url: str, timeout: int = TIMEOUT) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _local_offset_hours() -> float:
    off = datetime.now().astimezone().utcoffset()
    return off.total_seconds() / 3600 if off else 0.0


def _local_tz_is_cn() -> bool:
    names = " ".join(time.tzname or ()).lower()
    if any(k in names for k in ("中国", "china", "台北", "taipei", "香港", "hong kong")):
        return True
    return abs(_local_offset_hours() - 8) < 0.01


# ---------------------------------------------------------------- 配置

def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                return cfg
        except Exception:
            pass
    return {}


def geocode(city: str) -> Optional[Dict[str, Any]]:
    """城市名 → 经纬度（open-meteo geocoding，优先中国境内结果）。"""
    if city in FALLBACK_CITIES:
        lat, lon, tz = FALLBACK_CITIES[city]
        return {"city": city, "lat": lat, "lon": lon, "tz": tz,
                "admin": "", "country": "", "source": "preset"}
    q = urllib.parse.quote(str(city))
    data = _get_json(
        f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=5&language=zh&format=json")
    results = (data or {}).get("results") or []
    if not results:
        return None
    best = next((r for r in results if r.get("country_code") == "CN"), results[0])
    return {
        "city": best.get("name") or city,
        "lat": best.get("latitude"),
        "lon": best.get("longitude"),
        "tz": best.get("timezone") or "auto",
        "admin": best.get("admin1") or "",
        "country": best.get("country") or "",
        "source": "geocode",
    }


def locate_by_ip() -> Optional[Dict[str, Any]]:
    """IP 归属地（三家依次降级），返回 {city,lat,lon,tz,country_code,source,provider}。"""
    providers = [
        ("ipwho.is", "https://ipwho.is/?lang=zh-CN", lambda d: {
            "ok": d.get("success"), "city": d.get("city"), "lat": d.get("latitude"),
            "lon": d.get("longitude"), "tz": (d.get("timezone") or {}).get("id"),
            "cc": d.get("country_code"), "country": d.get("country"),
        }),
        ("ipapi.co", "https://ipapi.co/json/", lambda d: {
            "ok": bool(d.get("city")), "city": d.get("city"), "lat": d.get("latitude"),
            "lon": d.get("longitude"), "tz": d.get("timezone"),
            "cc": d.get("country_code"), "country": d.get("country_name"),
        }),
        ("ip-api.com", "http://ip-api.com/json/?lang=zh-CN&fields=status,country,countryCode,city,lat,lon,timezone",
         lambda d: {
             "ok": d.get("status") == "success", "city": d.get("city"), "lat": d.get("lat"),
             "lon": d.get("lon"), "tz": d.get("timezone"),
             "cc": d.get("countryCode"), "country": d.get("country"),
         }),
    ]
    for name, url, parse in providers:
        raw = _get_json(url, timeout=8)
        if not raw:
            continue
        try:
            rec = parse(raw)
        except Exception:
            continue
        if rec.get("ok") and rec.get("city") and rec.get("lat") is not None:
            return {
                "city": str(rec["city"]), "lat": float(rec["lat"]), "lon": float(rec["lon"]),
                "tz": rec.get("tz") or "auto", "cc": rec.get("cc") or "",
                "country": rec.get("country") or "", "source": "ip", "provider": name,
            }
    return None


def resolve_location(city: Optional[str] = None, lat: Optional[float] = None,
                     lon: Optional[float] = None) -> Dict[str, Any]:
    """按优先级确定位置，返回 {city,lat,lon,tz,source[,provider,note]}。"""
    cfg = load_config()

    if lat is not None and lon is not None:
        return {"city": city or cfg.get("city") or "本地", "lat": float(lat), "lon": float(lon),
                "tz": cfg.get("tz") or "auto", "source": "arg"}

    want = city or os.environ.get("X_WEATHER_CITY") or cfg.get("city")
    if want:
        geo = geocode(str(want))
        if geo:
            geo["source"] = "arg" if city else ("env" if os.environ.get("X_WEATHER_CITY") else "config")
            return geo

    if cfg.get("lat") is not None and cfg.get("lon") is not None:
        return {"city": cfg.get("city") or "本地", "lat": float(cfg["lat"]), "lon": float(cfg["lon"]),
                "tz": cfg.get("tz") or "auto", "source": "config"}

    ip = locate_by_ip()
    if ip:
        same_tz = False
        if _local_tz_is_cn() and ip.get("cc") not in ("CN", "HK", "MO", "TW"):
            same_tz = False
        else:
            same_tz = True
        if same_tz:
            return ip
        # IP 与时区冲突：本机在国内时区，IP 却在境外 → 视为代理出口，忽略
        fallback = str(cfg.get("fallback_city") or "深圳")
        geo = geocode(fallback) or {}
        if geo:
            geo.update({"source": "tz-fallback",
                        "note": f"IP 定位为{ip.get('city')}（疑似代理出口），按本地时区取{geo['city']}"})
            return geo

    fallback = str(cfg.get("fallback_city") or "深圳")
    geo = geocode(fallback)
    if geo:
        geo["source"] = "default"
        return geo
    raise RuntimeError("无法定位：IP 归属地与时区兜底均失败，请用 --city 指定城市")


# ---------------------------------------------------------------- 天气

def fetch_weather(loc: Dict[str, Any]) -> Dict[str, Any]:
    """open-meteo 实况 + 当日高低温/降水概率。"""
    lat, lon = loc["lat"], loc["lon"]
    tz = loc.get("tz") or "auto"
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
        f"&timezone={urllib.parse.quote(str(tz))}&forecast_days=1"
    )
    data = _get_json(url)
    if not data or "current" not in data:
        raise RuntimeError("open-meteo 未返回实况数据")

    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    code = cur.get("weather_code")
    cond, icon = describe(code)

    def _pick(key: str, idx: int = 0) -> Any:
        arr = daily.get(key) or []
        return arr[idx] if len(arr) > idx else None

    tmax, tmin = _pick("temperature_2m_max"), _pick("temperature_2m_min")
    pop = _pick("precipitation_probability_max")
    obs_raw = str(cur.get("time") or "")
    try:
        obs_dt = datetime.strptime(obs_raw, "%Y-%m-%dT%H:%M")
        obs_label = f"{obs_dt.month:02d}/{obs_dt.day:02d} {WEEKDAY_CN[obs_dt.weekday()]} {obs_dt:%H:%M}"
        date_label = f"{obs_dt.month:02d}/{obs_dt.day:02d} {WEEKDAY_CN[obs_dt.weekday()]}"
    except Exception:
        obs_label, date_label = obs_raw, ""

    out: Dict[str, Any] = {
        "ok": True,
        "city": loc.get("city") or "—",
        "admin": loc.get("admin") or "",
        "lat": lat, "lon": lon, "tz": tz,
        "obs_time": obs_raw,
        "obs_label": obs_label,
        "date_label": date_label,
        "temp": round(float(cur["temperature_2m"])) if cur.get("temperature_2m") is not None else None,
        "feels": round(float(cur["apparent_temperature"])) if cur.get("apparent_temperature") is not None else None,
        "humidity": cur.get("relative_humidity_2m"),
        "wind": cur.get("wind_speed_10m"),
        "is_day": cur.get("is_day"),
        "code": code,
        "cond": cond,
        "icon": icon,
        "tmax": round(float(tmax)) if tmax is not None else None,
        "tmin": round(float(tmin)) if tmin is not None else None,
        "pop": pop,
        "dcode": _pick("weather_code"),
        "dcond": describe(_pick("weather_code"))[0],
        "sunrise": (_pick("sunrise") or "")[11:16] or None,
        "sunset": (_pick("sunset") or "")[11:16] or None,
        "loc_source": loc.get("source") or "—",
        "loc_note": loc.get("note") or "",
        "provider": loc.get("provider") or "open-meteo",
        "fetched_at": datetime.now(timezone(timedelta(hours=_local_offset_hours()))).isoformat(timespec="seconds"),
    }
    return out


# ---------------------------------------------------------------- 缓存

def _read_cache() -> Optional[Dict[str, Any]]:
    if not CACHE_PATH.exists():
        return None
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - float(raw.get("ts") or 0) > CACHE_TTL:
            return None
        data = raw.get("data")
        return data if isinstance(data, dict) and data.get("ok") else None
    except Exception:
        return None


def _write_cache(data: Dict[str, Any]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def get_weather(city: Optional[str] = None, lat: Optional[float] = None,
                lon: Optional[float] = None, *, use_cache: bool = True,
                refresh: bool = False) -> Dict[str, Any]:
    """取当天天气（失败抛异常，调用方自行降级）。

    缓存只服务于「自动定位」这一条路径：显式指定城市/经纬度时既不读也不写，
    否则一次 --city 北京 的临时调用会污染后续默认取值（深圳）的缓存。
    """
    explicit = any(v is not None for v in (city, lat, lon))
    if use_cache and not refresh and not explicit:
        cached = _read_cache()
        if cached:
            cached["cached"] = True
            return cached
    loc = resolve_location(city=city, lat=lat, lon=lon)
    data = fetch_weather(loc)
    if use_cache and not explicit:
        _write_cache(data)
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="取当日天气（open-meteo，免密钥）")
    ap.add_argument("--city", help="城市名，如 深圳 / 北京")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--json", action="store_true", help="输出一行 JSON")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存")
    ap.add_argument("--no-cache", action="store_true", help="本次不读写缓存")
    args = ap.parse_args(argv)
    try:
        d = get_weather(args.city, args.lat, args.lon,
                        use_cache=not args.no_cache, refresh=args.refresh)
    except Exception as exc:  # noqa: BLE001
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[weather] 失败：{exc}")
        return 1
    if args.json:
        print(json.dumps(d, ensure_ascii=False))
    else:
        print(f"{d['city']} {d['date_label']} {d['obs_label'][-5:]} 实况 "
              f"{d['temp']}°C {d['cond']}（体感 {d['feels']}°C，湿度 {d['humidity']}%，"
              f"风 {d['wind']} km/h）｜{d['tmin']}~{d['tmax']}°C 降水 {d['pop']}%｜"
              f"定位来源 {d['loc_source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
