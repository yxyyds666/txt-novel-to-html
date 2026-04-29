#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 txt-novel-to-html 极简纯文字版（无小说目录页）
 适配诺基亚 S30+ / S40 / Symbian 等极低内存功能机
 特性：
   - 完全无 CSS / JS / viewport，仅基础 HTML 标签
   - 正则智能分章 + 编码自动检测
   - 每本小说不再生成目录页，点击书名直接进入第 1 章
   - 章节内“返回目录”指向总目录页
   - 零第三方依赖，Python 3.6+ 标准库
"""

import os
import re
import shutil
import zipfile

# ========== 配置 ==========
NOVELS_DIR = "novels"               # 放 txt 文件的目录
OUTPUT_DIR = "output"
SITE_DIR = os.path.join(OUTPUT_DIR, "site")
ZIP_NAME = os.path.join(OUTPUT_DIR, "novel_site.zip")
LINES_PER_CHAPTER_FALLBACK = 80      # 未识别到章节标题时的固定行数

# 章节标题正则（覆盖绝大多数中文网文格式）
CHAPTER_PATTERN = re.compile(
    r'^\s*'
    r'(?:'
        r'第\s*[0-9零一二三四五六七八九十百千万]+[\s]*[章卷节部集篇回]'
        r'|Chapter\s*\d+'
        r'|[Vv]olume\s*\d+'
        r'|(?:序章|楔子|尾声|番外|后记|前言|引子|终章|结局)'
    r')'
    r'\s*.*',
    re.IGNORECASE
)


# ========== 工具函数 ==========
def read_file_with_encoding(filepath):
    """尝试多种常见中文编码读取文件，成功返回 (text, encoding)"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            if content and (len(content) > 10 or any('\u4e00' <= c <= '\u9fff' for c in content)):
                return content, enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法识别文件编码，已尝试: {encodings}")


def sanitize_filename(name):
    """清理文件名中的非法字符，限制长度"""
    safe = re.sub(r'[\\/*?:"<>|]', '', name).strip().rstrip('.')
    return safe[:50] if safe else "unnamed"


def split_by_chapter(lines):
    """正则分章，若全文无任何章节标题则返回空列表（触发回退）"""
    chapters = []
    current_title = "序章"
    current_lines = []
    matched_any = False

    for line in lines:
        if CHAPTER_PATTERN.match(line.strip()):
            if current_lines:
                chapters.append((current_title, current_lines))
            current_title = line.strip()
            current_lines = []
            matched_any = True
        else:
            current_lines.append(line.strip())

    if current_lines:
        chapters.append((current_title, current_lines))

    return chapters if matched_any else []


def split_by_fixed_lines(lines, per_chapter=80):
    """固定行数分章，返回 (标题, 行列表) 列表"""
    chapters = []
    for i in range(0, len(lines), per_chapter):
        chunk = lines[i:i + per_chapter]
        chapters.append((f"第{i // per_chapter + 1}部分", chunk))
    return chapters


# ========== 极简 HTML 生成 ==========
def generate_chapter_html(chapter_title, content_lines, prev_link, next_link, index_link):
    """生成单章页面（纯文字 + 超链接）"""
    body_text = "<br>\n".join(content_lines)

    nav = []
    if prev_link:
        nav.append(f'<a href="{prev_link}">上一章</a>')
    nav.append(f'<a href="{index_link}">返回目录</a>')
    if next_link:
        nav.append(f'<a href="{next_link}">下一章</a>')
    nav_str = " | ".join(nav)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><title>{chapter_title}</title></head>
<body>
<h2>{chapter_title}</h2>
<p>{nav_str}</p>
<hr>
<p>{body_text}</p>
<hr>
<p>{nav_str}</p>
</body>
</html>"""


def generate_root_index(novels_info):
    """总目录页：小说名 → 直接进入第 1 章"""
    items = "".join(
        f'<li><a href="{dir_name}/chapter_1.html">{title}</a></li>\n'
        for title, dir_name in novels_info
    )
    return f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><title>全部小说</title></head>
<body>
<h2>📚 全部小说</h2>
<ol>{items}</ol>
<hr>
<p>由 txt-novel-to-html 生成 · 纯文字极简版</p>
</body>
</html>"""


# ========== 单本小说处理 ==========
def process_novel(filepath, filename):
    print(f"📖 处理: {filename}")
    try:
        content, encoding = read_file_with_encoding(filepath)
    except Exception as e:
        print(f"⛔ 跳过 {filename}: {e}")
        return None

    # 过滤空行，第一行作书名
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) < 2:
        print(f"⛔ 跳过 {filename}: 内容过短")
        return None

    novel_title = lines[0]
    body = lines[1:]

    # 智能分章
    chapters = split_by_chapter(body)
    if not chapters:
        print(f"   ℹ️ 未检测到章节标题，固定 {LINES_PER_CHAPTER_FALLBACK} 行分章")
        chapters = split_by_fixed_lines(body, LINES_PER_CHAPTER_FALLBACK)
    else:
        print(f"   ✅ 识别到 {len(chapters)} 个章节")

    safe_title = sanitize_filename(novel_title)
    novel_dir = os.path.join(SITE_DIR, safe_title)
    os.makedirs(novel_dir, exist_ok=True)

    # 生成各章节 HTML（不再生成章节目录页）
    for i, (ch_title, ch_lines) in enumerate(chapters):
        prev_link = f"chapter_{i}.html" if i > 0 else None
        next_link = f"chapter_{i+2}.html" if i < len(chapters)-1 else None
        # “返回目录”链接改为总目录 ../index.html
        ch_html = generate_chapter_html(
            chapter_title=ch_title,
            content_lines=ch_lines,
            prev_link=prev_link,
            next_link=next_link,
            index_link="../index.html"
        )
        with open(os.path.join(novel_dir, f"chapter_{i+1}.html"), 'w', encoding='utf-8') as f:
            f.write(ch_html)

    print(f"   📁 已输出到: {novel_dir}")
    return (novel_title, safe_title)


def create_zip(source_dir, output_zip):
    """将生成站点打包为 ZIP"""
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                full = os.path.join(root, file)
                arcname = os.path.relpath(full, start=source_dir)
                zf.write(full, arcname)
    print(f"📦 已打包: {output_zip}")


# ========== 主流程 ==========
def main():
    if not os.path.isdir(NOVELS_DIR):
        print(f"❌ 目录 {NOVELS_DIR} 不存在，请先创建并放入 TXT 文件。")
        return

    txt_files = [f for f in os.listdir(NOVELS_DIR) if f.lower().endswith('.txt')]
    if not txt_files:
        print(f"⚠️ {NOVELS_DIR} 中没有找到 .txt 文件。")
        return

    # 清理旧输出站
    if os.path.exists(SITE_DIR):
        shutil.rmtree(SITE_DIR)
    os.makedirs(SITE_DIR, exist_ok=True)

    novels_info = []
    for fname in txt_files:
        res = process_novel(os.path.join(NOVELS_DIR, fname), fname)
        if res:
            novels_info.append(res)

    if not novels_info:
        print("⚠️ 没有成功生成任何小说。")
        return

    # 生成总目录
    with open(os.path.join(SITE_DIR, "index.html"), 'w', encoding='utf-8') as f:
        f.write(generate_root_index(novels_info))

    # 打包
    if os.path.exists(ZIP_NAME):
        os.remove(ZIP_NAME)
    create_zip(SITE_DIR, ZIP_NAME)

    print("🎉 完成！可在 output/site/ 查看或分享 output/novel_site.zip")


if __name__ == "__main__":
    main()