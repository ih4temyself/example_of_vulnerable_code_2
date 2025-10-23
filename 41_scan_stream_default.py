#!/usr/bin/python3

import os
import cv2
import time
import socket
import logging
from multiprocessing import Pool
import configparser
import pymysql
import requests
from pathlib import Path
from typing import List, Tuple, Optional

CONFIG_PATH = os.getenv("VIDEO_CONFIG_PATH", "/root/scripts/VIDEO/config.ini")
IMAGE_DIR = Path(os.getenv("SCAN_IMAGE_DIR", "/var/www/html/scan"))
IMAGE_URL_BASE = os.getenv("SCAN_IMAGE_URL_BASE")
POOL_PROCESSES = int(os.getenv("POOL_PROCESSES", str(max(4, (os.cpu_count() or 2) * 2))))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "300"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "8.0"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage" if TELEGRAM_BOT_TOKEN else None

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

IMAGE_DIR.mkdir(parents=True, exist_ok=True)

config = configparser.ConfigParser()
read_files = config.read(CONFIG_PATH)
if not read_files:
    logger.warning("config file not found at %s; ensure DB env vars or config file exist", CONFIG_PATH)

DB_HOST = os.getenv("MYSQL_HOST", config.get("MySQL", "host", fallback=None))
DB_USER = os.getenv("MYSQL_USER", config.get("MySQL", "user", fallback=None))
DB_PASS = os.getenv("MYSQL_PASSWORD", config.get("MySQL", "password", fallback=None))
DB_NAME = os.getenv("MYSQL_DATABASE", config.get("MySQL", "database", fallback=None))

if not all([DB_HOST, DB_USER, DB_PASS, DB_NAME]):
    raise RuntimeError("database configuration is incomplete, provide via config file or environment variables")

def _get_host_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())

    except Exception:
        return "127.0.0.1"

HOST_IP = _get_host_ip()
HOSTNAME = socket.gethostname()



def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
    )

def select_ip_list(up_host: str) -> List[Tuple[str, str, str]]:
    sql = (
        "SELECT `ip`, CONCAT(REPLACE(`ip`,'.','_'), '-', `country_code`, '-', `region`, '-', `city`) AS name_camera "
        "FROM rtsp_scan WHERE `url` IS NULL AND `up` = %s;"
    )
    with get_connection() as con:
        with con.cursor() as cur:
            cur.execute(sql, (up_host,))
            return cur.fetchall()

def get_view_support_paths() -> List[Tuple[str, Optional[str], Optional[str]]]:
    sql = "SELECT `path`, `login`, `passwd` FROM `view_support_path_default`"
    with get_connection() as con:
        with con.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

def insert_url(url_to_store: str, ip: str, link: str, login: Optional[str], passwd: Optional[str]) -> None:
    sql = (
        "UPDATE `rtsp_scan` SET `url` = %s, `up` = %s, `link` = %s, `login` = %s, `passwd` = %s "
        "WHERE `ip` = %s;"
    )
    with get_connection() as con:
        with con.cursor() as cur:
            cur.execute(sql, (url_to_store, HOSTNAME, link, login, passwd, ip))
        con.commit()

def safe_filename(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)

def build_image_url(filename: str) -> str:
    base = IMAGE_URL_BASE or f"http://{HOST_IP}/scan"
    return f"{base.rstrip('/')}/{filename}"

def job(task: Tuple[str, str, str, Optional[str], Optional[str]]) -> None:
    rtsp_url, ip, name_camera, login, passwd = task
    try:
        cap = cv2.VideoCapture(rtsp_url)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return

        filename = f"{safe_filename(name_camera)}.jpg"
        image_path = IMAGE_DIR / filename
        cv2.imwrite(str(image_path), frame)

        public_url = build_image_url(filename)

        insert_url(rtsp_url, ip, public_url, login, passwd)

    except Exception as e:
        logger.error("job failed for IP %s: %s", ip, e)



def main() -> None:
    link_list = get_view_support_paths()
    if not link_list:
        logger.warning("no support paths found")
        return

    for link_path, login, passwd in link_list:
        rows = select_ip_list(HOSTNAME)
        if not rows:
            logger.info("no ips to process for host '%s' right now", HOSTNAME)
            continue

        tasks = []
        for ip, name_camera in rows:
            rtsp_url = link_path.replace('ip_for_replace', ip)
            tasks.append((rtsp_url, ip, name_camera, login, passwd))

        start = time.time()
        processes = max(2, min(POOL_PROCESSES, 64))
        logger.info("starting pool with %d processes for %d tasks", processes, len(tasks))
        with Pool(processes=processes) as p:
            p.map(job, tasks)

        elapsed = int(time.time() - start)
        sleep_for = max(0, SLEEP_SECONDS - elapsed)
        logger.info("cycle took %ss; sleeping for %ss", elapsed, sleep_for)
        if sleep_for:
            time.sleep(sleep_for)

def notify_telegram(message: str) -> None:
    if not (TELEGRAM_API_URL and TELEGRAM_CHAT_ID):
        return
    
    try:
        requests.post(
            TELEGRAM_API_URL,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=REQUEST_TIMEOUT,
        )

    except Exception as e:
        logger.warning("telegram notification failed: %s", e)

if __name__ == "__main__":
    start_time = time.time()
    main()
    done = int(time.time() - start_time)
    notify_telegram(f"41_scan_stream_default done - {done}")
    
    try:
        import substream
        if hasattr(substream, "main"):
            substream.main()

    except Exception as e:
        logger.warning("substream call failed: %s", e)
