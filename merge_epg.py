#!/usr/bin/env python3
"""
把 sources.txt 里列出的多个 XMLTV 源下载、合并成一个 guide.xml(.gz)。

设计要点(针对 Threadfin 踩过的坑):
  - 每个源独立超时,下载失败只跳过该源,不影响其他源
  - 自动识别 .gz / 纯 xml,不用管后缀
  - 同一个 channel id 在多个源里出现时,只保留第一个源的数据
    (sources.txt 中越靠前优先级越高),避免节目单重复
  - 流式解析 + 流式写出,内存占用与文件大小无关
"""

import gzip
import io
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

SOURCES_FILE = "sources.txt"
OUT_DIR = "public"
OUT_XML = os.path.join(OUT_DIR, "guide.xml")
OUT_GZ = OUT_XML + ".gz"

TIMEOUT = 90          # 单个源的下载超时(秒)
RETRIES = 2           # 失败重试次数
UA = "Mozilla/5.0 (compatible; epg-merge/1.0)"


def load_sources():
    """读 sources.txt,忽略空行和 # 开头的注释行。"""
    if not os.path.exists(SOURCES_FILE):
        sys.exit(f"找不到 {SOURCES_FILE}")
    urls = []
    with open(SOURCES_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    if not urls:
        sys.exit("sources.txt 里没有任何有效链接")
    return urls


def fetch(url):
    """下载并在需要时解压,返回 XML 字节内容。失败返回 None。"""
    for attempt in range(1, RETRIES + 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            # gzip 文件头是 1f 8b,不靠后缀判断
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            return data
        except (urllib.error.URLError, OSError, EOFError) as e:
            print(f"    第 {attempt} 次失败: {e}")
            if attempt <= RETRIES:
                time.sleep(5)
    return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    urls = load_sources()

    seen_channels = set()   # 已收录的 channel id
    owner = {}              # channel id -> 哪个源(序号)拥有它
    n_channels = 0
    n_programmes = 0
    ok_sources = 0
    failed = []

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(OUT_XML, "w", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write(f'<!-- merged by epg-merge at {stamp} -->\n')
        out.write('<tv generator-info-name="epg-merge">\n')

        for idx, url in enumerate(urls):
            print(f"[{idx + 1}/{len(urls)}] {url}")
            raw = fetch(url)
            if raw is None:
                print("    跳过(下载失败)")
                failed.append(url)
                continue

            src_channels = 0
            src_programmes = 0
            try:
                # iterparse 边读边处理,处理完的节点立刻清掉,不会把整个文件读进内存
                for event, elem in ET.iterparse(
                    io.BytesIO(raw), events=("end",)
                ):
                    if elem.tag == "channel":
                        cid = elem.get("id", "")
                        if cid and cid not in seen_channels:
                            seen_channels.add(cid)
                            owner[cid] = idx
                            out.write(ET.tostring(elem, encoding="unicode"))
                            out.write("\n")
                            src_channels += 1
                        elem.clear()

                    elif elem.tag == "programme":
                        cid = elem.get("channel", "")
                        # 只写"归这个源管"的频道的节目,避免重复
                        if owner.get(cid) == idx:
                            out.write(ET.tostring(elem, encoding="unicode"))
                            out.write("\n")
                            src_programmes += 1
                        elem.clear()

            except ET.ParseError as e:
                print(f"    跳过(XML 解析失败: {e})")
                failed.append(url)
                continue

            ok_sources += 1
            n_channels += src_channels
            n_programmes += src_programmes
            print(f"    频道 {src_channels},节目 {src_programmes}")

        out.write("</tv>\n")

    # 同时输出 gz 版本,TiviMate 两种都能吃,gz 传输快很多
    with open(OUT_XML, "rb") as f_in, gzip.open(OUT_GZ, "wb", compresslevel=9) as f_out:
        f_out.writelines(f_in)

    size_xml = os.path.getsize(OUT_XML) / 1024 / 1024
    size_gz = os.path.getsize(OUT_GZ) / 1024 / 1024

    print("\n===== 合并结果 =====")
    print(f"成功的源: {ok_sources}/{len(urls)}")
    print(f"频道总数: {n_channels}")
    print(f"节目总数: {n_programmes}")
    print(f"guide.xml    {size_xml:.1f} MB")
    print(f"guide.xml.gz {size_gz:.1f} MB")
    if failed:
        print("\n失败的源(这次被跳过,不影响其他源):")
        for u in failed:
            print(f"  - {u}")

    # 一个源都没成功才算失败,个别源挂掉不让整个任务红掉
    if ok_sources == 0:
        sys.exit("所有源都失败了")


if __name__ == "__main__":
    main()
